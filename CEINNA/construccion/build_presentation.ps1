param([string]$Root = 'E:\Downloads\MATB\CEINNA')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $Root
$out = Join-Path $Root 'entregables'
$renders = Join-Path $Root 'revision\diapositivas'
New-Item -ItemType Directory -Force -Path $out,$renders | Out-Null
$template = Join-Path $Root 'fuentes\Plantilla_III_CEINNA.pptx'
$working = Join-Path $Root 'construccion\presentacion_trabajo.pptx'
Copy-Item -LiteralPath $template -Destination $working -Force

# Personalizar solo los metadatos de la copia; conservar intacta la plantilla.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive=[System.IO.Compression.ZipFile]::Open($working,[System.IO.Compression.ZipArchiveMode]::Update)
try {
    $entry=$archive.GetEntry('docProps/core.xml')
    $reader=[System.IO.StreamReader]::new($entry.Open())
    try {$coreText=$reader.ReadToEnd()} finally {$reader.Dispose()}
    $core=[System.Xml.XmlDocument]::new(); $core.XmlResolver=$null; $core.LoadXml($coreText)
    $ns=[System.Xml.XmlNamespaceManager]::new($core.NameTable)
    $ns.AddNamespace('dc','http://purl.org/dc/elements/1.1/')
    $ns.AddNamespace('cp','http://schemas.openxmlformats.org/package/2006/metadata/core-properties')
    $values=@{'dc:title'='Carga mental y desempeño multitarea en ASTRA: diseño longitudinal mediante MATB';'dc:creator'='SMSM DIEGO L MALPICA';'dc:subject'='III CEINNA 2026 · Subdirección Científica Aeroespacial – DIMAE';'cp:lastModifiedBy'='SMSM DIEGO L MALPICA'}
    foreach($name in $values.Keys){
        $node=$core.SelectSingleNode('//'+$name,$ns)
        if($null -eq $node){$parts=$name.Split(':'); $node=$core.CreateElement($parts[0],$parts[1],$ns.LookupNamespace($parts[0])); $null=$core.DocumentElement.AppendChild($node)}
        $node.InnerText=$values[$name]
    }
    $entry.Delete()
    $replacement=$archive.CreateEntry('docProps/core.xml')
    $writer=[System.IO.StreamWriter]::new($replacement.Open(),[System.Text.UTF8Encoding]::new($false))
    try {$writer.Write($core.OuterXml)} finally {$writer.Dispose()}
} finally {$archive.Dispose()}

