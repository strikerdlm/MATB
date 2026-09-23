# ASTRA y MATB — III CEINNA 2026

## Edición visual · 23 de septiembre de 2026

- [PowerPoint visual editable, 17 láminas](entregables/ASTRA_MATB_III_CEINNA_es_visual.pptx): ilustraciones conceptuales en las láminas 5, 8 y 9; la captura documental de OpenMATB permanece en la 7.
- [Vista previa PDF de 17 páginas](entregables/ASTRA_MATB_III_CEINNA_es_visual_preview.pdf): raster de revisión; la exportación PDF nativa de PowerPoint sigue pendiente de ejecutarse en Windows.
- [Notas de la edición visual](entregables/Notas_del_ponente_visual_es.md), [mapa](guion/mapa_diapositivas_visual.csv), [procedencia de activos](visuales/registro_activos_visual.csv) y [prompts](visuales/PROMPTS_IMAGEGEN_2026-09-23.md).

La nueva lámina distingue la adquisición fisiológica del protocolo MATB. Polar H10 puede aportar R–R cuando se verifica la ruta; ActiGraph registra movimiento; HRV es derivada y depende de calidad. Las imágenes no representan participantes, señales ni resultados de misión. La exposición visual suma 720 segundos previstos. La documentación y el PDF sin sufijo `_visual` conservan el paquete original de 16 láminas.

**Presentación terminada y revisada · 21 de septiembre de 2026 · Español.**

SMSM DIEGO L MALPICA  
Especialista en Medicina Aeroespacial  
Subdirección Científica Aeroespacial – DIMAE

## Entregables

- [Presentación editable PowerPoint](entregables/ASTRA_MATB_III_CEINNA_es.pptx)
- [Presentación PDF](entregables/ASTRA_MATB_III_CEINNA_es.pdf)
- [Notas del ponente](entregables/Notas_del_ponente_es.md)
- [Preguntas y respuestas del comité](entregables/Preguntas_y_respuestas_del_comite.md)
- [Referencias APA](entregables/Referencias_APA.md) y [glosario](entregables/Glosario.md)
- [Informe de verificación](entregables/Informe_de_verificacion.md)

La presentación contiene 16 diapositivas, incluidas las láminas institucionales de apertura y cierre. Conserva la plantilla suministrada, su formato 16:9, tipografía Bell MT, emblemas, franja y lema. El contenido desarrolla la pregunta, el diseño longitudinal, las mediciones, la trazabilidad, los resultados técnicos y la interpretación científica.

El guion programa **11:30 de exposición**, deja **0:30 de margen** dentro del límite de 12 minutos y reserva **3:00 para preguntas**. Las notas contienen 1270 palabras de exposición. Una lectura sintética local duró 10:00 aproximadamente sin pausas añadidas; las 14 láminas con discurso caben individualmente en su ventana. No se realizó un ensayo humano cronometrado.

Se leyeron íntegramente el manual, el cronograma y los dos resúmenes aportados, y se auditó el repositorio. Scite y las fuentes primarias respaldan seis referencias de 2020–2025. La figura de hábitat creada con imagegen está identificada como ilustración conceptual; la captura de OpenMATB procede de la documentación del repositorio. Los resultados presentados son comprobaciones técnicas de generación, reproducción y conversión de archivos sintéticos. ASTRA se describe conforme a su programación; el paquete no contiene resultados humanos de las misiones.

## Evidencia y revisión

- [Conciliación documental](evidencia/conciliacion_documental.md), [contexto ASTRA](evidencia/contexto_astra.md) y [auditoría MATB](evidencia/auditoria_matb.md).
- [Matriz de afirmaciones](evidencia/matriz_afirmaciones.csv) y [búsquedas Scite](evidencia/busquedas_scite.md).
- [Revisión científica](revision/revision_cientifica.md), [bibliográfica](revision/revision_bibliografica.md) y [visual](revision/revision_visual.md).
- [Verificación final](revision/verificacion_final.json) y [correcciones](revision/registro_correcciones.md).
- [Plan implementado](PLAN_DE_PRESENTACION.md) y [encargos ejecutados](ENCARGOS_PARA_AGENTES.md).

Las cinco copias de los adjuntos conservan sus SHA-256 originales, registrados en [fuentes/manifest.json](fuentes/manifest.json). La revisión final comprobó 16 páginas PDF, 16 diapositivas con notas, cero relaciones internas rotas y cero desbordamientos detectados. Se inspeccionaron visualmente todas las láminas.

## Reproducción local

Requiere Windows, PowerPoint de escritorio, Python y pdftotext. Ejecutar desde la raíz del repositorio; la exportación usa PowerPoint COM.

```powershell
& .\CEINNA\construccion\build_presentation.ps1
& .\CEINNA\construccion\ensayo_sintetico.ps1
pdftotext -layout .\CEINNA\entregables\ASTRA_MATB_III_CEINNA_es.pdf .\CEINNA\revision\texto_pdf.txt
python .\CEINNA\construccion\finalizar_paquete.py
```

La entrega Git se limita a CEINNA en el repositorio privado strikerdlm/MATB, por solicitud del investigador. No se ha enviado material al Congreso. Los audios WAV regenerables y la copia intermedia del PowerPoint se excluyen mediante .gitignore; se conservan sus informes. La ejecución no modificó el software MATB.

## Ampliación científica con los nuevos documentos

Se incorporaron los dos resúmenes aportados y una nueva lectura de Cegarra (2020), Pontiggia (2024, revisión) y Vogl (2024). La secuencia ahora conecta los aportes de las implementaciones MATB, el hallazgo de siete de diecinueve configuraciones suficientemente descritas, un ejemplo de RTLX y las preguntas del marco de calificación. Las conclusiones articulan demanda, trazabilidad y trayectoria individual. Se preservan seis referencias, 16 láminas y 690 segundos.

La lectura completa de los tres artículos centrales se verificó mediante Scite. NASA NTRS aportó metadatos y DTIC no devolvió texto legible; la caracterización histórica NASA/AF se atribuye a Vogl. No se trasladaron conteos históricos de pruebas como resultados actuales. Las copias de los cinco adjuntos conservan sus SHA-256 originales.

Consultar [lectura y decisiones](evidencia/lectura_comparativa_y_aportes.md), [revisión científica ampliada](revision/revision_ampliacion_cientifica.md) y [revisión visual ampliada](revision/revision_visual_ampliada.md). La última lectura sintética duró 599,81 segundos; no constituye ensayo humano.
