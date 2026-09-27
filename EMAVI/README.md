# EMAVI — MATB y ASTRA

## Edición ampliada · 27 de septiembre de 2026

La presentación ampliada contiene **40 diapositivas**, con guion programado de **29:00**. El video de 8:34 y las preguntas son independientes. La duración es estimada; no se ha realizado un ensayo humano.

El rótulo **Público Clasificado** aparece únicamente en la diapositiva 2, según la instrucción del usuario. Se conserva la clasificación del material y el aviso institucional; la política gráfica anterior queda documentada en `fuentes/historico_20260923/`.

- [PowerPoint editable ampliado](entregables/ASTRA_MATB_EMAVI_es_ampliada.pptx).
- [PDF nativo ampliado](entregables/ASTRA_MATB_EMAVI_es_ampliada.pdf).
- [Contenido de las diapositivas](entregables/Contenido_diapositivas.md) y [notas del ponente](entregables/Notas_del_ponente_es.md).
- [Revisión crítica del corpus](entregables/Revision_evidencia_MATB_ASTRA.md) y [24 referencias numeradas](entregables/Referencias_APA.md).
- [Verificación del archivo exportado](revision/verificacion_ampliada.json) y [revisión visual](revision/revision_ampliada.md).

## Contenido científico

Las diapositivas 6–15 explican las tareas MATB, su evolución, la comparación entre NASA MATB/MATB-II, AF_MATB, OpenMATB, USAARL y MATB-FAC, las aplicaciones de NASA, USAF y US Army y la evidencia de sensibilidad, memoria prospectiva, interfaces y medición multimodal. La tabla comparativa es nativa y editable. Se distingue documentación técnica, resultados de estudios específicos y aspectos que requieren validación local.

Las diapositivas 16–23 desarrollan ASTRA: fundamentos NASA, hábitat terrestre, tripulación y MCC, calendario previsto, jornada y EVA simuladas, medición multimodal, ocho visitas MATB y análisis longitudinal. Se prioriza el manual v2.6 del 25 de septiembre. Las fechas corresponden a planificación, no a misiones o resultados ya realizados.

Las siete capturas de la aplicación ocupan las diapositivas 24–30. Las diapositivas 31–36 presentan aplicaciones locales en aviación convencional, UAS y otros dominios, una ruta de desarrollo y el estado de preparación. Se explicita la diferencia entre las ocho visitas del manual y los tres hitos del perfil actual del software; esta ampliación no modifica el protocolo de la aplicación.

La revisión incluye 16 documentos MATB, seis PDF NASA, ocho documentos operativos y cinco registros externos de contraste. Las síntesis narrativas y duplicados se identifican para evitar contarlos como evidencia primaria adicional. El [registro de fuentes](fuentes/registro_fuentes.json) conserva ubicaciones, hashes y localizadores; la [matriz de afirmaciones](fuentes/matriz_afirmaciones.json) vincula el contenido con sus fuentes. Es una revisión narrativa estructurada del corpus solicitado, no una revisión sistemática exhaustiva ni un metaanálisis.

## Ilustraciones y material documental

Se incorporan seis ilustraciones conceptuales de estilo didáctico: cuatro tareas MATB, hábitat, tripulación y MCC, EVA terrestre, medición y sueño, y aviación convencional/UAS. Fueron creadas con la herramienta integrada imagegen. [Prompts, revisión y límites](visuales/AMPLIACION_IMAGEGEN.md) · [procedencia y hashes](assets/fac-visuals/procedencia.json).

Las imágenes no son fotografías de participantes, planos verificados ni resultados experimentales. Se conserva el alfa de los PNG originales y su inclusión sin recorte. La primera variante de medición no está seleccionada; la versión corregida muestra el cinturón torácico en contacto con la piel.

Las siete capturas de la aplicación conservan sus archivos y [procedencia original](capturas/procedencia.json). Muestran catálogo, diseñador, OpenMATB, KSS, sUAS, inspector de evidencia y revisión de un evento. El mapa utiliza una sesión técnica sintética y el inspector utiliza `synthetic_capture`; no se consultaron registros reales de participantes.

