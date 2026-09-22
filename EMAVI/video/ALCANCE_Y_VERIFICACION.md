# Demostración EMAVI — alcance y procedencia

**Público Clasificado. Reproducción local; distribución en el repositorio privado MATB.** Narración generada con **OpenAI `gpt-4o-mini-tts-2025-12-15`, voz `cedar`, velocidad 1.0**, seleccionada por el usuario después de escuchar las muestras Cedar y Ash. Se enviaron únicamente las frases del guion al servicio de voz; la clave se cargó de `.env.local` en memoria y no se incluyó en los entregables. El reproductor funciona sin conexión una vez descargados los archivos.

## Qué se entrega

- `../entregables/EMAVI_recorrido_es.mp4`: montaje continuo, 1920 × 1080, 30 cuadros/s, H.264/AAC, subtítulos en español y capítulos incrustados.
- `../entregables/Demostracion_interactiva.html`: el mismo video con navegación, repetición, cuatro comprobaciones de comprensión y una estación 3D manipulable. El MP4 es lineal; las interacciones pertenecen a este reproductor.
- `guion.json`, `chapters.json`, `subtitulos.vtt`, `subtitulos.srt`, `audio/`: guion, tiempos, subtítulos y narración. Los límites de las frases proceden de la duración de los WAV; se añade el mismo desplazamiento de 350 ms al audio y al texto.

Los subtítulos usan los límites medidos de 76 frases de audio independientes y pausas de 180 ms entre frases. El montaje añade 350 ms antes de cada capítulo. Los WAV transmitidos por la API pueden tener un tamaño de cabecera indeterminado; se cuentan las muestras PCM realmente recibidas. `../revision/subtitulos.json` comprueba los intervalos sin solapamiento y `../revision/narracion-hd.json` identifica el modelo, la voz y los hashes. No se reutilizan las marcas de Windows Speech de la versión anterior.

- `scene.ts` y `scene.js`: fuente editable y módulo de la escena. `vendor/` contiene Three.js 0.186.0, OrbitControls de la misma versión y su licencia MIT.

Abra **`../Abrir_demostracion.cmd`** en Windows. Necesita Node.js y un navegador con soporte MP4. El lanzador sirve únicamente la carpeta EMAVI en `127.0.0.1:3128`. No necesita la aplicación MATB ni conexión a Internet para reproducir el material. Para iniciarlo manualmente desde la raíz del repositorio:

```powershell
node EMAVI/construccion/serve_video.mjs
```

Después abra `http://127.0.0.1:3128/`. El servidor local permite cargar módulos 3D y subtítulos sin las restricciones de `file://`. El MP4 también puede abrirse directamente en un reproductor.

Para proyectar con preguntas, use **Pantalla completa** en la barra de la demostración. El modo nativo de pantalla completa del video reproduce el recorrido sin las pausas HTML; al salir se restaura la opción de interacción.

## Lo ejecutado y lo mostrado

| Familia / función | Alcance de la grabación |
|---|---|
| KSS y PVT | Recorrido real de práctica: identificación, ocasión, KSS, instrucciones, un minuto de PVT, respuestas visibles automatizadas y confirmación de guardado. Los tiempos mostrados no describen a una persona. |
| Pruebas | Las cuatro tareas en modo de familiarización abreviado: reacción simple, elección, 2-back y seguimiento; práctica previa y guardado final. Respuestas automatizadas a los estímulos visibles. |
| sUAS | Práctica, LOW, MEDIUM y HIGH, preguntas ISA/SAGAT, escalas posteriores, finalización explícita e informe. Se utilizó `e2e_area_search`, escenario técnico corto del repositorio, en una base aislada. |
| Contexto sUAS | El código P18 y su asignación son ficticios. Los prerrequisitos de estudio se prepararon con el helper de aceptación del repositorio, incluyendo un PVT sintético; no corresponden al minuto de práctica P02 mostrado en el capítulo PVT. La grabación explica esa diferencia y no presenta una visita humana real. |
| OpenMATB | Vista previa web y configuración. No se grabó una adquisición nativa ni se ejecutó el perfil estándar de tres bloques de 15 minutos. |
| Liftoff | Preparación y explicación del flujo basal → vuelo → recuperación. No se conectó el simulador ni se produjo telemetría nueva. |
| Polar H10 | Preparación y requisitos de calidad. No se conectó un sensor ni se adquirieron señales humanas. |
| Investigador | Catálogo, asignaciones, participantes, estudio, diseñador, configuración y páginas de análisis. El video explica que la secuencia efectiva depende del protocolo asignado. |
| Evidencia | Importación real de `synthetic_capture`, selección de una métrica y apertura del evento original. La exportación anterior recomputó 11 métricas; su huella de dependencias no coincidió con el lockfile. Véase `../revision/verificacion_exportacion.json`. |

Las capturas originales proceden del checkout `24d37b52da7196e5c69f9a8cfc9481c04fd1221d`. Las tomas del catálogo y de Pruebas se renovaron desde `e105a67` con el cambio de etiquetas de esta revisión; se conserva el parche de las fuentes en `../revision/frontend-capturado.patch`. Los scripts no modifican la aplicación ni inyectan resultados en sus pantallas. Los datos y la asignación de la misión son fixtures explícitos de una base de demostración. Los clips se recortan, se aceleran cuando exceden la narración y conservan la última imagen cuando el texto dura más. No se altera el texto o los valores visibles. La introducción y el cierre son esquemas ilustrativos, no capturas de MATB.

