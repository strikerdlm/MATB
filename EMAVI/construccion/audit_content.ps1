$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$manifest=Get-Content (Join-Path $root 'fuentes/manifest.json') -Raw | ConvertFrom-Json
$script=Get-Content (Join-Path $PSScriptRoot 'New-FacPresentation.ps1') -Raw
$first=$script.IndexOf('function Fail(');$last=$script.IndexOf('$manifestFullPath =')
Invoke-Expression $script.Substring($first,$last-$first)
$msoFalse=0;$msoTrue=-1;$msoAutoSizeNone=0
$color=@{Gold=0x71D1F4;Blue=0x261300;Gray=0x404040;White=0xFFFFFF}
$app=New-Object -ComObject PowerPoint.Application
$deck=$null;$rows=@()
try {
 $deck=$app.Presentations.Open((Join-Path $root 'fuentes/FAC-template.pptx'),0,-1,0)
 $i=4
 foreach($item in $manifest.content) {
  $i++
  $source=switch($item.type){'text'{10};'image_text'{8};'section'{7}}
  $copy=$deck.Slides.Item($source).Duplicate();$slide=$copy.Item(1);$slide.MoveTo($deck.Slides.Count)
  [void](Clean-Archetype $slide $source)
  $checks=@()
  switch($source){
   7 {Set-Text (Get-ShapeById $slide 4) $item.title 'Times New Roman' 40 $color.White;$checks=@(4)}
   8 {Set-Text (Get-ShapeById $slide 7) $item.title 'Arial' 32 $color.Blue $true;Set-Text (Get-ShapeById $slide 6) $item.body 'Arial' 14 $color.Gray $false 4;$checks=@(7,6)}
   10 {
    $title=Get-ShapeById $slide 9;Set-Text $title $item.title 'Arial' 32 $color.Blue $true
    $lines=[Math]::Ceiling(($title.TextFrame.TextRange.BoundHeight/(32*1.2))-.05)
    if($lines -gt 1){$baseBottom=$title.Top+$title.Height;Set-Text $title $item.title 'Arial' 24 $color.Blue $true;$height=$title.TextFrame.TextRange.BoundHeight;$title.Top=[single]($baseBottom-$height);$title.Height=[single]$height}
    Set-Text (Get-ShapeById $slide 17) ($item.bullets -join "`r") 'Arial' 14 $color.Gray $false 4;$checks=@(9,17)
   }
  }
  foreach($id in $checks){$shape=Get-ShapeById $slide $id;$tr=$shape.TextFrame.TextRange;$rows += [pscustomobject]@{slide=$i;title=$item.title;shape=$id;font=$tr.Font.Size;box_width=$shape.Width;box_height=$shape.Height;bound_width=$tr.BoundWidth;bound_height=$tr.BoundHeight;overflow=($tr.BoundWidth -gt $shape.Width+.5 -or $tr.BoundHeight -gt $shape.Height+.5);lines=[Math]::Ceiling($tr.BoundHeight/$tr.Font.Size)}}
  $slide.Delete()
 }
 $rows|ConvertTo-Json -Depth 5|Set-Content (Join-Path $root 'revision/auditoria_texto_previa.json') -Encoding utf8
 $rows|Where-Object {$_.overflow -or ($_.shape -eq 6 -and $_.lines -gt 10)}|ConvertTo-Json -Depth 5
 'Audited text slots: '+$rows.Count
} finally {if($deck){$deck.Saved=-1;$deck.Close()};$app.Quit()}
