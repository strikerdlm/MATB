# Voces de comunicaciones en español

Los fragmentos WAV de esta carpeta son recursos de voz sintética para la tarea
COMM de OpenMATB. Las letras usan el alfabeto de deletreo radiotelefónico OACI
(`Alfa`, `Bravo`, `Charlie`, etc.); las cifras se reproducen en español y el
separador de frecuencia se pronuncia `decimal`.

- Variante: español de Colombia (`es-CO`).
- Voces de síntesis: `es-CO-SalomeNeural` y `es-CO-GonzaloNeural`.
- Formato: WAV PCM, mono, 22 050 Hz, 16 bits.
- Generación verificada con `edge-tts` 7.2.8.
- Regeneración: instale `edge-tts` y ejecute
  `python scripts/generate_spanish_audio.py --overwrite`.

Estos audios respaldan una tarea experimental. No sustituyen comunicaciones
ATS reales, instrucción operacional ni una evaluación formal de inteligibilidad.