El capítulo de evidencia incorpora, después del noveno segundo, la captura documental `../capturas/07_evento_detalle.png` para hacer legibles el evento original y sus tiempos. Su procedencia está conservada en `../capturas/procedencia.json`.

Durante las explicaciones de catálogo, asignaciones, configuración, KSS y equipo se mantiene una captura documental de esa misma pantalla después de la transición inicial. El capítulo de supervisión pasa a `../capturas/05_suas_detalle.png` después del octavo segundo para enfocar el mapa. Estas pausas de lectura se distinguen del recorrido continuo conservado en los archivos fuente; el montaje no representa tiempos de administración reales.

Dos tomas iniciales de misión no se utilizaron en el montaje: una agotó el selector de confirmación final y otra superó el tiempo de espera durante MEDIUM. Se reiniciaron únicamente los servicios de demostración y se registró la recuperación de su estación. La toma entregada llegó a `mission/debrief`. No se presentan las tomas interrumpidas como sesiones completadas.

## Modelo 3D

Geometría procedural en TypeScript. Se reutilizan las fuentes originales REDLINE de `strikerdlm/3d-physiology-webxr/drone-racing-three`, verificadas contra el commit `f8a22932544368475dda9dd05227f092dbde1893`. Las copias originales, dimensiones y hashes están en `../fuentes/redline/`; la copia ejecutable conserva 17 conjuntos, cuatro rotores y texturas procedurales. No se carga ningún recurso remoto durante la reproducción. Unidades: metros; eje vertical +Y. Dimensiones ilustrativas: mesa 1.80 × 0.82 m, ancho de pantalla 0.76 m, escala de aeronave 0.52 m. Las dimensiones y el sensor esquemático no constituyen réplicas de productos. No hay simulación fisiológica o de vuelo en este modelo.

Controles: órbita, acercamiento, enfoque de componentes, separación reversible, pausa y reinicio. El modo de movimiento reducido comienza en pausa. Se conserva la geometría durante la animación y se liberan geometrías, materiales, controles y renderer al salir.

Se comprobó el contrato de los módulos contra el código oficial de [WebGLRenderer r186](https://github.com/mrdoob/three.js/blob/r186/src/renderers/WebGLRenderer.js) y [OrbitControls r186](https://github.com/mrdoob/three.js/blob/r186/examples/jsm/controls/OrbitControls.js), consultados el 22-09-2026. Se eligió la ruta procedural de la skill solicitada; no se necesitó una conversión CAD/Blender ni imágenes generadas para representar las pantallas reales.

## Verificación reproducible

```powershell
node EMAVI/construccion/build_video_assets.mjs
node webui/frontend/node_modules/typescript/bin/tsc -p EMAVI/video/tsconfig.json
node EMAVI/construccion/check_video.mjs
```

Los resultados medidos se guardan en `../revision/verificacion-video.json`, `../revision/metricas-3d.json` y `../revision/ffprobe-video.json`; las vistas de revisión se guardan junto a ellos. Las mediciones corresponden a Chrome automatizado en Windows y no garantizan rendimiento en cualquier equipo. La comprobación de integridad técnica no valida instrumentos, calibración humana ni uso clínico u operacional.

Las recetas de grabación y montaje son `../construccion/record_walkthrough.mjs`, `generate_hd_narration.ps1`, `assemble_hd_narration.py` y `render_video.mjs`. FFmpeg y Chrome deben estar instalados para reconstruir el MP4. Los videos fuente e intermediarios grandes permanecen locales y están excluidos por `.gitignore`; el video final y los elementos necesarios para reproducirlo están en el paquete.

La exportación de la presentación FAC conserva su bloqueo independiente hasta la aprobación de la política de aviso y cierre. Este video se reproduce después de la presentación y no modifica el arte original FAC.

Para regenerar la voz, ejecute `pwsh -File EMAVI/construccion/generate_hd_narration.ps1 -Force` desde la raíz. Requiere Python con el SDK OpenAI, la skill speech y la clave local; realiza solicitudes facturables a OpenAI. El script lee modelo, voz, velocidad e instrucciones de instructor en `narracion.json`. Los nombres históricos de los scripts y del informe `narracion-hd.json` se conservan por compatibilidad; el campo `model` identifica la generación actual. Después ejecute `node EMAVI/construccion/render_video.mjs` y `node EMAVI/construccion/finalize_video.mjs`. El generador local antiguo se conserva como receta histórica y sus marcas no son compatibles con este montaje.

En el montaje, el capítulo de escalas mantiene la captura documental de las medidas posteriores al bloque tras la transición inicial, para acompañar su explicación sin avanzar visualmente al informe antes del capítulo siguiente. La normalización de audio del montaje usa -18 LUFS y un pico verdadero objetivo de -1.5 dBTP.

La introducción y el cierre muestran el dron REDLINE con hélices giratorias, movimiento de cámara y separación/reensamblaje de sus conjuntos. Es una visualización ilustrativa; no reutiliza ni representa una prueba de vuelo del simulador. `drone-viewer.ts` conserva la escala original en metros; la estación amplía el dron para su lectura. `../revision/redline.json` comprueba geometría finita, 17 conjuntos, cuatro rotores, tiempo determinista y diez ciclos de reensamblaje.
