[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ManifestPath,
    [Parameter(Mandatory)][string]$OutputPath,
    [string]$TemplatePath = (Join-Path $PSScriptRoot '..\fuentes\FAC-template.pptx'),
    [string]$RenderDirectory,
    [switch]$AllowTemplateImageSmokeTest,
    [switch]$SkipDeckValidation
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Fac-Raster.ps1')

$ExpectedTemplateSha256 = '147312EAAC5E5C164B9433B072C36C104BE8F8E090405539BB4E0BDBF4FC6959'
$msoFalse = 0; $msoTrue = -1; $msoAutoSizeNone = 0; $ppSaveAsPNG = 18
$color = @{ Gold = 0x71D1F4; Blue = 0x261300; Gray = 0x404040; White = 0xFFFFFF }

function Fail([string]$Message) { throw "FAC-template blocked: $Message" }
function Get-ShapeById($Slide, [int]$Id) {
    foreach ($s in $Slide.Shapes) { if ($s.Id -eq $Id) { return $s } }
    Fail "La forma inmutable/slot $Id no existe en la diapositiva $($Slide.SlideIndex)."
}
function Remove-ShapeIds($Slide, [int[]]$Ids) {
    foreach ($id in $Ids) { (Get-ShapeById $Slide $id).Delete() }
}
function Set-Text($Shape, [string]$Text, [string]$Font, [single]$Size, [int]$Rgb, [bool]$Bold = $false, [int]$Align = 2, [int]$ParagraphAlign = 0) {
    $geometry = @($Shape.Left,$Shape.Top,$Shape.Width,$Shape.Height)
    $Shape.TextFrame.AutoSize = $msoAutoSizeNone
    try { $Shape.TextFrame2.AutoSize = $msoAutoSizeNone } catch { }
    $Shape.TextFrame.TextRange.Text = $Text
    $Shape.Left=$geometry[0]; $Shape.Top=$geometry[1]; $Shape.Width=$geometry[2]; $Shape.Height=$geometry[3]
    $range = $Shape.TextFrame.TextRange
    $range.Font.Name = $Font; $range.Font.Size = $Size; $range.Font.Bold = $(if ($Bold) { $msoTrue } else { $msoFalse })
    $range.Font.Color.RGB = $Rgb; $range.ParagraphFormat.Alignment = $Align
    if ($ParagraphAlign -ne 0) { $range.ParagraphFormat.Alignment = $ParagraphAlign }
}
function Prepare-TextSlot($Shape) {
    $geometry = @($Shape.Left,$Shape.Top,$Shape.Width,$Shape.Height)
    $Shape.TextFrame.AutoSize = $msoAutoSizeNone
    try { $Shape.TextFrame2.AutoSize = $msoAutoSizeNone } catch { }
    $Shape.Left=$geometry[0]; $Shape.Top=$geometry[1]; $Shape.Width=$geometry[2]; $Shape.Height=$geometry[3]
}
function Assert-Geometry($Shape, [single]$Left, [single]$Top, [single]$Width, [single]$Height, [string]$Slot) {
    if ([Math]::Abs($Shape.Left-$Left) -gt 0.2 -or [Math]::Abs($Shape.Top-$Top) -gt 0.2 -or [Math]::Abs($Shape.Width-$Width) -gt 0.2 -or [Math]::Abs($Shape.Height-$Height) -gt 0.2) { Fail "$Slot cambió de geometría." }
}
function Assert-Fits($Shape, [string]$Slot, [int]$MaxLines = 0) {
    $tr = $Shape.TextFrame.TextRange
    if (($tr.BoundHeight -gt ($Shape.Height + 0.5)) -or ($tr.BoundWidth -gt ($Shape.Width + 0.5))) { Fail "$Slot tiene overflow; divida la diapositiva." }
    if ($MaxLines -gt 0) {
        $lines = [Math]::Ceiling($tr.BoundHeight / $tr.Font.Size)
        if ($lines -gt $MaxLines) { Fail "$Slot excede $MaxLines líneas renderizadas; divida la diapositiva." }
    }
    if (($Shape.Top + $Shape.Height) -gt 470.5) { Fail "$Slot invade la zona inferior protegida." }
}
function Get-FontNames {
    Add-Type -AssemblyName System.Drawing
    return [System.Drawing.Text.InstalledFontCollection]::new().Families.Name
}
function Assert-Dependencies {
    if (-not $IsWindows) { Fail 'Windows es obligatorio.' }
    $fonts = Get-FontNames
    foreach ($required in @('Arial','Times New Roman')) { if ($fonts -notcontains $required) { Fail "No está disponible la fuente obligatoria $required." } }
    try { return New-Object -ComObject PowerPoint.Application } catch { Fail "Microsoft PowerPoint COM no está disponible: $($_.Exception.Message)" }
}
function Get-Signature($Slide, [int[]]$Ids) {
    $parts = foreach ($id in $Ids) { $s = Get-ShapeById $Slide $id; '{0}|{1:N2}|{2:N2}|{3:N2}|{4:N2}|{5}' -f $id,$s.Left,$s.Top,$s.Width,$s.Height,$s.Type }
    return ($parts -join ';')
}
function Clean-Archetype($Slide, [int]$SourceIndex) {
    switch ($SourceIndex) {
        2 { Remove-ShapeIds $Slide @(6,7,8,9,10); return @(4,5) }
        3 { Remove-ShapeIds $Slide @(5,8,9,10,12,13,14); return @(6,7,11) }
        4 { return @(11,12,13) }
        5 { Remove-ShapeIds $Slide @(7,8,9,10,11); return @() }
        6 { Remove-ShapeIds $Slide @(6,7,8,9,10,12,13,14); return @() }
        7 { Remove-ShapeIds $Slide @(8,9,10,11,12,14,15); return @(5) }
        8 { Remove-ShapeIds $Slide @(8,9,10,11,13,14); return @(15) }
        10 { Remove-ShapeIds $Slide @(10,11,12,13,14,15,16,18); return @(19) }
        default { return @() }
    }
}
function Add-ApprovedImage($Slide, $Image, [switch]$AllowTemplatePlaceholder) {
    foreach ($key in @('path','approved','source','alt')) { if (-not $Image.PSObject.Properties.Name.Contains($key)) { Fail "La imagen no declara '$key'." } }
    if ($Image.approved -isnot [bool] -or $Image.approved -ne $true -or [string]::IsNullOrWhiteSpace($Image.source) -or [string]::IsNullOrWhiteSpace($Image.alt)) { Fail 'La imagen debe estar aprobada y tener origen y texto alternativo trazables.' }
    if ($Image.path -eq 'template://original-placeholder') {
        if (-not $AllowTemplatePlaceholder) { Fail 'template://original-placeholder solo se permite con -AllowTemplateImageSmokeTest.' }
        return
    }
    if (-not [System.IO.Path]::IsPathRooted([string]$Image.path) -or -not (Test-Path -LiteralPath $Image.path -PathType Leaf)) { Fail 'La imagen debe ser una ruta local absoluta existente.' }
    Get-FacRasterFileInfo ([string]$Image.path) | Out-Null
    $slot = Get-ShapeById $Slide 5; $left=$slot.Left; $top=$slot.Top; $width=$slot.Width; $height=$slot.Height; $slot.Delete()
    $picture=$Slide.Shapes.AddPicture([string]$Image.path,$msoFalse,$msoTrue,$left,$top,-1,-1)
    $crop=$picture.PictureFormat.Crop; $naturalWidth=$crop.PictureWidth; $naturalHeight=$crop.PictureHeight
    if ($naturalWidth -le 0 -or $naturalHeight -le 0) { Fail 'PowerPoint no devolvió dimensiones válidas para la imagen.' }
    $crop.ShapeLeft=$left; $crop.ShapeTop=$top; $crop.ShapeWidth=$width; $crop.ShapeHeight=$height
    $scale=[Math]::Min($width/$naturalWidth,$height/$naturalHeight)
    $crop.PictureWidth=$naturalWidth*$scale; $crop.PictureHeight=$naturalHeight*$scale; $crop.PictureOffsetX=0; $crop.PictureOffsetY=0
    $picture.Name='FAC_IMAGE_SLOT'; $picture.AlternativeText=[string]$Image.alt; $picture.Title=[string]$Image.source
    $picture.Tags.Add('fac.source',[string]$Image.source); $picture.Tags.Add('fac.alt',[string]$Image.alt)
    Assert-Geometry $picture $left $top $width $height 'imagen FAC contain'
}
function Assert-Manifest($Manifest) {
    foreach ($key in @('schema_version','privacy','title_page','agenda','content')) { if (-not $Manifest.PSObject.Properties.Name.Contains($key)) { Fail "Manifest sin '$key'." } }
    if ($Manifest.schema_version -ne '1.0.0') { Fail 'schema_version debe ser 1.0.0.' }
    if (@($Manifest.privacy).Count -ne 1 -or [string]::IsNullOrWhiteSpace([string]$Manifest.privacy.branch)) { Fail 'Debe declarar exactamente una rama de privacidad.' }
    switch ([string]$Manifest.privacy.branch) {
        'public' { }
        'classified' { if ([string]::IsNullOrWhiteSpace([string]$Manifest.privacy.level)) { Fail 'classified exige el nivel exacto.' }; Fail 'La v1 no puede propagar classified al cierre inmutable; entregue una política aprobada compatible.' }
        'qualified' { if ($Manifest.privacy.value -ne 'Público Clasificado') { Fail 'EMAVI requiere Público Clasificado.' }; $policy=Get-Content (Join-Path $PSScriptRoot '../fuentes/aprobacion_politica.json') -Raw | ConvertFrom-Json; if($policy.approved -ne $true){Fail 'La política gráfica debe estar aprobada.'} }
        default { Fail "Rama de privacidad no admitida: $($Manifest.privacy.branch)." }
    }
    foreach ($key in @('title','rank','presenter_name','role')) { if ([string]::IsNullOrWhiteSpace([string]$Manifest.title_page.$key)) { Fail "title_page sin '$key'." } }
    if (@($Manifest.agenda).Count -lt 1) { Fail 'La agenda debe tener al menos un tema.' }
}

$manifestFullPath = (Resolve-Path -LiteralPath $ManifestPath -ErrorAction Stop).Path
$templateFullPath = (Resolve-Path -LiteralPath $TemplatePath -ErrorAction Stop).Path
if ((Get-FileHash -LiteralPath $templateFullPath -Algorithm SHA256).Hash -ne $ExpectedTemplateSha256) { Fail 'SHA-256 de la plantilla no coincide con el valor aprobado.' }
$manifest = Get-Content -LiteralPath $manifestFullPath -Raw | ConvertFrom-Json
Assert-Manifest $manifest
foreach ($item in @($manifest.content | Where-Object { $_.type -eq 'image_text' })) {
    if (-not [System.IO.Path]::IsPathRooted([string]$item.image.path)) {
        $item.image.path = [System.IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $manifestFullPath) ([string]$item.image.path)))
    }
}
$outputFullPath = [System.IO.Path]::GetFullPath($OutputPath); [System.IO.Directory]::CreateDirectory((Split-Path -Parent $outputFullPath)) | Out-Null
Copy-Item -LiteralPath $templateFullPath -Destination $outputFullPath -Force

