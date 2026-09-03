# Criterios terminológicos para la localización española

Esta localización emplea español aeronáutico de uso internacional y la variante
`es_CO`. Se distingue entre términos aeronáuticos, etiquetas experimentales de
MATB e identificadores internos del software.

| Inglés | Español visible | Criterio |
|---|---|---|
| System monitoring | Vigilancia de sistemas | «Vigilancia» es el término aeronáutico para *surveillance/monitoring*; «de sistemas» delimita la tarea MATB. |
| Tracking | Seguimiento | Describe el seguimiento continuo de la retícula; no se presenta como guía vectorial ni vigilancia ATS. |
| Communications | Comunicaciones | Se conserva COMM como identificador de tarea. |
| Resources management | Gestión de recursos | Describe depósitos y bombas de la tarea RESMAN; no implica gestión de recursos de tripulación (CRM). |
| Callsign | Distintivo de llamada | Término aeronáutico para la identificación usada en las comunicaciones. |
| Target frequency | Frecuencia objetivo | Se evita «frecuencia meta» y se conserva la unidad MHz. |
| System fault | Condición anormal o falla del sistema | Se elige según se describa un aviso operativo o el estado técnico simulado. |
| Performance | Rendimiento | Se reserva «performance» sin traducir únicamente para denominaciones normativas que lo requieran. |

Los alias `sysmon`, `track`, `communications`, `resman` y `scheduling`; los
comandos `start`, `stop`, `pause` y `resume`; los parámetros de escenario; y las
abreviaturas NAV/COM permanecen sin cambios para preservar compatibilidad.

Las letras de COMM utilizan el alfabeto de deletreo radiotelefónico internacional
(`Alfa`, `Bravo`, `Charlie`, …, `Zulu`). En audio, el separador decimal se
pronuncia «decimal».

Fuentes normativas y de orientación consultadas:

- OACI, *Procedimientos para los servicios de navegación aérea — Abreviaturas y códigos de la OACI* (PANS-ABC, Doc 8400), referenciado en esta [documentación oficial OACI](https://www.icao.int/sites/default/files/sp-files/SAM/Documents/GREPECAS/2008/CNSCOMM06/CNSC06NI02.pdf).
- OACI, *Procedimientos para los servicios de navegación aérea — Gestión del tránsito aéreo* (PANS-ATM, Doc 4444), relacionado con el empleo de fraseología normalizada en esta [orientación oficial OACI](https://www.icao.int/sites/default/files/sp-files/SAM/Documents/2014-SAMIG13/SAMIG13_NE20.pdf).
- OACI, Anexo 10, Volumen II, disposiciones sobre procedimientos de comunicaciones y fraseología.

La localización no constituye aprobación de la OACI ni valida OpenMATB para uso
operacional, entrenamiento certificado o comunicaciones ATS reales.
