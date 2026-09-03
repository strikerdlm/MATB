# Voces de comunicaciones en español

Los fragmentos WAV de esta carpeta son recursos de voz sintética generados por
inteligencia artificial para la tarea COMM de OpenMATB. No corresponden a la
voz de una persona ni a una comunicación ATS real. Las letras usan el alfabeto
de deletreo radiotelefónico OACI (`Alfa`, `Bravo`, `Charlie`, etc.); las cifras
se reproducen individualmente en español y el separador de frecuencia se
pronuncia `decimal`.

- Variante: español de Colombia (`es-CO`).
- Proveedor: OpenAI, endpoint de voz `/v1/audio/speech`.
- Modelo fijado: `gpt-4o-mini-tts-2025-12-15`.
- Voces: `marin` y `cedar`, recomendadas por OpenAI para mayor calidad.
- Los directorios `female` y `male` conservan los selectores históricos de
  OpenMATB; no representan una clasificación de género de las voces de OpenAI.
- Formato: WAV PCM, mono, 22 050 Hz, 16 bits.
- El archivo `manifest.json` registra texto, modelo, voz, duración y SHA-256 de
  cada recurso.
- Regeneración de mantenimiento: instale las dependencias de desarrollo,
  configure `OPENAI_API_KEY` mediante un mecanismo seguro y ejecute
  `python scripts/generate_spanish_audio.py --overwrite`.
- Verificación sin red ni credencial:
  `python scripts/generate_spanish_audio.py --check`.

Los recursos conservan la estructura experimental de MATB. La alineación OACI
se limita al alfabeto radiotelefónico y a la lectura de frecuencias; no afirma
que el mensaje completo sea fraseología ATS normalizada. Estos audios no
sustituyen comunicaciones reales, instrucción operacional, revisión por un
especialista en radiotelefonía ni una evaluación formal de inteligibilidad.
