# EMAVI — MATB y ASTRA

**Pública clasificada · contenido preparado; exportación FAC pendiente de aprobación gráfica.**

La clasificación fue declarada por el usuario como «Publica clasificada». El campo literal de la plantilla es **Público Clasificado**. La plantilla instalada bloquea esta rama hasta disponer de una política aprobada para su propagación y cierre. No se ha convertido el material a información pública.

## Material preparado

- **[Abrir demostración interactiva](Abrir_demostracion.cmd)**: video en español, capítulos, preguntas y estación 3D. Requiere Node.js; sirve el contenido localmente.
- **[Video MP4](entregables/EMAVI_recorrido_es.mp4)**: 7:24 aproximadamente, Full HD, 30 fps, 18 capítulos y 76 subtítulos por frase en español; voz masculina OpenAI TTS HD (`onyx`). Versión continua para proyectar después de la presentación.
- [Alcance de la grabación y verificación](video/ALCANCE_Y_VERIFICACION.md): identifica las pruebas ejecutadas, las vistas de preparación y los datos sintéticos.

- [Contenido de las diapositivas](entregables/Contenido_diapositivas.md): 17 láminas de contenido; secuencia FAC prevista de 23 láminas.
- [Demostración de la aplicación](entregables/Demostracion_app.html): siete capturas focales y enlaces a sus originales completos.
- [Notas del ponente](entregables/Notas_del_ponente_es.md): 10:45 de discurso programado; sin ensayo humano. El tiempo del evento EMAVI no fue especificado.
- [Referencias](entregables/Referencias_APA.md): seis referencias heredadas del paquete CEINNA y su verificación del 21-09-2026.
- [Política gráfica propuesta](fuentes/politica_clasificacion.md).
- [Vista previa del aviso y cierre](entregables/Propuesta_aviso_y_cierre.pdf).
- [Procedencia de las capturas](capturas/procedencia.json).

El contenido conserva la estructura científica de CEINNA: pregunta, diseño, medición, trazabilidad, análisis y siguiente etapa. Los detalles particulares del congreso CEINNA no se presentan como programación de EMAVI.

Las capturas muestran catálogo, diseñador de experimentos, vista previa de OpenMATB, KSS, mapa sUAS, inspector de evidencia y revisión de un evento. El catálogo se recapturó con la etiqueta «Pruebas»; las demás son pantallas reales del checkout `24d37b52da7196e5c69f9a8cfc9481c04fd1221d`, ejecutado localmente con una base aislada. El mapa corresponde a una sesión técnica sintética; el inspector utiliza `synthetic_capture`. No se consultaron grabaciones reales de participantes.

## Estado de verificación

- Video: decodificación completa de audio y video sin errores. El reproductor superó navegación, preguntas y reanudación, pantalla completa, vista móvil sin desbordamiento y movimiento reducido. Cero errores de consola y solicitudes externas. [Informe de entrega y hashes](revision/entrega-video.json) · [Revisión visual de los 18 capítulos](revision/storyboard-video.png).
- Modelo 3D: TypeScript estricto sin errores, geometría finita y reensamblaje exacto después de diez ciclos. Seis componentes, 104 llamadas de dibujo y 4.116 triángulos. Mediciones de Chrome automatizado; no representan una validación en todos los dispositivos.

- Compilación de producción y TypeScript del frontend completados con éxito en `.next/emavi-hd` para esta revisión.
- Siete imágenes inspeccionadas, en PNG con margen alfa transparente; originales completos conservados. El margen se añadió mediante una composición de Chromium sin cambiar píxeles, texto o valores de la captura focal.
- Exportación sintética: 11 métricas recomputadas y vínculos coincidentes. [Informe](revision/verificacion_exportacion.json). La huella de dependencias no coincide con el archivo de bloqueo; el resultado no certifica un entorno de publicación calificado.
- La [auditoría previa de texto](revision/auditoria_texto_previa.json) comprobó 33 cuadros de contenido mediante PowerPoint COM, sin desbordamientos; no reemplaza la revisión visual del PPTX final.
- El PowerPoint y PDF finales todavía **no se han generado**. La aprobación de la política está pendiente en `fuentes/aprobacion_politica.json`; los scripts mantienen ese bloqueo.

## Plantilla y construcción

`fuentes/FAC-template.pptx` es una copia intacta de la plantilla de la skill FAC-template, SHA-256 `147312eaac5e5c164b9433b072c36c104be8f8e090405539bb4e0bdbf4fc6959`.

Los scripts locales `New-FacPresentation.ps1`, `Test-FacPresentation.ps1` y `Fac-Raster.ps1` proceden de `C:/Users/User/.codex/skills/fac-template/scripts`. Los dos primeros se han preparado para la política propuesta: aviso de la lámina 4, rótulo de clasificación en contenido, reiteración del aviso y cierre intacto. La skill instalada no fue modificada. Estas adaptaciones siguen pendientes de ejecución y revisión final.

La skill enumera los modelos Sol/Terra/Luna; no están disponibles en esta sesión. La síntesis y preparación fueron realizadas por el asistente actual y la automatización local. No se invocaron ni se atribuyeron revisiones a esos modelos. Las imágenes solicitadas son capturas documentales, sin generación de imágenes ni envío a proveedores.

Una vez recibida y registrada la aprobación de la política:

```powershell
pwsh -NoProfile -File .\EMAVI\construccion\New-FacPresentation.ps1 `
  -ManifestPath .\EMAVI\fuentes\manifest.json `
  -OutputPath .\EMAVI\entregables\ASTRA_MATB_EMAVI_es.pptx `
  -RenderDirectory .\EMAVI\revision\diapositivas
pwsh -NoProfile -File .\EMAVI\construccion\Test-FacPresentation.ps1 `
  -DeckPath .\EMAVI\entregables\ASTRA_MATB_EMAVI_es.pptx `
  -ManifestPath .\EMAVI\fuentes\manifest.json
```

Después deben revisarse todas las diapositivas renderizadas, el número de páginas PDF, las notas, los avisos, la geometría y las imágenes incrustadas. No usar `-SkipDeckValidation` para la entrega.

## Reproducir la demostración

Los scripts `capture_*.js` son funciones para `playwright-cli run-code --filename` y requieren navegar primero al estado indicado. `recapture_design.js` prepara el diseñador directamente. Son recetas de captura, no una suite de pruebas de la aplicación.

El lanzador `construccion/run_demo.mjs` utiliza los puertos 8018/3118 y guarda sus datos en `construccion/runtime/`, excluido del control de versiones. En esta ejecución se utilizó un entorno local con acceso a los paquetes del entorno Conda `matb` y las versiones fijadas `fastapi==0.141.1`, `starlette==1.6.0` y `anyio==4.14.2`. No se modificó el entorno Conda compartido. Para iniciar, definir `MATB_PYTHON` con la ruta del Python preparado y ejecutar el lanzador. El frontend requiere construir previamente con `MATB_NEXT_DIST_DIR=.next/emavi-hd` y usar esa misma variable al iniciar el lanzador.

Durante la captura se observó que un intento de compilar mientras la estación estaba ocupada podía producir un error de interfaz (`compiled.manifest.spec`); recargar y compilar con la estación libre permitió obtener la captura final. No se modificó el software para esta presentación. La recuperación de la práctica KSS y el cierre de las misiones se registraron explícitamente en la base sintética.