function Color([string]$hex) {
    return [Convert]::ToInt32($hex.Substring(0,2),16) + 256*[Convert]::ToInt32($hex.Substring(2,2),16) + 65536*[Convert]::ToInt32($hex.Substring(4,2),16)
}
$navy=Color '000F4D'; $ink=Color '242424'; $muted=Color '4F5A6C'; $pale=Color 'EEF1F7'; $white=Color 'FFFFFF'
$script:shapeNumber=0
function Text($s,[double]$x,[double]$y,[double]$w,[double]$h,[string]$value,[double]$size=24,[bool]$bold=$false,[int]$rgb=$ink,[int]$align=1) {
    $q=$s.Shapes.AddTextbox(1,[single]$x,[single]$y,[single]$w,[single]$h)
    $script:shapeNumber++
    $q.Name='CEINNA_text_'+$script:shapeNumber
    $q.TextFrame.MarginLeft=0; $q.TextFrame.MarginRight=0; $q.TextFrame.MarginTop=0; $q.TextFrame.MarginBottom=0
    $q.TextFrame.WordWrap=-1; $q.TextFrame.AutoSize=0
    $r=$q.TextFrame.TextRange; $r.Text=$value
    $r.Font.Name='Bell MT'; $r.Font.Size=$size; $r.Font.Bold=$(if($bold){-1}else{0}); $r.Font.Color.RGB=$rgb
    $r.LanguageID=9226
    $r.ParagraphFormat.Alignment=$align; $r.ParagraphFormat.SpaceAfter=0
    $q.TextFrame.VerticalAnchor=1
    $q.TextFrame2.AutoSize=0
    $q.Left=[single]$x; $q.Top=[single]$y; $q.Width=[single]$w; $q.Height=[single]$h
    return $q
}
function Box($s,[double]$x,[double]$y,[double]$w,[double]$h,[int]$rgb=$pale) {
    $q=$s.Shapes.AddShape(1,[single]$x,[single]$y,[single]$w,[single]$h)
    $script:shapeNumber++; $q.Name='CEINNA_box_'+$script:shapeNumber
    $q.Fill.Solid(); $q.Fill.ForeColor.RGB=$rgb; $q.Line.Visible=0
    return $q
}
function Line($s,[double]$x,[double]$y,[double]$x2,[double]$y2) {
    $q=$s.Shapes.AddLine([single]$x,[single]$y,[single]$x2,[single]$y2)
    $q.Line.ForeColor.RGB=$navy; $q.Line.Weight=1.5
    return $q
}
function Picture($s,[string]$relative,[double]$x,[double]$y,[double]$w,[double]$h) {
    $path=Join-Path $Root $relative
    Add-Type -AssemblyName System.Drawing
    $img=[System.Drawing.Image]::FromFile($path)
    try { $ratio=[double]$img.Width/$img.Height } finally { $img.Dispose() }
    if($w/$h -gt $ratio){$newW=$h*$ratio; $x+=($w-$newW)/2; $w=$newW}else{$newH=$w/$ratio; $y+=($h-$newH)/2; $h=$newH}
    $q=$s.Shapes.AddPicture($path,0,-1,[single]$x,[single]$y,[single]$w,[single]$h)
    $q.AlternativeText='Recurso con procedencia en visuales/registro_activos.csv'
    return $q
}
function Clear-Content($s) {
    for($j=$s.Shapes.Count;$j -ge 1;$j--){
        $shape=$s.Shapes.Item($j)
        if($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1){
            if($shape.TextFrame.TextRange.Text -notlike '*Del conocimiento a la capacidad*'){$shape.Delete()}
        }
    }
}
function Header($s,[string]$value,[double]$size=39) {
    $null=Text $s 145 29 706 69 $value $size $true $navy 2
}
function Citation($s,[string]$value,[int]$n) {
    $null=Text $s 128 474 735 21 $value 12 $false $muted
    $null=Text $s 869 475 23 18 ([string]$n) 12 $false $muted 3
}