## Demostración y edición anterior

- [Abrir demostración interactiva](Abrir_demostracion.cmd): video en español, capítulos, preguntas y estación 3D; requiere Node.js.
- [Video MP4](entregables/EMAVI_recorrido_es.mp4): 8:34 aproximadamente, Full HD, 30 fps, 18 capítulos.
- [Demostración de la aplicación](entregables/Demostracion_app.html).
- [Alcance y verificación previa del video](video/ALCANCE_Y_VERIFICACION.md) y [registro de entrega](revision/entrega-video.json).
- Edición anterior del 23 de septiembre, conservada: [PPTX de 24 diapositivas](entregables/ASTRA_MATB_EMAVI_es.pptx) y [PDF](entregables/ASTRA_MATB_EMAVI_es.pdf).

La ampliación conserva la edición anterior, las capturas, el video, el póster y el funcionamiento de la aplicación. Las verificaciones previas de esos materiales no se presentan como pruebas nuevas. La recomputación sintética anterior de once métricas conserva la limitación sobre la huella de dependencias descrita en su [informe](revision/verificacion_exportacion.json).

## Construcción y comprobación

`fuentes/FAC-template.pptx` permanece intacta, con SHA-256 `147312eaac5e5c164b9433b072c36c104be8f8e090405539bb4e0bdbf4fc6959`. Se mantienen apertura, cierre, marcas, fondos y líneas institucionales. Los scripts locales adaptan el aviso inicial único y añaden tablas editables dentro del área libre; la skill instalada no se modifica. La [política gráfica](fuentes/politica_clasificacion.md) y su [registro de aprobación](fuentes/aprobacion_politica.json) documentan la instrucción del usuario.

```powershell
python .\EMAVI\construccion\preparar_ampliacion.py
python .\EMAVI\construccion\revisar_fuentes.py
pwsh -NoProfile -File .\EMAVI\construccion\Confirmar-Ilustraciones.ps1
pwsh -NoProfile -File .\EMAVI\construccion\New-FacPresentation.ps1 `
  -ManifestPath .\EMAVI\fuentes\manifest.json `
  -OutputPath .\EMAVI\entregables\ASTRA_MATB_EMAVI_es_ampliada.pptx `
  -RenderDirectory .\EMAVI\revision\diapositivas_ampliada
python .\EMAVI\construccion\verificar_ampliacion.py
```

La exportación requiere Windows, PowerPoint de escritorio y fuentes Arial/Times New Roman. La revisión bibliográfica usa los directorios locales solicitados; la comprobación del PDF usa Poppler. El generador ejecuta el validador nativo de geometría, tipografía, tablas e imágenes. Después se revisan visualmente las 40 diapositivas. Los programas cierran únicamente las presentaciones que abren para construir o validar.

## Reproducir la demostración

Los scripts `capture_*.js` son funciones para `playwright-cli run-code --filename` y requieren navegar primero al estado indicado. `recapture_design.js` prepara el diseñador directamente. Son recetas de captura, no una suite de pruebas de la aplicación.

El lanzador `construccion/run_demo.mjs` utiliza los puertos 8018/3118 y guarda sus datos en `construccion/runtime/`, excluido del control de versiones. La edición anterior utilizó un entorno local con acceso a los paquetes Conda `matb` y las versiones fijadas `fastapi==0.141.1`, `starlette==1.6.0` y `anyio==4.14.2`. Para iniciar, definir `MATB_PYTHON` con la ruta del Python preparado y ejecutar el lanzador. El frontend requiere construir previamente con `MATB_NEXT_DIST_DIR=.next/emavi-hd` y usar esa misma variable al iniciar el lanzador.

Durante aquella captura, compilar con la estación ocupada produjo un error de interfaz (`compiled.manifest.spec`); recargar y compilar con la estación libre permitió obtener la captura final. La recuperación de la práctica KSS y el cierre de las misiones se registraron en la base sintética. No se modifica el software para esta ampliación.
