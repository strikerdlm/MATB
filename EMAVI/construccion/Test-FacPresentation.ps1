[CmdletBinding()]
param(
    [string]$DeckPath,
    [string]$ManifestPath,
    [string]$TemplatePath = (Join-Path $PSScriptRoot '..\fuentes\FAC-template.pptx')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Fac-Raster.ps1')
$msoFalse=0; $msoTrue=-1
$ExpectedTemplateSha256='147312EAAC5E5C164B9433B072C36C104BE8F8E090405539BB4E0BDBF4FC6959'
$Color=@{Gold=0x71D1F4;Blue=0x261300;Gray=0x404040;White=0xFFFFFF}
$Banned='(?i)(OPCI[ÓO]N\s*0?[12]|Esta\s+plantilla|USO\s+INADECUADO|\bX{4,}\b|\bXxxxx\b)'
function Fail([string]$Message) { throw "FAC-template validation failed: $Message" }
function Get-ShapeById($Slide,[int]$Id) { foreach($s in $Slide.Shapes){if($s.Id -eq $Id){return $s}}; Fail "Falta forma $Id en slide $($Slide.SlideIndex)." }
function Get-Text($Shape) { try { return [string]$Shape.TextFrame.TextRange.Text } catch { return '' } }
function Assert-Color($Shape,[int]$Expected,[string]$Slot) { if ($Shape.TextFrame.TextRange.Font.Color.RGB -ne $Expected) { Fail "$Slot no conserva el color requerido." } }
function Assert-Font($Shape,[string]$Name,[double]$Size,[string]$Slot) { $f=$Shape.TextFrame.TextRange.Font; if ($f.Name -ne $Name -or [Math]::Abs($f.Size-$Size)-gt 0.2) { Fail "$Slot no conserva $Name $Size pt." } }
function Assert-Geometry($Actual,$Expected,[string]$Name) { if ($Actual.Type -ne $Expected.Type -or [Math]::Abs($Actual.Left-$Expected.Left)-gt .2 -or [Math]::Abs($Actual.Top-$Expected.Top)-gt .2 -or [Math]::Abs($Actual.Width-$Expected.Width)-gt .2 -or [Math]::Abs($Actual.Height-$Expected.Height)-gt .2) { Fail "Se alteró la geometría de $Name." } }
function Assert-NoBannedText($Presentation) { foreach($slide in $Presentation.Slides){ foreach($shape in $slide.Shapes){ $text=Get-Text $shape; if($text -match $Banned){ Fail "Texto bloqueado en slide $($slide.SlideIndex): $($Matches[0])" } } } }
function Assert-Fits($Shape,[string]$Slot,[int]$MaximumLines=0) { $tr=$Shape.TextFrame.TextRange; if($tr.BoundHeight -gt $Shape.Height+.5 -or $tr.BoundWidth -gt $Shape.Width+.5){Fail "$Slot presenta overflow."}; if($MaximumLines -gt 0 -and [Math]::Ceiling($tr.BoundHeight/$tr.Font.Size) -gt $MaximumLines){Fail "$Slot excede $MaximumLines líneas renderizadas."}; if(($Shape.Top+$Shape.Height)-gt 470.5){Fail "$Slot invade la zona inferior protegida."} }
function Assert-Cucarda($Shape) { $paragraphs=$Shape.TextFrame.TextRange.Paragraphs(); for($i=1;$i -le $paragraphs.Count;$i++){ $paragraph=$paragraphs.Paragraphs($i); if([string]::IsNullOrWhiteSpace([string]$paragraph.Text)){continue}; $bullet=$paragraph.ParagraphFormat.Bullet; if($bullet.Visible -ne $msoTrue -or $bullet.Type -ne 3){Fail "La cucarda de shape17 párrafo $i no se preservó como viñeta gráfica."} } }

if (-not $IsWindows) { Fail 'Windows es obligatorio para validar con PowerPoint COM.' }
$templateFull=(Resolve-Path -LiteralPath $TemplatePath).Path
if ((Get-FileHash -LiteralPath $templateFull -Algorithm SHA256).Hash -ne $ExpectedTemplateSha256) { Fail 'La plantilla instalada no tiene el SHA-256 aprobado.' }
if (-not $DeckPath) {
    $work=Join-Path ([System.IO.Path]::GetTempPath()) ('fac-template-smoke-'+[guid]::NewGuid().ToString('N')); [void][System.IO.Directory]::CreateDirectory($work)
    $example=Join-Path $PSScriptRoot '..\examples\public-deck.example.json'; $placeholderDeck=Join-Path $work 'fac-public-placeholder-smoke.pptx'; $render=Join-Path $work 'placeholder-render'
    & (Join-Path $PSScriptRoot 'New-FacPresentation.ps1') -ManifestPath $example -OutputPath $placeholderDeck -RenderDirectory $render -AllowTemplateImageSmokeTest -SkipDeckValidation
    # Deliberately non-scientific raster fixture to exercise alpha and contain.
    $imagePath=Join-Path $work 'transparent-fixture.png'
    $fixture=[Drawing.Bitmap]::new(800,600); $graphics=[Drawing.Graphics]::FromImage($fixture)
    try { $graphics.Clear([Drawing.Color]::Transparent); $graphics.FillRectangle([Drawing.Brushes]::Navy,40,40,720,520); $fixture.Save($imagePath,[Drawing.Imaging.ImageFormat]::Png) }
    finally { $graphics.Dispose(); $fixture.Dispose() }
    $manifest=Get-Content -LiteralPath $example -Raw | ConvertFrom-Json; $imageItem=@($manifest.content | Where-Object type -eq 'image_text')[0]
    $imageItem.image.path=$imagePath; $imageItem.image.approved=$true; $imageItem.image.source='PNG transparente de prueba técnica local; no es una ilustración científica ni una imagen de API.'; $imageItem.image.alt='Rectángulo de prueba con borde transparente'
    $ManifestPath=Join-Path $work 'fac-public-real-image-smoke.json'; $manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $ManifestPath -Encoding utf8
    $DeckPath=Join-Path $work 'fac-public-real-image-smoke.pptx'; & (Join-Path $PSScriptRoot 'New-FacPresentation.ps1') -ManifestPath $ManifestPath -OutputPath $DeckPath -RenderDirectory (Join-Path $work 'real-image-render') -SkipDeckValidation
    Write-Host "FAC-template real-image smoke input: $imagePath"
}
$deckFull=(Resolve-Path -LiteralPath $DeckPath).Path
if (-not $ManifestPath) { Fail 'ManifestPath es obligatorio cuando se valida un deck existente.' }
$manifest=Get-Content -LiteralPath (Resolve-Path -LiteralPath $ManifestPath) -Raw | ConvertFrom-Json
foreach($item in @($manifest.content | Where-Object { $_.type -eq 'image_text' })) {
    if(-not [System.IO.Path]::IsPathRooted([string]$item.image.path)) {
        $item.image.path=[System.IO.Path]::GetFullPath((Join-Path (Split-Path -Parent (Resolve-Path -LiteralPath $ManifestPath).Path) ([string]$item.image.path)))
    }
}
if ($manifest.privacy.branch -ne 'qualified' -or $manifest.privacy.value -ne 'Público Clasificado') { Fail 'Rama EMAVI incorrecta.' }
$app=$null;$deck=$null;$template=$null
try {
    try {$app=New-Object -ComObject PowerPoint.Application} catch {Fail "PowerPoint COM no está disponible: $($_.Exception.Message)"}
    $deck=$app.Presentations.Open($deckFull,$msoFalse,$true,$false); $template=$app.Presentations.Open($templateFull,$msoFalse,$true,$false)
    if([Math]::Abs($deck.PageSetup.SlideWidth-960)-gt .1 -or [Math]::Abs($deck.PageSetup.SlideHeight-540)-gt .1){Fail 'El deck no es 960 × 540 pt.'}
    $agendaCount=[Math]::Ceiling(@($manifest.agenda).Count/5); $expectedCount=1+1+1+$agendaCount+@($manifest.content).Count+2
    if($deck.Slides.Count -ne $expectedCount){Fail "Secuencia inválida: se esperaban $expectedCount slides y existen $($deck.Slides.Count)."}; Assert-NoBannedText $deck
    foreach($pair in @(@(1,1),@($deck.Slides.Count,12))){$actual=$deck.Slides.Item($pair[0]);$expected=$template.Slides.Item($pair[1]);foreach($shape in $expected.Shapes){$match=$null;foreach($candidate in $actual.Shapes){if($candidate.Id -eq $shape.Id){$match=$candidate;break}};if($match){Assert-Geometry $match $shape "slide $($pair[0]) shape $($shape.Id)";if((Get-Text $shape) -ne (Get-Text $match)){Fail "Se reescribió texto fijo/legal en slide $($pair[0])."}}}}
    foreach($ni in @(2,($deck.Slides.Count-1))) {
        $notice=$deck.Slides.Item($ni); $original=$template.Slides.Item(4)
        foreach($id in @(11,12,13)){Assert-Geometry (Get-ShapeById $notice $id) (Get-ShapeById $original $id) 'aviso de privacidad'}
        foreach($id in @(11,12)){if((Get-Text (Get-ShapeById $notice $id)) -cne (Get-Text (Get-ShapeById $original $id))){Fail 'Se modificó el aviso legal.'}}
        if((Get-Text (Get-ShapeById $notice 13)) -cne 'Público Clasificado'){Fail 'Clasificación incorrecta.'}
    }
    for($ni=3;$ni -lt $deck.Slides.Count-1;$ni++) {
        $label=$deck.Slides.Item($ni).Shapes.Item('EMAVI_CLASSIFICATION')
        if((Get-Text $label) -cne 'Público Clasificado'){Fail 'Falta propagación de clasificación.'}
    }
    $index=3; $title=$deck.Slides.Item($index);$index++; foreach($id in @(4,5,6)){Assert-Geometry (Get-ShapeById $title $id) (Get-ShapeById $template.Slides.Item(5) $id) "slot portada $id"}; Assert-Font (Get-ShapeById $title 4) 'Arial' 40 'título de portada';Assert-Color (Get-ShapeById $title 4) $Color.Gold 'título de portada';Assert-Font (Get-ShapeById $title 5) 'Arial' 24 'presentador';Assert-Font (Get-ShapeById $title 6) 'Arial' 24 'cargo'
    for($a=0;$a -lt $agendaCount;$a++){$s=$deck.Slides.Item($index);$index++;foreach($id in @(4,5)){Assert-Geometry (Get-ShapeById $s $id) (Get-ShapeById $template.Slides.Item(6) $id) "slot agenda $id"};Assert-Font (Get-ShapeById $s 4) 'Arial' 40 'agenda';Assert-Color (Get-ShapeById $s 4) $Color.Gold 'agenda';Assert-Fits (Get-ShapeById $s 5) 'agenda'}
    foreach($item in $manifest.content){$s=$deck.Slides.Item($index);$index++;switch([string]$item.type){
        'section' {foreach($id in @(4,5)){Assert-Geometry (Get-ShapeById $s $id) (Get-ShapeById $template.Slides.Item(7) $id) "slot separador $id"};Assert-Font (Get-ShapeById $s 4) 'Times New Roman' 40 'separador';Assert-Color (Get-ShapeById $s 4) $Color.White 'separador'}
        'image_text' {foreach($id in @(6,7,15)){Assert-Geometry (Get-ShapeById $s $id) (Get-ShapeById $template.Slides.Item(8) $id) "slot imagen/texto $id"};$picture=$s.Shapes.Item('FAC_IMAGE_SLOT');Assert-Geometry $picture (Get-ShapeById $template.Slides.Item(8) 5) 'imagen contain';$raster=Get-FacRasterFileInfo ([string]$item.image.path);$crop=$picture.PictureFormat.Crop;if($crop.PictureWidth -gt $picture.Width+.2 -or $crop.PictureHeight -gt $picture.Height+.2 -or [Math]::Abs($crop.PictureOffsetX)-gt .2 -or [Math]::Abs($crop.PictureOffsetY)-gt .2 -or [Math]::Abs(($crop.PictureWidth/$crop.PictureHeight)-($raster.Width/$raster.Height))-gt .002){Fail 'La ilustración está recortada, desplazada o distorsionada.'};Assert-FacEmbeddedRaster $deckFull $s.SlideIndex ([string]$item.image.path);if($picture.AlternativeText -ne [string]$item.image.alt -or $picture.Title -ne [string]$item.image.source){Fail 'La imagen no conservó alt/source.'};Assert-Font (Get-ShapeById $s 7) 'Arial' 32 'título imagen';Assert-Color (Get-ShapeById $s 7) $Color.Blue 'título imagen';Assert-Font (Get-ShapeById $s 6) 'Arial' 14 'cuerpo imagen';Assert-Color (Get-ShapeById $s 6) $Color.Gray 'cuerpo imagen';Assert-Fits (Get-ShapeById $s 6) 'cuerpo imagen' 10}
        'text' {$titleShape=Get-ShapeById $s 9;$line=Get-ShapeById $s 19;Assert-Geometry $line (Get-ShapeById $template.Slides.Item(10) 19) 'línea texto';if($titleShape.TextFrame.TextRange.Font.Size -ne 32 -and $titleShape.TextFrame.TextRange.Font.Size -ne 24){Fail 'El título de texto no es 32/24 pt.'};$lineCount=[Math]::Ceiling(($titleShape.TextFrame.TextRange.BoundHeight/($titleShape.TextFrame.TextRange.Font.Size*1.2))-0.05);if($lineCount -gt 2 -or ($titleShape.Top+$titleShape.TextFrame.TextRange.BoundHeight)-gt 85.64){Fail 'El título de texto cruza la línea o excede dos líneas.'};if($lineCount -le 1){Assert-Geometry $titleShape (Get-ShapeById $template.Slides.Item(10) 9) 'título texto una línea'};Assert-Color $titleShape $Color.Blue 'título texto';$body=Get-ShapeById $s 17;Assert-Geometry $body (Get-ShapeById $template.Slides.Item(10) 17) 'cuerpo texto';Assert-Font $body 'Arial' 14 'cuerpo texto';Assert-Color $body $Color.Gray 'cuerpo texto';Assert-Fits $body 'cuerpo texto';if($item.PSObject.Properties.Name -contains 'bullets'){Assert-Cucarda $body}}
        default {Fail "Tipo inesperado $($item.type)"}
    }}
    Write-Host "FAC-template validation passed: $deckFull"
} finally {if($deck){try{$deck.Close()}catch{}};if($template){try{$template.Close()}catch{}};if($app){try{$app.Quit()}catch{}};[GC]::Collect();[GC]::WaitForPendingFinalizers()}