$map=@(1,2,3,4,4,4,4,4,4,5,4,4,6,7,7,8)
$times=@(0,20,55,50,50,65,60,55,65,65,65,55,65,10,10,0)
$titles=@('III CEINNA','Carga mental y desempeño multitarea en ASTRA','Aportes de la familia MATB','De la literatura al diseño ASTRA','ASTRA: contexto del estudio','Ocho visitas por participante','Cuatro tareas simultáneas','Estructura de una visita','Del escenario a una métrica interpretable','Resultados de desarrollo','Análisis de medidas repetidas','Marco de calificación científica','Conclusiones y recomendaciones','Bibliografía I','Bibliografía II','Cierre institucional')
$refsPath=Join-Path $Root 'construccion\referencias_slide.json'
$refs=@(); if(Test-Path $refsPath){$refs=@(Get-Content $refsPath -Raw -Encoding UTF8 | ConvertFrom-Json)}
$notesPath=Join-Path $Root 'guion\notas_data.json'
$notes=@(); if(Test-Path $notesPath){$notes=@(Get-Content $notesPath -Raw -Encoding UTF8 | ConvertFrom-Json)}
$pp=$null; $deck=$null
try {
    $pp=New-Object -ComObject PowerPoint.Application
    $pp.DisplayAlerts=1
    $deck=$pp.Presentations.Open($working,0,0,0)
    $originalIds=@(); for($i=1;$i -le 8;$i++){$originalIds+=$deck.Slides.Item($i).SlideID}
    foreach($base in $map){
        $dup=$deck.Slides.FindBySlideID($originalIds[$base-1]).Duplicate().Item(1)
        $dup.MoveTo($deck.Slides.Count)
    }
    foreach($id in $originalIds){$deck.Slides.FindBySlideID($id).Delete()}
    for($i=2;$i -le 15;$i++){Clear-Content $deck.Slides.Item($i)}

    $s=$deck.Slides.Item(2)
    $null=Text $s 157 147 685 111 "Carga mental y desempeño`nmultitarea en ASTRA" 43 $true $navy 2
    $null=Text $s 162 266 675 42 'Diseño longitudinal mediante MATB' 28 $false $navy 2
    $null=Text $s 165 338 670 32 'SMSM DIEGO L MALPICA' 25 $true $ink 2
    $null=Text $s 165 374 670 30 'Especialista en Medicina Aeroespacial' 24 $false $ink 2
    $null=Text $s 165 406 670 38 'Subdirección Científica Aeroespacial – DIMAE' 24 $false $ink 2
    Citation $s 'III CEINNA · 13–14 de octubre de 2026' 2

    $s=$deck.Slides.Item(3); Header $s 'Aportes de la familia MATB'
    $heritage=@(@('NASA MATB-II · 2011','Tareas de referencia y configuración experimental'),@('USAF AF-MATB · 2014','Generación de guiones y sincronización externa'),@('OpenMATB · 2020','Personalización, código abierto y replicabilidad'),@('USAARL MATB · 2024','Transiciones de demanda y automatización adaptativa'))
    for($k=0;$k -lt 4;$k++){
        $x=132+($k%2)*386; $y=142+[math]::Floor($k/2)*118
        $null=Box $s $x $y 363 102
        $null=Text $s ($x+15) ($y+12) 333 32 $heritage[$k][0] 25 $true $navy
        $null=Text $s ($x+15) ($y+49) 333 49 $heritage[$k][1] 21
    }
    $null=Box $s 132 390 749 70 $navy
    $null=Text $s 149 400 715 27 'Integración FAC para ASTRA' 24 $true $white
    $null=Text $s 149 430 715 25 'Escenario reproducible → registro trazable → seguimiento longitudinal' 20 $false $white
    Citation $s '[1,5] Cegarra et al., 2020; Vogl et al., 2024 (§1.2). Aportes complementarios.' 3

    $s=$deck.Slides.Item(4); Header $s 'De la literatura al diseño ASTRA' 37
    $null=Box $s 132 143 280 180
    $null=Text $s 148 149 248 70 '7 / 19' 55 $true $navy 2
    $null=Text $s 148 228 248 84 'Configuración suficiente para replicación o revisión' 20 $false $ink 2
    $null=Text $s 440 143 438 36 'Decisión metodológica' 27 $true $navy
    $null=Text $s 440 190 438 120 "Documentar parámetros y versión.`nSeparar demanda y respuesta.`nConservar contexto y secuencia." 24
    $null=Text $s 132 344 749 103 '¿Cómo varían el desempeño y la carga percibida entre condiciones de demanda y a lo largo de ASTRA?' 30 $true $navy
    Citation $s '[2] Pontiggia et al., 2024, §3. Revisión de 19 estudios; heterogeneidad sin metaanálisis.' 4

    $s=$deck.Slides.Item(5); Header $s 'ASTRA: contexto del estudio'
    $null=Text $s 130 145 335 56 'Aerospace Simulation Training Research Analogs' 23 $true $navy
    $null=Text $s 130 222 330 49 '2 misiones · 15 días' 31 $true $navy
    $null=Text $s 130 283 335 64 'Hasta 6 participantes previstos por misión' 25
    $null=Text $s 130 356 338 72 "Aislamiento y confinamiento`nEvaluación intrapersonal" 24
    $null=Picture $s 'visuales\imagegen\habitat_estacion_conceptual.png' 486 141 397 304
    $null=Text $s 487 449 394 17 'Ilustración conceptual generada con IA; no fotografía de ASTRA.' 11.5 $false $muted
    Citation $s 'Manual ASTRA v2.5 y cronograma, 11-09-2026. Diseño previsto.' 5

    $s=$deck.Slides.Item(6); Header $s 'Ocho visitas por participante'
    $null=Text $s 131 140 745 48 'Dos series longitudinales: ASTRA 1 y ASTRA 2' 26
    $null=Line $s 161 259 848 259
    $days=@('Basal','DM2','DM4','DM7','DM10','DM13','DM15','D+1')
    for($k=0;$k -lt 8;$k++){
        $x=132+$k*98
        $null=Text $s $x 205 73 35 ('V'+$k) 24 $true $navy 2
        $q=$s.Shapes.AddShape(9,[single]($x+31),[single]253,[single]12,[single]12)
        $q.Fill.ForeColor.RGB=$navy; $q.Line.Visible=0
        $null=Text $s ($x-8) 281 90 36 $days[$k] 23 $false $ink 2
    }
    $null=Text $s 132 321 741 24 'Secuencia de visitas; separación gráfica no proporcional al tiempo.' 15 $false $muted
    $null=Text $s 132 347 741 34 'V0: 29 sep. (ASTRA 1) · 28 sep. (ASTRA 2)' 23
    $null=Text $s 132 389 741 34 'V7: 20 oct. (ASTRA 1) · 5 nov. (ASTRA 2)' 23
    $null=Text $s 132 431 741 29 'Basal respecto al ingreso: D−6 y D−23, respectivamente.' 19 $false $muted
    Citation $s 'Manual §4.7.6 y cronograma §§2, 4.1 y 7. DM = día de misión. Fechas previstas.' 6

    $s=$deck.Slides.Item(7); Header $s 'Cuatro tareas simultáneas'
    $capture='visuales\capturas_tecnicas\openmatb_captura_documentacion.png'
    $captureLabel='Captura documental de OpenMATB (interfaz original en francés).'
    $runtimePath=Join-Path $Root 'visuales\capturas_tecnicas\captura_actual.json'
    if(Test-Path $runtimePath){
        $runtime=Get-Content $runtimePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $capture=$runtime.path; $captureLabel=$runtime.label
    }
    $null=Picture $s $capture 130 151 467 275
    $tasks=@(@('SYSMON','Supervisión de sistemas'),@('TRACK','Seguimiento compensatorio'),@('COMM','Comunicaciones'),@('RESMAN','Gestión de recursos'))
    for($k=0;$k -lt 4;$k++){
        $y=149+$k*74
        $null=Text $s 620 $y 265 30 $tasks[$k][0] 25 $true $navy
        $null=Text $s 620 ($y+31) 265 40 $tasks[$k][1] 20
    }
    $null=Text $s 131 440 476 29 $captureLabel 12 $false $muted
    Citation $s '[1] Cegarra et al., 2020; plugins del repositorio MATB, revisión fd5e1318.' 7

    $s=$deck.Slides.Item(8); Header $s 'Estructura de una visita'
    $null=Text $s 131 138 750 43 '90 min de reserva · 3 × 900 s de escenario' 28 $true $navy
    $levels=@('LOW','MEDIUM','HIGH')
    for($k=0;$k -lt 3;$k++){
        $x=132+$k*255
        $null=Box $s $x 202 233 104
        $null=Text $s ($x+12) 216 209 40 $levels[$k] 28 $true $navy 2
        $null=Text $s ($x+12) 260 209 31 '15 min de escenario' 22 $false $ink 2
    }
    $null=Text $s 131 316 750 33 'Tres condiciones de demanda · orden contrabalanceado' 23 $false $navy 2
    $stages=@(@('Antes de cada bloque','Somnolencia (KSS)'),@('Durante la tarea','Autoevaluación (ISA)'),@('Después del bloque',"Carga percibida`n(NASA‑TLX)"))
    for($k=0;$k -lt 3;$k++){
        $x=132+$k*255
        $null=Text $s $x 366 234 29 $stages[$k][0] 22 $true $navy
        $null=Text $s $x 404 234 53 $stages[$k][1] 21
    }
    Citation $s 'Manual §4.7; [6] Laverde-López et al., 2022. Preparación, reposo y pausas en la reserva.' 8

    $s=$deck.Slides.Item(9); Header $s 'Del escenario a una métrica interpretable' 33
    $flow=@(@('Escenario',"Parámetros`nSemilla`nOrden"),@('Registro',"Identidad`nVisita`nEventos"),@('Métricas',"Definición`nUnidades`nVersión"),@('Análisis',"Calidad`nElegibilidad`nTrazabilidad"))
    for($k=0;$k -lt 4;$k++){
        $x=132+$k*193
        $null=Box $s $x 156 170 156
        $null=Text $s ($x+12) 170 148 39 $flow[$k][0] 26 $true $navy 2
        $null=Text $s ($x+12) 218 148 89 $flow[$k][1] 22 $false $ink 2
        if($k -lt 3){$null=Text $s ($x+173) 220 25 37 '→' 24 $false $navy 2}
    }
    $null=Text $s 132 338 749 33 'Ejemplo: carga percibida con RTLX' 26 $true $navy
    $null=Text $s 132 383 749 33 '6 respuestas completas (0–10) → media × 10 → índice 0–100' 24
    $null=Text $s 132 431 749 26 'Cada resultado conserva versión, unidad, regla de cálculo y procedencia.' 21 $false $muted
    Citation $s '[1,5] Replicabilidad y registro. Ejemplo local: metrics_spec.json y log_converter.py.' 9

    $s=$deck.Slides.Item(10); Header $s 'Resultados de desarrollo'
    $null=Text $s 131 135 750 43 'Demostración técnica con datos sintéticos' 26 $true $navy
    $tableRows=@(@('Generación','Tres escenarios de 900 s: LOW, MEDIUM y HIGH.'),@('Reproducción','Archivos idénticos al repetir parámetros y semillas.'),@('Integridad y conversión','Hashes SHA-256 verificados; tres archivos CSV sintéticos convertidos.'))
    for($k=0;$k -lt 3;$k++){
        $y=200+$k*81
        $null=Box $s 131 $y 750 70 $(if($k%2 -eq 0){$pale}else{$white})
        $null=Text $s 145 ($y+7) 220 58 $tableRows[$k][0] 24 $true $navy
        $null=Text $s 380 ($y+11) 481 55 $tableRows[$k][1] 23
    }
    Citation $s 'Ejecución local: 21-09-2026 · commit fd5e1318 · evidencia/verificacion_tecnica/.' 10

    $s=$deck.Slides.Item(11); Header $s 'Análisis de medidas repetidas'
    $null=Text $s 131 143 740 41 'Unidad de seguimiento: la persona' 28 $true $navy
    $null=Box $s 131 213 442 108
    $null=Text $s 146 242 412 43 'Persona → visita → bloque' 30 $true $navy 2
    $null=Text $s 132 350 441 102 "Trayectorias individuales`nContrastes entre condiciones`nCambios entre visitas" 24
    $null=Text $s 614 211 266 36 'Contexto de medición' 25 $true $navy
    $null=Text $s 614 261 265 178 "Orden de bloques`nHora y estación`nSueño previo`nDías desde V0" 24
    Citation $s '[3,4] Pontiggia et al., 2024 (experimento); Tortello et al., 2020. Manual §4.7.' 11

    $s=$deck.Slides.Item(12); Header $s 'Marco de calificación científica' 37
    $scope=@(@('Reproducción','¿Se repite el escenario programado?'),@('Fidelidad temporal','¿Cuándo se presenta el estímulo físico?'),@('Respuesta humana','¿Cómo se relacionan demanda y respuesta?'),@('Estabilidad','¿Qué variación aparece al repetir la medición?'),@('Comparabilidad','¿Qué se conserva entre implementaciones?'))
    for($k=0;$k -lt 5;$k++){
        $y=141+$k*55
        $null=Box $s 132 $y 749 46 $(if($k%2 -eq 0){$pale}else{$white})
        $null=Text $s 145 ($y+8) 224 34 $scope[$k][0] 23 $true $navy
        $null=Text $s 387 ($y+8) 481 34 $scope[$k][1] 22
    }
    $null=Text $s 132 433 749 30 'Cada pregunta se vincula con su procedimiento y evidencia específicos.' 22 $true $navy
    Citation $s 'Marco del proyecto: resúmenes CEINNA y contratos locales; contexto metodológico [1,2,5].' 12

    $s=$deck.Slides.Item(13); Header $s 'Conclusiones y recomendaciones' 36
    $conclusions=@('Describir la demanda hace interpretable la comparación entre condiciones.','La trazabilidad vincula escenario, evento y métrica en cada visita.','ASTRA sitúa la respuesta multitarea en la trayectoria de cada persona.')
    for($k=0;$k -lt 3;$k++){
        $y=143+$k*92
        $null=Text $s 133 $y 47 42 ([string]($k+1)) 31 $true $navy
        $null=Text $s 193 $y 684 72 $conclusions[$k] 27
    }
    $null=Text $s 133 432 749 35 'Siguiente etapa: ejecución protocolizada y análisis de las visitas.' 22 $true $navy
    Citation $s 'Síntesis del diseño ASTRA y de la verificación técnica de MATB.' 13

    for($page=0;$page -lt 2;$page++){
        $s=$deck.Slides.Item(14+$page); Header $s $(if($page -eq 0){'Bibliografía I'}else{'Bibliografía II'})
        $items=@($refs | Where-Object {$_.page -eq ($page+1)})
        $idx=0
        foreach($ref in $items){
            $y=135+$idx*110
            $null=Text $s 130 $y 753 101 ('['+$ref.id+'] '+$ref.display) 18.5 $false $ink
            $idx++
        }
        Citation $s 'Autorías abreviadas en pantalla. Referencias APA completas en notas y documento adjunto.' (14+$page)
    }

    $checks=@(); $texts=@()
    for($i=1;$i -le $deck.Slides.Count;$i++){
        $s=$deck.Slides.Item($i)
        $s.Tags.Add('CEINNA_DURATION_SECONDS',[string]$times[$i-1])
        $s.Tags.Add('CEINNA_TEMPLATE_SLIDE',[string]$map[$i-1])
        $s.SlideShowTransition.AdvanceOnTime=0
        $note=@($notes | Where-Object {$_.slide -eq $i})
        $noteText="Diapositiva $i. $($titles[$i-1]). Tiempo previsto: $($times[$i-1]) segundos."
        if($note.Count -gt 0){$noteText+="`r`n`r`n"+$note[0].notes}
        if($i -eq 14 -or $i -eq 15){$noteText+="`r`n`r`n"+(($refs|Where-Object{$_.page -eq ($i-13)}|ForEach-Object{$_.full}) -join "`r`n`r`n")}
        try {$s.NotesPage.Shapes.Placeholders.Item(2).TextFrame.TextRange.Text=$noteText} catch {throw "No se pudieron insertar notas en la lámina $i : $_"}
        $slideText=@()
        foreach($shape in $s.Shapes){
            if($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1){
                $r=$shape.TextFrame.TextRange
                $slideText+=$r.Text
                if($shape.Name -like 'CEINNA_text_*'){
                    $checks+=[PSCustomObject]@{slide=$i;shape=$shape.Name;text=$r.Text;left=$shape.Left;top=$shape.Top;width=$shape.Width;height=$shape.Height;bound_height=$r.BoundHeight;font_size=$r.Font.Size;overflow=($r.BoundHeight -gt ($shape.Height+2))}
                }
            }
        }
        $texts+=[PSCustomObject]@{slide=$i;title=$titles[$i-1];seconds=$times[$i-1];template_slide=$map[$i-1];text=($slideText -join "`n");notes=$noteText}
    }
    $checks|ConvertTo-Json -Depth 6|Set-Content (Join-Path $Root 'revision\geometria_texto.json') -Encoding UTF8
    $texts|ConvertTo-Json -Depth 6|Set-Content (Join-Path $Root 'construccion\diapositivas_texto.json') -Encoding UTF8
    $final=Join-Path $out 'ASTRA_MATB_III_CEINNA_es.pptx'
    $deck.SaveAs($final,24)
    $deck.Export($renders,'PNG',1600,900)
    $deck.SaveAs((Join-Path $out 'ASTRA_MATB_III_CEINNA_es.pdf'),32)
    Write-Output ('PPTX/PDF y '+$deck.Slides.Count+' diapositivas exportadas. Tiempo previsto: '+(($times|Measure-Object -Sum).Sum)+' s.')
    Write-Output ('Cajas con posible desbordamiento: '+@($checks|Where-Object{$_.overflow}).Count)
} finally {
    if($null -ne $deck){$deck.Close()}
    if($null -ne $pp){$pp.Quit()}
}
