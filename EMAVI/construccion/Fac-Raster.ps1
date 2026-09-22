# Shared raster checks. No image generation or background removal occurs here.
Add-Type -AssemblyName System.Drawing

function Get-FacRasterInfo([byte[]]$Bytes) {
    $stream = [IO.MemoryStream]::new($Bytes, $false)
    $bitmap = $null; $locked = $null
    try {
        $bitmap = [Drawing.Bitmap]::new($stream)
        if ($bitmap.RawFormat.Guid -ne [Drawing.Imaging.ImageFormat]::Png.Guid) {
            throw 'FAC image must be an actual PNG; SVG/JPEG and renamed files are rejected.'
        }
        $rect = [Drawing.Rectangle]::new(0, 0, $bitmap.Width, $bitmap.Height)
        $locked = $bitmap.LockBits($rect, [Drawing.Imaging.ImageLockMode]::ReadOnly, [Drawing.Imaging.PixelFormat]::Format32bppArgb)
        $transparent = $false; $visible = $false
        $row = [byte[]]::new($bitmap.Width * 4)
        for ($y=0; $y -lt $bitmap.Height -and -not ($transparent -and $visible); $y++) {
            [Runtime.InteropServices.Marshal]::Copy([IntPtr]::Add($locked.Scan0, $y * $locked.Stride), $row, 0, $row.Length)
            for ($i=3; $i -lt $row.Length; $i+=4) {
                if ($row[$i] -eq 0) { $transparent=$true } else { $visible=$true }
                if ($transparent -and $visible) { break }
            }
        }
        if (-not $transparent -or -not $visible) { throw 'FAC PNG needs fully transparent pixels and visible content; opaque or empty images are rejected.' }
        return [pscustomobject]@{Width=$bitmap.Width; Height=$bitmap.Height; Sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes))}
    } finally {
        if ($locked) { $bitmap.UnlockBits($locked) }
        if ($bitmap) { $bitmap.Dispose() }
        $stream.Dispose()
    }
}

function Get-FacRasterFileInfo([string]$Path) {
    if ([IO.Path]::GetExtension($Path) -ine '.png') { throw 'FAC image must use the .png extension; SVG is prohibited.' }
    return Get-FacRasterInfo ([IO.File]::ReadAllBytes($Path))
}

function Assert-FacEmbeddedRaster([string]$DeckPath, [int]$SlideIndex, [string]$SourcePath) {
    $original = Get-FacRasterFileInfo $SourcePath
    $zip = [IO.Compression.ZipFile]::OpenRead($DeckPath)
    try {
        function Read-ZipXml([string]$Name) {
            $entry=$zip.GetEntry($Name)
            if (-not $entry) { throw "Missing PPTX part: $Name" }
            $reader=[IO.StreamReader]::new($entry.Open())
            try { return [xml]$reader.ReadToEnd() } finally { $reader.Dispose() }
        }
        $slide = Read-ZipXml "ppt/slides/slide$SlideIndex.xml"
        $pic=$slide.SelectSingleNode("//*[local-name()='pic'][*[local-name()='nvPicPr']/*[local-name()='cNvPr'][@name='FAC_IMAGE_SLOT']]")
        if (-not $pic -or $pic.SelectSingleNode(".//*[local-name()='svgBlip']")) { throw 'Missing FAC raster slot or prohibited SVG image.' }
        $blip=$pic.SelectSingleNode(".//*[local-name()='blip']")
        $relId=$blip.GetAttribute('embed','http://schemas.openxmlformats.org/officeDocument/2006/relationships')
        $rels=Read-ZipXml "ppt/slides/_rels/slide$SlideIndex.xml.rels"
        $rel=@($rels.Relationships.Relationship | Where-Object Id -eq $relId)[0]
        if (-not $rel -or $rel.GetAttribute('TargetMode') -eq 'External') { throw 'Image must be embedded, not externally linked.' }
        $uri=[Uri]::new([Uri]'https://pptx.local/ppt/slides/',[string]$rel.Target)
        $entry=$zip.GetEntry($uri.AbsolutePath.TrimStart('/'))
        if (-not $entry) { throw 'Missing embedded image data.' }
        $buffer=[IO.MemoryStream]::new(); $inputStream=$entry.Open()
        try { $inputStream.CopyTo($buffer); $embedded=Get-FacRasterInfo ($buffer.ToArray()) }
        finally { $inputStream.Dispose(); $buffer.Dispose() }
        if ($original.Sha256 -ne $embedded.Sha256) { throw 'Embedded image does not match the approved PNG; preserve the original bytes and alpha.' }
    } finally { $zip.Dispose() }
}
