$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$app=New-Object -ComObject PowerPoint.Application
$deck=$null
try {
    $deck=$app.Presentations.Open((Join-Path $root 'fuentes/FAC-template.pptx'),0,0,0)
    foreach($i in @(4,12)) { $copy=$deck.Slides.Item($i).Duplicate(); $copy.Item(1).MoveTo($deck.Slides.Count) }
    for($i=12;$i -ge 1;$i--){$deck.Slides.Item($i).Delete()}
    foreach($shape in $deck.Slides.Item(1).Shapes){if($shape.Id -eq 13){$shape.TextFrame.TextRange.Text='Público Clasificado'}}
    $out=Join-Path $root 'revision/vista_previa_politica'
    [void][IO.Directory]::CreateDirectory($out)
    $deck.SaveAs((Join-Path $out 'Aviso_y_cierre_propuestos.pptx'),24)
    $deck.SaveAs((Join-Path $out 'Aviso_y_cierre_propuestos.pdf'),32)
    foreach($i in @(1,2)){$deck.Slides.Item($i).Export((Join-Path $out "Slide$i.png"),'PNG',1440,810)}
} finally { if($deck){$deck.Close()}; $app.Quit() }
