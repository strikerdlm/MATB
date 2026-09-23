[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root='E:\Downloads\MATB'
$out=Join-Path $root 'EMAVI\poster'
$review=Join-Path $out 'revision_actualizacion'
$source=Join-Path $out 'EMAVI_2026_poster_Malpica.pptx'
$target=Join-Path $out 'EMAVI_2026_poster_Malpica_actualizado.pptx'
$before=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
$navy=0x542000; $blue=0xA8692E; $ink=0x302B25; $muted=0x655D53
$pale=0xF7F1EA; $white=0xFFFFFF; $edge=0xB5B5B5; $amber=0xD6EEFF
function Pt([double]$cm) { return [single]($cm*72/2.54) }
function Box($name,$x,$y,$w,$h,$fill,$border=$null,$round=$false) {
    $kind=1; if($round){$kind=5}
    $s=$slide.Shapes.AddShape($kind,(Pt $x),(Pt $y),(Pt $w),(Pt $h)); $s.Name=$name
    $s.Fill.Solid(); $s.Fill.ForeColor.RGB=$fill
    $s.Shadow.Visible=0
    if($round){$s.Adjustments.Item(1)=0.08}
    if($null -eq $border){$s.Line.Visible=0}else{$s.Line.ForeColor.RGB=$border;$s.Line.Weight=1.4}
    return $s
}
function Txt($name,$text,$x,$y,$w,$h,$size=26,$bold=$false,$color=$ink,$align=1) {
    $s=$slide.Shapes.AddTextbox(1,(Pt $x),(Pt $y),(Pt $w),(Pt $h));$s.Name=$name
    $s.TextFrame.AutoSize=0;$s.TextFrame.WordWrap=-1
    $s.TextFrame.MarginLeft=4;$s.TextFrame.MarginRight=4;$s.TextFrame.MarginTop=0;$s.TextFrame.MarginBottom=0
    $s.TextFrame2.AutoSize=0
    $r=$s.TextFrame.TextRange;$r.Text=$text;$r.Font.Name='Arial';$r.Font.Size=$size
    $r.Font.Bold=$(if($bold){-1}else{0});$r.Font.Color.RGB=$color
    $r.ParagraphFormat.Alignment=$align;$r.ParagraphFormat.SpaceAfter=4
    return $s
}
function Section($name,$label,$x,$y,$w,$h,$tabwidth) {
    $null=Box "$name-frame" $x $y $w $h $white $edge $true
    $null=Box "$name-tab" ($x+1.1) ($y-0.6) $tabwidth 2.2 $navy 0x64804B $true
    $null=Txt "$name-heading" $label ($x+1.45) ($y-0.38) ($tabwidth-0.7) 1.5 36 $true $white 2
}
$app=New-Object -ComObject PowerPoint.Application
$deck=$null
try {
    $deck=$app.Presentations.Open($source,-1,0,0)
    $slide=$deck.Slides.Item(1)
    # Preserve the original event artwork as a cropped header. All scientific content is native/editable.
    for($i=$slide.Shapes.Count;$i -ge 1;$i--){if($slide.Shapes.Item($i).Id -ne 2){$slide.Shapes.Item($i).Delete()}}
    $banner=$slide.Shapes.Item(1);$banner.Name='Banner institucional original'
    $banner.LockAspectRatio=0
    $banner.PictureFormat.CropBottom=[single]($banner.Height*(1-14.8/120))
    $banner.Left=0;$banner.Top=0;$banner.Width=Pt 80;$banner.Height=Pt 14.8
    $null=Box 'Fondo blanco' 0 14.8 80 105.2 $white
    $null=Txt 'Titulo' "MATB-FAC: PLATAFORMA DE INVESTIGACIÓN`rDEL DESEMPEÑO HUMANO Y LA CARGA MENTAL" 5 17 70 4 43 $true $ink 2
    $null=Txt 'Autor' 'Diego Leonel Malpica Hincapié' 8 21.4 64 1.4 31 $false $ink 2
    $null=Txt 'Contacto' 'diego.malpica@fac.mil.co  ·  ORCID: 0000-0002-2257-4940' 8 22.8 64 1.2 25 $false $ink 2
    $null=Txt 'Afiliacion' 'Fuerza Aeroespacial Colombiana · Dirección de Medicina Aeroespacial · Bogotá, Colombia' 5 24.1 70 1.2 24 $false $ink 2
    Section 'Resumen' 'RESUMEN' 5 29 70 10.3 15
    $abstract="Resumen. Se revisaron la implementación y los artefactos técnicos de MATB-FAC. La plataforma reúne tareas OpenMATB, carga percibida, simulación y adquisición fisiológica experimental con trazabilidad por evento. Una verificación sintética documenta 11 métricas recomputadas; la calificación del entorno y la validación humana permanecen pendientes.`rAbstract. MATB-FAC combines multitask performance, perceived workload, simulation and experimental physiology with event-level provenance. A documented synthetic verification recomputed 11 metrics; environment qualification and human validation remain pending.`rPalabras clave / Keywords: carga mental / mental workload; desempeño humano / human performance; simulación / simulation.`rMATB: batería multitarea de atributos múltiples. FAC: Fuerza Aeroespacial Colombiana."
    $null=Txt 'Resumen bilingue' $abstract 6.2 31 67.6 7.9 24
    Section 'Introduccion' 'INTRODUCCIÓN' 5.5 41 34 22 17
    $null=Txt 'Introduccion texto' 'El estudio de la multitarea exige documentar la demanda programada y separar desempeño, carga percibida y fisiología. OpenMATB permite configurar tareas reproducibles [1]; la diversidad de configuraciones limita las comparaciones entre estudios [2,3]. Objetivo: describir las capacidades actuales y el alcance de su evidencia técnica.' 6.7 43.1 31.6 8.1 27
    $domains=@(@('DESEMPEÑO','respuestas y control'),@('CARGA PERCIBIDA','autoinforme'),@('FISIOLOGÍA','contexto descriptivo'))
    for($i=0;$i -lt 3;$i++){
        $x=6.8+$i*10.5
        $null=Box "Dominio-$i" $x 52.9 9.7 5.5 $pale $blue $true
        $null=Txt "Dominio-titulo-$i" $domains[$i][0] ($x+0.4) 53.7 8.9 1.8 23 $true $navy 2
        $null=Txt "Dominio-detalle-$i" $domains[$i][1] ($x+0.4) 56 8.9 1.3 22 $false $ink 2
    }
    $null=Txt 'Separacion de constructos' 'Dominios relacionados, analizados por separado.' 7 60 31 1.7 25 $true $navy 2
    Section 'Metodologia' 'METODOLOGÍA' 41 41 34 27 17
    $null=Txt 'Metodologia texto' 'Revisión técnica del código, contratos de medición y artefactos de verificación [4]. Se distinguen capacidades implementadas, comprobaciones sintéticas y validación pendiente. Esta revisión no incorpora datos de participantes.' 42.2 43.1 31.6 5.7 26
    $steps=@(@('ESCENARIO','Tareas, eventos, duración y semilla'),@('CAPTURA','Práctica o estudio; eventos y manifiesto'),@('CALIDAD','Integridad, procedencia y exclusiones'),@('MÉTRICAS','Definición versionada y enlace al evento'),@('ANÁLISIS LONGITUDINAL','Persona, visita, bloque y condición'))
    for($i=0;$i -lt 5;$i++){
        $y=49.7+$i*3.4
        $null=Box "Paso-$i" 43 $y 30 2.9 $(if($i%2 -eq 0){$pale}else{$white}) $edge $true
        $null=Txt "Paso-numero-$i" ([string]($i+1)) 43.5 ($y+0.35) 2 1.8 32 $true $blue 2
        $null=Txt "Paso-titulo-$i" $steps[$i][0] 46 ($y+0.25) 26 1 24 $true $navy
        $null=Txt "Paso-texto-$i" $steps[$i][1] 46 ($y+1.45) 26 1 23
        if($i -lt 4){$line=$slide.Shapes.AddLine((Pt 58),(Pt ($y+2.92)),(Pt 58),(Pt ($y+3.38)));$line.Name="Paso-flecha-$i";$line.Line.ForeColor.RGB=$blue;$line.Line.EndArrowheadStyle=3;$line.Line.Weight=2}
    }
    Section 'Resultados' 'RESULTADOS' 5.5 66.6 34 24 15
    $null=Txt 'Resultados tipo' 'CAPACIDADES IMPLEMENTADAS [4]' 7 69 31 1.1 25 $true $navy
    $null=Txt 'Capacidades' "OpenMATB: vigilancia, seguimiento, comunicaciones y gestión de recursos; escenarios y métricas versionadas.`rConsola: práctica/estudio, evidencia por evento y seguimiento entre visitas.`rMódulos opcionales: supervisión sUAS sintética, simulación FPV y adquisición Polar H10 experimental." 7 71 31 9.6 26
    $null=Box 'Evidencia sintetica panel' 7 81.2 31 7.9 $pale $edge $true
    $null=Txt 'Once' '11' 8 82 5.7 3 64 $true $blue 2
    $null=Txt 'Once descripcion' "MÉTRICAS RECOMPUTADAS`rValores y enlaces coincidentes`ren un paquete sintético [5]." 15 82 22 3.8 25 $true $navy
    $null=Txt 'Limitacion entorno' "Informe revisado: 23-09-2026. Dependencias sin`rcoincidencia con el archivo de bloqueo;`rentorno de publicación aún no calificado." 8 85.7 29 3.3 23 $false $ink
    Section 'Discusion' 'DISCUSIÓN' 41 71.2 34 33.6 18
    $null=Txt 'Discusion texto' 'La trazabilidad permite revisar cómo se obtuvo cada métrica. La disponibilidad de software y la recomputación sintética no establecen por sí solas validez de medición en personas [4,5].' 42.5 73.6 31 5.6 27
    $null=Txt 'Discusion pregunta' 'ALCANCE DE LA EVIDENCIA ACTUAL' 43 80.1 30 1.4 27 $true $navy 2
    $levels=@(@('VERIFICACIÓN DE SOFTWARE','Evidencia técnica y sintética documentada', $navy,$white),@('TIEMPO FÍSICO','Calificación pendiente en el equipo utilizado',$pale,$ink),@('CALIBRACIÓN HUMANA','Demanda experimental pendiente de calibración',$pale,$ink),@('CONFIABILIDAD Y VALIDEZ','Evaluación con participantes pendiente',$pale,$ink),@('TRANSFERENCIA EXTERNA','Sin evidencia de transferencia operacional',$pale,$ink))
    for($i=0;$i -lt 5;$i++){
        $y=82.5+$i*3.7
        $null=Box "Nivel-$i" 43 $y 30 3.1 $levels[$i][2] $edge $false
        $null=Txt "Nivel-titulo-$i" $levels[$i][0] 43.7 ($y+0.35) 28.6 1.2 25 $true $levels[$i][3]
        $null=Txt "Nivel-texto-$i" $levels[$i][1] 43.7 ($y+1.65) 28.6 1.1 22 $false $levels[$i][3]
    }
    $null=Txt 'Limite inferencial' 'Uso de investigación; sin diagnóstico ni calificación de aptitud.' 43 102 30 1.7 24 $true $navy 2
    Section 'Conclusiones' 'CONCLUSIONES' 5.5 93.5 34 11.3 18
    $null=Txt 'Conclusiones texto' "La contribución es vincular configuración, evento, calidad y métrica en un flujo auditable.`rEl seguimiento longitudinal conserva separados desempeño, carga percibida y fisiología.`rLa siguiente etapa requiere calificar el equipo y evaluar calibración, confiabilidad y validez con participantes." 7 96 31 7.8 27
    Section 'Referencias' 'REFERENCIAS' 5.5 108.4 69.5 8.7 15
    $refs="[1] Cegarra J. et al. OpenMATB. Behav Res Methods. 2020;52:1980–1990. doi:10.3758/s13428-020-01364-w.`r[2] Pontiggia A. et al. MATB for assessing different mental workload levels. Front Physiol. 2024;15:1408242. doi:10.3389/fphys.2024.1408242.`r[3] Vogl J. et al. The USAARL Multi-Attribute Task Battery. Front Neuroergon. 2024;5:1435588. doi:10.3389/fnrgo.2024.1435588.`r[4] MATB-FAC. Código y documentación técnica. Revisión e7173321ac85, 23-09-2026.`r[5] MATB-FAC. Verificación sintética de exportación EMAVI. Código de origen 24d37b52da71; informe revisado el 23-09-2026."
    $null=Txt 'Referencias texto' $refs 6.5 110.4 67.5 5.5 21
    $null=Txt 'Siglas adicionales' 'sUAS: sistema de aeronave pequeña no tripulada. FPV: visión en primera persona. Fuentes y límites: auditoría adjunta.' 6.5 116 67.5 0.9 20 $false $muted
    foreach($shape in $slide.NotesPage.Shapes){if($shape.HasTextFrame -and $shape.TextFrame.HasText){$shape.TextFrame.TextRange.Text=''}}
    $notes="Actualización del 23-09-2026. Fuentes locales: README.es.md; matb_integration/evidence/reconcile.py; docs/research/qualification-workflow.md; docs/physiology/polar-h10-release-a.md; EMAVI/revision/verificacion_exportacion.json. Referencia [5]: verificación histórica, no una nueva ejecución. Consulte AUDITORIA_POSTER_ACTUALIZADO.md. La duración y el número de visitas dependen del protocolo; existen discrepancias entre la presentación ASTRA y el protocolo del software. No se importaron capturas ni contenido clasificado de la presentación. El banner institucional procede del póster original. No se efectuó revisión jurídica de difusión."
    $slide.NotesPage.Shapes.Placeholders.Item(2).TextFrame.TextRange.Text=$notes
    $deck.SaveAs($target,24)
    $deck.Close();$deck=$null
    # PowerPoint's document-property COM binding fails on this host. Edit only core metadata in the saved copy.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip=[IO.Compression.ZipFile]::Open($target,[IO.Compression.ZipArchiveMode]::Update)
    try {
        $entry=$zip.GetEntry('docProps/core.xml')
        $reader=[IO.StreamReader]::new($entry.Open());$xml=[xml]$reader.ReadToEnd();$reader.Dispose()
        $metadata=@{
            title='MATB-FAC: plataforma de investigación del desempeño humano y la carga mental'
            subject='Póster científico EMAVI 2026: capacidades implementadas y alcance de la evidencia técnica'
            keywords='MATB-FAC, OpenMATB, carga mental, desempeño humano, trazabilidad, simulación'
            description='Actualizado el 23-09-2026. Evidencia sintética histórica diferenciada de la validación humana pendiente. Véase la auditoría adjunta.'
        }
        foreach($key in $metadata.Keys){
            $node=$xml.SelectSingleNode("//*[local-name()='$key']")
            if($null -ne $node){$node.InnerText=$metadata[$key]}
        }
        $entry.Delete();$entry=$zip.CreateEntry('docProps/core.xml')
        $stream=$entry.Open();$xml.Save($stream);$stream.Dispose()
    } finally {$zip.Dispose()}
    $deck=$app.Presentations.Open($target,-1,0,0);$slide=$deck.Slides.Item(1)
    $deck.SaveAs([IO.Path]::ChangeExtension($target,'.pdf'),32)
    $slide.Export((Join-Path $review 'poster_actualizado.png'),'PNG',2000,3000)
    $checks=@()
    foreach($s in $slide.Shapes){
        if($s.HasTextFrame -and $s.TextFrame.HasText){
            $r=$s.TextFrame.TextRange
            $checks += [pscustomobject]@{name=$s.Name; font_pt=$r.Font.Size; width=$s.Width;height=$s.Height;bound_width=$r.BoundWidth;bound_height=$r.BoundHeight;overflow=($r.BoundWidth -gt $s.Width+1 -or $r.BoundHeight -gt $s.Height+1)}
        }
    }
    [pscustomobject]@{source_sha256=$before;source_unchanged=($before -eq (Get-FileHash -LiteralPath $source).Hash);slides=$deck.Slides.Count;width_cm=$deck.PageSetup.SlideWidth*2.54/72;height_cm=$deck.PageSetup.SlideHeight*2.54/72;text_checks=$checks} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $review 'verificacion_powerpoint.json') -Encoding utf8
    $checks | Where-Object overflow | Format-Table
} finally {
    if($null -ne $deck){$deck.Close()}
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
}