$app = $null; $presentation = $null
try {
    $app = Assert-Dependencies
    $presentation = $app.Presentations.Open($outputFullPath,$msoFalse,$false,$false)
    if ([Math]::Abs($presentation.PageSetup.SlideWidth - 960) -gt 0.1 -or [Math]::Abs($presentation.PageSetup.SlideHeight - 540) -gt 0.1) { Fail 'El tamaño no es 960 × 540 pt.' }
    $sourceIndexes = New-Object System.Collections.Generic.List[int]
    [void]$sourceIndexes.Add(1); [void]$sourceIndexes.Add(4); [void]$sourceIndexes.Add(5)
    $agendaChunks = @($manifest.agenda | ForEach-Object -Begin {$n=0} -Process { $n++; [PSCustomObject]@{N=$n;Text=[string]$_} } | Group-Object { [Math]::Floor(($_.N-1)/5) })
    foreach ($chunk in $agendaChunks) { [void]$sourceIndexes.Add(6) }
    foreach ($item in $manifest.content) { switch ($item.type) { 'section' {[void]$sourceIndexes.Add(7)} 'image_text' {[void]$sourceIndexes.Add(8)} 'text' {[void]$sourceIndexes.Add(10)} default { Fail "content.type no permitido: $($item.type)" } } }
    [void]$sourceIndexes.Add(4); [void]$sourceIndexes.Add(12)
    foreach ($sourceIndex in $sourceIndexes) { $copy = $presentation.Slides.Item($sourceIndex).Duplicate(); $copy.Item(1).MoveTo($presentation.Slides.Count) }
    for ($i=12; $i -ge 1; $i--) { $presentation.Slides.Item($i).Delete() }

    $agendaIndex=0; $contentIndex=0
    for ($i=1; $i -le $presentation.Slides.Count; $i++) {
        $slide = $presentation.Slides.Item($i); $sourceIndex = $sourceIndexes[$i-1]
        $protected = @(Clean-Archetype $slide $sourceIndex); $baseline = if ($protected.Count) { Get-Signature $slide $protected } else { '' }
        switch ($sourceIndex) {
            4 { (Get-ShapeById $slide 13).TextFrame.TextRange.Text='Público Clasificado' }
            5 {
                Set-Text (Get-ShapeById $slide 4) ([string]$manifest.title_page.title).ToUpperInvariant() 'Arial' 40 $color.Gold $false 2
                Set-Text (Get-ShapeById $slide 5) (('{0} {1}' -f $manifest.title_page.rank,([string]$manifest.title_page.presenter_name).ToUpperInvariant()).Trim()) 'Arial' 24 $color.White $true 2
                Set-Text (Get-ShapeById $slide 6) (Get-Culture).TextInfo.ToTitleCase(([string]$manifest.title_page.role).ToLowerInvariant()) 'Arial' 24 $color.White $false 2
                Assert-Fits (Get-ShapeById $slide 4) 'título de portada'; Assert-Fits (Get-ShapeById $slide 5) 'expositor de portada'; Assert-Fits (Get-ShapeById $slide 6) 'cargo de portada'
            }
            6 {
                $chunk = $agendaChunks[$agendaIndex]; $agendaIndex++
                $agendaShape=Get-ShapeById $slide 5; Prepare-TextSlot $agendaShape; $agendaShape.TextFrame.TextRange.Text=''
                foreach ($entry in $chunk.Group) {
                    $paragraph=$agendaShape.TextFrame.TextRange.Paragraphs($agendaShape.TextFrame.TextRange.Paragraphs().Count+1)
                    $paragraph.Text = "$($entry.N).   $($entry.Text)`r"; $paragraph.Font.Name='Arial'; $paragraph.Font.Size=28; $paragraph.Font.Color.RGB=$color.White
                    $paragraph.Characters(1,($entry.N.ToString().Length)).Font.Color.RGB=$color.Gold
                }
                Set-Text (Get-ShapeById $slide 4) 'AGENDA' 'Arial' 40 $color.Gold $false 2
                Assert-Fits $agendaShape 'agenda'
            }
            7 {
                $item=$manifest.content[$contentIndex]; $contentIndex++
                Set-Text (Get-ShapeById $slide 4) ([string]$item.title) 'Times New Roman' 40 $color.White $false 2
                Assert-Fits (Get-ShapeById $slide 4) 'separador'
            }
            8 {
                $item=$manifest.content[$contentIndex]; $contentIndex++
                Add-ApprovedImage $slide $item.image -AllowTemplatePlaceholder:$AllowTemplateImageSmokeTest
                Set-Text (Get-ShapeById $slide 7) ([string]$item.title) 'Arial' 32 $color.Blue $true 2
                Set-Text (Get-ShapeById $slide 6) ([string]$item.body) 'Arial' 14 $color.Gray $false 4
                Assert-Fits (Get-ShapeById $slide 7) 'título imagen'; Assert-Fits (Get-ShapeById $slide 6) 'cuerpo imagen' 10
            }
            10 {
                $item=$manifest.content[$contentIndex]; $contentIndex++
                $title=[string]$item.title; $titleShape=Get-ShapeById $slide 9; $baseBottom=$titleShape.Top+$titleShape.Height
                Set-Text $titleShape $title 'Arial' 32 $color.Blue $true 2
                $renderedLines=[Math]::Ceiling(($titleShape.TextFrame.TextRange.BoundHeight/(32*1.2))-0.05)
                if ($renderedLines -gt 1) { Set-Text $titleShape $title 'Arial' 24 $color.Blue $true 2; $renderedLines=[Math]::Ceiling(($titleShape.TextFrame.TextRange.BoundHeight/(24*1.2))-0.05) }
                if ($renderedLines -gt 2) { Fail 'Título de texto excede dos líneas; divida la diapositiva.' }
                if ($renderedLines -gt 1) { $requiredHeight=[single]$titleShape.TextFrame.TextRange.BoundHeight; $titleShape.Top=[single]($baseBottom-$requiredHeight); $titleShape.Height=[single]$requiredHeight }
                if (($titleShape.Top+$titleShape.TextFrame.TextRange.BoundHeight) -gt $baseBottom+0.2) { Fail 'Título de texto cruza la línea inmutable; acórtelo o divida la diapositiva.' }
                $body=Get-ShapeById $slide 17; Prepare-TextSlot $body; $body.TextFrame.TextRange.Text=''
                if ($item.PSObject.Properties.Name.Contains('bullets')) {
                    foreach ($line in @($item.bullets)) { if ([string]::IsNullOrWhiteSpace([string]$line) -or [string]$line -match '[•◦▪◾]') { Fail 'Las listas no pueden incluir viñetas Unicode.' }; $p=$body.TextFrame.TextRange.Paragraphs($body.TextFrame.TextRange.Paragraphs().Count+1); $p.Text="$line`r"; $p.Font.Name='Arial';$p.Font.Size=14;$p.Font.Color.RGB=$color.Gray; $body.TextFrame.TextRange.Font.Name='Arial'; $body.TextFrame.TextRange.Font.Size=14; $body.TextFrame.TextRange.Font.Color.RGB=$color.Gray }
                } elseif ($item.PSObject.Properties.Name.Contains('body')) { Set-Text $body ([string]$item.body) 'Arial' 14 $color.Gray $false 4 } else { Fail 'text exige body o bullets.' }
                Assert-Fits (Get-ShapeById $slide 9) 'título texto'; Assert-Fits $body 'cuerpo texto'
            }
        }
        if($sourceIndex -notin @(1,4,12)) {
            $label=$slide.Shapes.AddTextbox(1,640,10,220,20)
            $label.Name='EMAVI_CLASSIFICATION'
            $label.TextFrame.MarginLeft=0; $label.TextFrame.MarginRight=0; $label.TextFrame.MarginTop=0; $label.TextFrame.MarginBottom=0
            $label.TextFrame.TextRange.Text='Público Clasificado'
            $label.TextFrame.TextRange.Font.Name='Arial';$label.TextFrame.TextRange.Font.Size=12
            $label.TextFrame.TextRange.Font.Color.RGB=255;$label.TextFrame.TextRange.Font.Bold=-1
            $label.TextFrame.TextRange.ParagraphFormat.Alignment=2
        }
        if ($protected.Count -and (Get-Signature $slide $protected) -ne $baseline) { Fail "Se alteró una forma inmutable en arquetipo $sourceIndex." }
    }
    $notes=Get-Content (Join-Path $PSScriptRoot '../fuentes/notas.json') -Raw | ConvertFrom-Json
    if($notes.Count -ne $presentation.Slides.Count){Fail 'Notas y diapositivas no coinciden.'}
    for($n=1;$n -le $presentation.Slides.Count;$n++) {
        $note=$notes[$n-1]
        foreach($shape in $presentation.Slides.Item($n).NotesPage.Shapes) {
            if($shape.Type -eq 14 -and $shape.PlaceholderFormat.Type -eq 2) {
                $shape.TextFrame.TextRange.Text="GUION ORAL ($($note.seconds) s)`r`r$($note.oral)`r`rAPOYO Y FUENTES`r$($note.sources)"
            }
        }
    }
    $presentation.BuiltInDocumentProperties.Item('Title').Value='MATB y ASTRA - EMAVI'
    $presentation.BuiltInDocumentProperties.Item('Author').Value='SMSM DIEGO L MALPICA'
    $presentation.BuiltInDocumentProperties.Item('Subject').Value='Público Clasificado - Investigación y demostración'
    $presentation.Save()
    $presentation.SaveAs([IO.Path]::ChangeExtension($outputFullPath,'.pdf'),32)

    if ($RenderDirectory) { $renderFull=[System.IO.Path]::GetFullPath($RenderDirectory); [System.IO.Directory]::CreateDirectory($renderFull)|Out-Null; $presentation.SaveAs($renderFull,$ppSaveAsPNG) }
    $presentation.Close(); $presentation=$null; $app.Quit(); $app=$null
    if (-not $SkipDeckValidation) { & (Join-Path $PSScriptRoot 'Test-FacPresentation.ps1') -DeckPath $outputFullPath -ManifestPath $manifestFullPath }
    Write-Host "FAC-template created: $outputFullPath"
} finally {
    if ($presentation) { try {$presentation.Close()} catch {} }
    if ($app) { try {$app.Quit()} catch {} }
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()
}
