# MATB-FAC: diagnóstico de audio, instrucciones y teclado

Fecha: 2 de octubre de 2026 (America/Bogota). Entrega comprobada sobre `origin/main` (`d425e68`).

## Diagnóstico

Los MP3 de instrucciones del navegador y las llamadas NAV/COM del motor nativo son recursos distintos. OpenMATB construye las llamadas con fragmentos WAV de `openmatb/includes/sounds`. La presencia de MP3 no garantiza su reproducción en la ventana nativa.

Se comprobaron tres defectos en la implementación:

- El motor aceptaba la salida silenciosa de Pyglet y continuaba tras ciertos errores de reproducción. Ahora rechaza `SilentDriver`, invalida la oportunidad afectada y detiene la ejecución ante errores de presentación, en vez de seguir acumulando respuestas a llamadas no presentadas.
- Una combinación de idioma/voz inexistente conservaba el banco anterior. Se reprodujo seleccionando `english/female`, que no está distribuido: se oía el banco español anterior. Ahora se rechazan bancos ausentes o incompletos. Los bancos comprobados son `english/male` y `spanish/female`.
- Al cambiar de ventana o abrir una pausa, una tecla sostenida podía permanecer activa. Ahora se libera ese estado, se registra que el reinicio fue realizado por software y se solicita el foco al abrir la ventana y al liberar la preparación. Enter numérico confirma COMM cuando la confirmación está asignada a Enter; se respetan las asignaciones personalizadas.

La entrega también vincula el bucle de eventos del planificador con el bucle global que utilizan los eventos de Windows en Pyglet. Se conserva una prueba de regresión para esta dependencia del funcionamiento nativo.

Las ejecuciones actuales reprodujeron sonido mediante XAudio2. No se dispone del registro de la sesión exacta del incidente, por lo que estos hallazgos no identifican con certeza la causa de aquella ausencia de sonido. No se midió la salida acústica física, el mezclador de volumen de aquella sesión ni la escucha humana.

## Instrucciones de audio

Archivo distribuido: `webui/frontend/public/audio/instructions/openmatb-es.wav`.

- OpenAI `gpt-4o-mini-tts-2025-12-15`, voz `marin`, español.
- WAV PCM de 16 bits, mono, 24 kHz, sin compresión; duración: 180,85 segundos.
- Pico digital: 0,6241; RMS: −21,73 dBFS; muestras recortadas: 0.
- Se corrigió la cabecera del WAV de streaming mediante FFmpeg, sin remuestrear. Su duración y cantidad de muestras se verificaron después.
- La transcripción automática conservó todos los párrafos sobre tareas y controles. El acrónimo del título se transcribió de forma imperfecta; esto no sustituye una revisión auditiva humana.
- El texto, las indicaciones de voz, el modelo, las características y los SHA-256 están en `openmatb-es.txt`, `openmatb-es-directions.txt` y `openmatb-es.manifest.json`, junto al audio.
- Los textos se distribuyen con saltos de línea LF mediante `.gitattributes`, para conservar sus hashes al descargar el repositorio en Windows o Linux.

La documentación oficial consultada identifica GPT-4o mini TTS como el modelo más reciente de síntesis de voz y recomienda Marin/Cedar para calidad: <https://developers.openai.com/api/docs/guides/text-to-speech>. La versión fijada está documentada en <https://developers.openai.com/api/docs/models/gpt-4o-mini-tts>.

La explicación pide prestar mucha atención, distingue indicativo propio y distractores, explica NAV/COM, flechas y Enter, F1–F6, teclado numérico 1–8, joystick, foco de ventana, pausa y preguntas de carga. Advierte que escuchar la explicación no verifica por sí solo las llamadas nativas.

## Uso

Reinicie OpenMATB para cargar las correcciones antes de una nueva práctica.

En la consola, la página del participante en español ofrece el audio antes de comenzar y entre bloques. El inicio se deshabilita mientras se reproduce; cambiar a la tarea detiene la narración. Hay transcripción y un mensaje si el archivo no puede reproducirse.

