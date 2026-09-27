[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Fac-Raster.ps1')
$root=Split-Path $PSScriptRoot -Parent
$assetDir=Join-Path $root 'assets/fac-visuals'
$path=Join-Path $assetDir 'procedencia.json'
$records=@(Get-Content -LiteralPath $path -Raw | ConvertFrom-Json)
$edit=Get-Content -LiteralPath (Join-Path $assetDir 'revision_medicion.json') -Raw | ConvertFrom-Json
$sources=@{
    1='[1, 2, 4] MATB NASA y OpenMATB: monitoreo, seguimiento, comunicaciones y recursos.'
    2='[21] Manual ASTRA v2.6: áreas funcionales del hábitat terrestre.'
    3='[18, 19, 21] Roles de tripulación, MCC y CAPCOM; coordinación humana.'
    4='[21] Manual ASTRA v2.6: EVA terrestres simuladas en DM6 y DM12.'
    5='[11, 21] HRV y manual ASTRA: H10 para intervalos R–R, actigrafía y contexto de sueño.'
    6='[13, 15, 21] Interfaces de control, coordinación humano–UAS e investigación local.'
}
$reviews=@{
    1='Cuatro dominios reconocibles, controles y depósitos conceptuales, sin texto generado. No reproduce una interfaz ni un circuito real de aeronave.'
    2='Áreas conectadas y equipamiento coherente para convivencia e investigación terrestre. No es un plano verificado, ni representa gravedad o presión lunar; las personas no codifican el tamaño de muestra.'
    3='Dos equipos genéricos y muebles completos; no identifica tripulantes ni muestra telemetría fisiológica real. La cantidad de figuras no representa la dotación nominal.'
    4='Dos participantes con equipo de simulación y muestreo completos. Los cascos y mochilas son ilustrativos; no representan trajes certificados para vacío.'
    5='Variante revisada: cinturón torácico en contacto con piel, módulo central, sensor de muñeca, anatomía y rostros genéricos coherentes. Escena de sueño contextual; sin valores medidos. No identifica sujetos ni especifica un modelo exacto de actígrafo.'
    6='Entrenador de vuelo de escritorio, estación UAS y cuadricóptero conceptuales. No implica simulación multiaxial, transferencia demostrada ni uso de una aeronave específica.'
}
foreach($r in $records){
    if($r.id -eq 5 -and $r.file -ne $edit.file){
        $prior=[pscustomobject]@{file=$r.file;source_path=$r.source_path;prompt=$r.prompt;selected=$false;reason='Sustituida: sensor torácico sobre ropa y rostros sin rasgos. La variante v2 corrige ambos detalles.'}
        $r | Add-Member -NotePropertyName iterations -NotePropertyValue @($prior) -Force
        $r.file=$edit.file;$r.source_path=$edit.source_path;$r.prompt=$edit.prompt
    }
    $meta=Get-FacRasterFileInfo (Join-Path $assetDir $r.file)
    $r.visual_review=$reviews[[int]$r.id]
    $r.technical_review='passed: PNG real, píxeles alfa transparentes y contenido visible; dimensiones y SHA-256 registrados. Incrustación sin recorte verificada en el PPTX final por separado.'
    $r | Add-Member -NotePropertyName width -NotePropertyValue $meta.Width -Force
    $r | Add-Member -NotePropertyName height -NotePropertyValue $meta.Height -Force
    $r | Add-Member -NotePropertyName sha256 -NotePropertyValue $meta.Sha256.ToLowerInvariant() -Force
    $r | Add-Member -NotePropertyName scientific_basis -NotePropertyValue $sources[[int]$r.id] -Force
    $r | Add-Member -NotePropertyName selected -NotePropertyValue $true -Force
}
$records | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath $path -Encoding utf8
$md=[Collections.Generic.List[string]]::new()
foreach($s in @('# Ilustraciones de la ampliación EMAVI','','Seis láminas conceptuales generadas con la herramienta integrada `image_gen.imagegen`, modo built-in, el 27 de septiembre de 2026. El modelo no fue expuesto por la herramienta. Los archivos seleccionados se copiaron al repositorio conservando sus originales y el alfa generado. No se usaron fotografías de participantes ni datos personales.','','Las ilustraciones explican funciones y contextos; las tablas, cifras, etiquetas y conclusiones científicas permanecen como contenido editable. La revisión técnica no constituye validación experimental. Referencias numeradas en `../entregables/Referencias_APA.md`.','')){$md.Add($s)}
foreach($r in $records){
    $md.Add("## $($r.id). $($r.file)");$md.Add('')
    $md.Add("Archivo: [PNG seleccionado](../assets/fac-visuals/$($r.file)). Dimensiones: $($r.width) × $($r.height) px. SHA-256: ``$($r.sha256)``.")
    $md.Add('');$md.Add('**Base científica:** '+$r.scientific_basis)
    $md.Add('');$md.Add('**Revisión visual y límites:** '+$r.visual_review)
    $md.Add('');$md.Add('**Control técnico:** '+$r.technical_review)
    $md.Add('');$md.Add('**Prompt final:**');$md.Add('');$md.Add($r.prompt);$md.Add('')
}
$md.Add('La primera variante de medición se conserva solo como antecedente. Su exclusión, prompt inicial y ruta original figuran en `../assets/fac-visuals/procedencia.json`; no está incorporada a la presentación.')
$md | Set-Content -LiteralPath (Join-Path $root 'visuales/AMPLIACION_IMAGEGEN.md') -Encoding utf8
Write-Output 'Six selected illustrations: alpha, hashes and provenance recorded.'
