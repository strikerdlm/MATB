[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
$root=Split-Path $PSScriptRoot -Parent
$source=Join-Path $root 'revision/diapositivas_ampliada'
$destination=Join-Path $root 'revision/contactos_ampliada'
[void][IO.Directory]::CreateDirectory($destination)
$files=@(Get-ChildItem -LiteralPath $source -Filter '*.PNG' | Sort-Object { [int]($_.BaseName -replace '\D','') })
if($files.Count -ne 40){throw 'Expected 40 native renders'}
$font=[Drawing.Font]::new('Arial',14)
try{
    for($group=0;$group -lt 10;$group++){
        $canvas=[Drawing.Bitmap]::new(1566,970)
        $graphics=[Drawing.Graphics]::FromImage($canvas)
        try{
            $graphics.Clear([Drawing.Color]::FromArgb(232,236,240))
            $graphics.InterpolationMode=[Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            for($j=0;$j -lt 4;$j++){
                $index=$group*4+$j
                $x=10+($j%2)*778;$y=10+[Math]::Floor($j/2)*478
                $graphics.DrawString(('Diapositiva '+($index+1)), $font, [Drawing.Brushes]::Navy, $x, $y)
                $img=[Drawing.Image]::FromFile($files[$index].FullName)
                try{$graphics.DrawImage($img,[Drawing.Rectangle]::new($x,$y+30,768,432))}finally{$img.Dispose()}
            }
            $canvas.Save((Join-Path $destination ('grupo-{0:00}.png' -f ($group+1))),[Drawing.Imaging.ImageFormat]::Png)
        }finally{$graphics.Dispose();$canvas.Dispose()}
    }
}finally{$font.Dispose()}
Write-Output '10 review sheets generated from 40 native slide renders.'