Al abrir OpenMATB directamente en español, aparece la pantalla de instrucciones antes de iniciar el reloj de la tarea. A reproduce y R repite. Espacio permite continuar después de la reproducción; Q sale y detiene el audio. Cancelar esta pantalla no inicia las tareas pendientes. El lanzamiento supervisado utiliza las instrucciones del navegador y conserva la preparación existente. `--skip-briefing` queda disponible para diagnósticos sintéticos.

Durante la práctica compruebe la escucha de NAV/COM en la salida elegida. Compruebe también Bloq Num y, en portátiles, el modo de las teclas de función. Si no se oyen las llamadas, revise la salida y el volumen de la aplicación OpenMATB/Python en Windows antes de iniciar otro bloque.

## Verificación

| Comprobación | Resultado |
| --- | --- |
| Suite completa del motor OpenMATB | 938 aprobadas |
| Perfil de comunicaciones y generador de escenarios | 67 aprobadas |
| Pantalla de participante | 17 aprobadas |
| TypeScript y ESLint de los archivos de interfaz modificados | Sin errores |
| Audio y controles nativos, inglés | Aprobado: 8 controles; HIT y CR en COMM |
| Audio y controles nativos, español | Aprobado: 8 controles; HIT y CR en COMM |
| Instrucciones nativas | Aprobado: visibles antes de la tarea, reproducción activa, inicio bloqueado durante narración y salida que detiene el audio |
| Integridad de WAV/texto/indicaciones | SHA-256 verificados |

Las pruebas nativas usan el planificador, el reproductor XAudio2, la ventana y el registro científico reales. El programa de diagnóstico envía eventos sintéticos por la ventana para probar selección de radio, bombas, pérdida de foco, pausa, reanudación, F1, ajuste sostenido y Enter numérico. Esto verifica el procesamiento de eventos, no la pulsación física de cada tecla. Se reprodujeron COM_1 y NAV_1; los bancos conservan los recursos de las cuatro radios.

Las ejecuciones iniciales permitieron detectar la selección de banco incorrecta y corregir dos aserciones del diagnóstico. Una ejecución inglesa posterior tuvo un evento SYSMON rechazado por retraso de apertura; no se modificó su tolerancia. La ejecución final completa pasó. Las evidencias iniciales se conservan en `output/` y no se presentan como aprobadas.

La validación de entrega se repitió en una copia de trabajo basada en `d425e68`, con los cambios de este PR. Las 59 pruebas específicas de audio, instrucciones, teclado y cierre también pasaron tras los ajustes finales de formato.

Evidencia final distribuida en esta carpeta:

- `native-result-en.json`, `native-result-es.json` y `native-result-briefing.json`.
- `native-briefing.png`, `native-controls-en.png` y `native-controls-es.png`.

Los registros completos permanecen localmente en `output/audio-pr-20261002-en`, `output/audio-pr-20261002-es` y `output/audio-pr-20261002-briefing`. En las copias distribuidas de los resultados, `voice_path` se expresa con relación a la raíz del repositorio para no depender del nombre de la copia temporal.

Comando reproducible, desde la raíz del repositorio con el intérprete de OpenMATB:

```powershell
.venv-openmatb/Scripts/python.exe scripts/verify_openmatb_audio_controls.py --language es_CO --output output/audio-control-check-es
.venv-openmatb/Scripts/python.exe scripts/verify_openmatb_audio_controls.py --language en_EN --output output/audio-control-check-en
.venv-openmatb/Scripts/python.exe scripts/verify_openmatb_audio_controls.py --language es_CO --briefing --output output/briefing-check-es
```

Cada destino debe ser nuevo. Las ejecuciones son sintéticas, no alteran sesiones de participantes y no constituyen validación humana ni calibración de latencia acústica. No se modificaron umbrales de puntuación ni ventanas de respuesta.
