# ASTRA y MATB — III CEINNA 2026

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

El guion programa **11:30 de exposición**, deja **0:30 de margen** dentro del límite de 12 minutos y reserva **3:00 para preguntas**. Las notas contienen 1229 palabras de exposición. Una lectura sintética local duró 9:41 sin pausas añadidas; las 14 láminas con discurso caben individualmente en su ventana. No se realizó un ensayo humano cronometrado.

Se leyeron íntegramente los dos Markdown adjuntos y se auditó el repositorio. Scite y las fuentes primarias respaldan seis referencias de 2020–2025. La figura de hábitat creada con imagegen está identificada como ilustración conceptual; la captura de OpenMATB procede de la documentación del repositorio. Los resultados presentados son comprobaciones técnicas de generación, reproducción y conversión de archivos sintéticos. ASTRA se describe conforme a su programación; el paquete no contiene resultados humanos de las misiones.

## Evidencia y revisión

- [Conciliación documental](evidencia/conciliacion_documental.md), [contexto ASTRA](evidencia/contexto_astra.md) y [auditoría MATB](evidencia/auditoria_matb.md).
- [Matriz de afirmaciones](evidencia/matriz_afirmaciones.csv) y [búsquedas Scite](evidencia/busquedas_scite.md).
- [Revisión científica](revision/revision_cientifica.md), [bibliográfica](revision/revision_bibliografica.md) y [visual](revision/revision_visual.md).
- [Verificación final](revision/verificacion_final.json) y [correcciones](revision/registro_correcciones.md).
- [Plan implementado](PLAN_DE_PRESENTACION.md) y [encargos ejecutados](ENCARGOS_PARA_AGENTES.md).

Las tres copias de los adjuntos conservan sus SHA-256 originales, registrados en [fuentes/manifest.json](fuentes/manifest.json). La revisión final comprobó 16 páginas PDF, 16 diapositivas con notas, cero relaciones internas rotas y cero desbordamientos detectados. Se inspeccionaron visualmente todas las láminas.

## Reproducción local

Requiere Windows, PowerPoint de escritorio, Python y pdftotext. Ejecutar desde la raíz del repositorio; la exportación usa PowerPoint COM.

```powershell
& .\CEINNA\construccion\build_presentation.ps1
& .\CEINNA\construccion\ensayo_sintetico.ps1
pdftotext -layout .\CEINNA\entregables\ASTRA_MATB_III_CEINNA_es.pdf .\CEINNA\revision\texto_pdf.txt
python .\CEINNA\construccion\finalizar_paquete.py
```

La entrega Git se limita a CEINNA en el repositorio privado strikerdlm/MATB, por solicitud del investigador. No se ha enviado material al Congreso. Los audios WAV regenerables y la copia intermedia del PowerPoint se excluyen mediante .gitignore; se conservan sus informes. La ejecución no modificó el software MATB.
