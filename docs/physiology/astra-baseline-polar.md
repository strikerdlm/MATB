# Basal ASTRA con Polar H10 en MATB

Procedimiento operativo solicitado el 2 de octubre de 2026 para ASTRA 1.
Una estación admite **un H10**. Cinco bandas no habilitan cinco capturas
simultáneas en el mismo servidor. Usar turnos o cinco estaciones independientes,
cada una con su propio Bluetooth, servidor y directorio de datos.

## Duración y finalidad

- **Basal PRE abreviado elegido:** ≥5 min de adaptación sentado + 5 min de
  RR, además de colocación y revisión. Planificar aproximadamente 15–20 min
  por persona (75–100 min para cinco por turnos); es una estimación logística.
- El manual ASTRA v2.8 y su protocolo basal reservan 30 min/persona con
  ≥5 min de adaptación y 10 min de RR (dos segmentos de cinco minutos).
  La opción abreviada omite el segundo segmento de respaldo; se registra en
  la versión del protocolo y con la condición `PRE_REST_SEATED_5MIN`.
- **Referencia MATB (`TASK_PRE`):** 5 min antes de la primera tarea, separada
  del basal PRE. La visita MATB V0 conserva 90 min, tres bloques de 15 min,
  familiarización, evaluaciones y pausas. Esta opción no acorta la visita.
- El manual programa V0 ASTRA 1 el 29 de septiembre y entrenamiento el
  3 de octubre. Registrar la fecha real y la reprogramación del basal pendiente;
  no duplicar un V0 ya realizado ni convertir entrenamiento en investigación.

Cinco minutos es la duración de referencia para HRV de corto plazo; mantener
≥5 min previos en la postura elegida, respiración espontánea y condiciones
comparables ([Laborde et al., 2017](https://doi.org/10.3389/fpsyg.2017.00213)).
Un resultado de la ventana rápida de 60 s no reemplaza el basal de cinco minutos.

## Preparar el puesto y las identidades

1. Comprobar que esta versión está cargada en frontend y backend. Hacer un
   ensayo identificado como **Práctica**, sin contabilizarlo como V0.
2. Abrir `http://127.0.0.1:3100/astra`, seleccionar ASTRA 1 y comprobar las
   cinco identidades y su correspondencia con los códigos originales. Conservar
   los identificadores existentes; documentar cualquier equivalencia Cxx/Pxx.
3. En una base sin protocolo activo, dejar marcado **Incluir Polar H10**,
   elegir **5 min · modalidad abreviada**, indicar el investigador y activar
   el protocolo. Esto crea asignaciones, no resultados. Un protocolo ya
   congelado sin Polar requiere una revisión explícita en Configuración del
   estudio; no se modifica automáticamente.
4. Rotular físicamente las bandas K01–K05 y guardar la correspondencia
   participante–banda–estación–hora. Los alias «Polar H10 1» se conservan entre
   búsquedas durante la misma ejecución del servicio; **no son números de serie**
   y pueden cambiar al reiniciarlo. Identificar cada banda con las otras
   desconectadas/inactivas, antes de colocarlas simultáneamente. No identificar
   personas por RSSI o frecuencia cardíaca. Evitar receptores competidores;
   verificar la configuración real si se usa también ActiGraph.
5. Confirmar consentimiento/elegibilidad y registrar hora real, postura,
   tiempo desde despertar, ingestas, ejercicio, síntomas e interrupciones
   según la hoja de campo. No introducir nombres clínicos en archivos públicos.

## Por persona: basal PRE

1. Seleccionar tripulante y **V0 PRE → Aplicar visita → Basal PRE sentado**.
   Abrir la captura desde esa evaluación asignada, en modo **Estudio**.
2. Humedecer y ajustar la banda; **Buscar y conectar H10**. Si aparece una sola
   banda disponible, se conecta automáticamente. Si aparecen varias, elegir la
   banda físicamente comprobada; no se inicia la grabación automáticamente.
   Verificar persona seleccionada, contacto y recepción real de RR. BPM emitidos
   por sí solos no sirven para HRV. Conservar ECG 130 Hz y ACC 50 Hz ±2 g del
   protocolo, salvo una configuración prescrita y verificada diferente.
3. **Preparar**. Adaptación ≥5 min: sentado, espalda apoyada, pies planos,
   manos quietas, ojos abiertos, silencio y respiración espontánea. No ejecutar
   MATB, responder cuestionarios ni conversar durante este reposo.
4. Al terminar la adaptación, **Iniciar grabación**. Registrar al menos cinco
   minutos continuos de RR utilizables. El reloj muestra duración, no certifica
   calidad. No iniciar la tarea durante estos cinco minutos.
5. **Detener y finalizar**. Revisar contacto, brechas y calidad. Si no hay una
   ventana continua elegible, conservar el intento y documentar el motivo;
   cualquier repetición técnica se registra como otro intento, no se sobrescribe.
6. Descargar **TXT Kubios · ms**, **CSV RR · ms**, **Participante, sesión y
   marcas** y metadatos. Conservar también Parquet/manifest y respaldos del
   estudio. Verificar que cada descarga corresponde a la persona y propósito.

## Capturar durante MATB

1. Volver a la visita y completar el screen/KSS/familiarización prescritos
   por el manual; no considerar el basal PRE sustituto de esas evaluaciones.
   El acceso ASTRA nativo no acredita automáticamente instrumentos externos.
2. Preparar el entorno nativo exacto hasta que quede retenido/listo. En el
   recorrido de visita, **Abrir captura Polar del bloque** crea/retoma la
   evaluación acompañante de ese bloque y de esa persona.
3. Comprobar la sesión acompañada, preparar e iniciar Polar. Antes del primer
   bloque, conservar cinco minutos de `TASK_PRE`. Volver a la visita; la
   captura continúa y el botón de tarea se habilita cuando consta capturando.
4. Ejecutar el bloque de 15 min y sus valoraciones. Las marcas de carga provienen
   del ciclo de vida OpenMATB. Son marcas de software, no medición física del
   inicio del estímulo.
5. Volver a **Polar del bloque**, detener y guardar; completar la pausa de
   tres minutos. Repetir en los bloques siguientes con el orden asignado.
   Esta implementación produce **una captura por bloque**, más el basal PRE;
   no presume continuidad entre esos archivos ni registra automáticamente las
   pausas. No añadir cinco minutos de referencia a cada bloque por defecto.
6. Finalizar las capturas y cerrar la recolección de la visita en Estación
   antes de cambiar de participante. Desconectar el H10 y conectar la siguiente
   banda verificada con **Cambiar de banda**. En práctica independiente, este
   botón también libera la captura terminada, conserva su revisión en
   **Última captura guardada** y limpia la selección de persona. En estudio,
   abrir la asignación de la siguiente persona desde su visita. Nunca reutilizar
   una captura cambiando el pseudónimo.

## Kubios, HRV y respiración

TXT: un RR por línea, milisegundos, sin encabezado. En Kubios: datos RR,
columna 1, unidades ms, cero encabezados y ninguna columna de tiempo. CSV RR:
mismas unidades, una columna `rr_ms`, una línea de encabezado. Importar cada
tramo continuo por separado; no concatenar archivos separados por brechas.
[Guía oficial Kubios](https://www.kubios.com/downloads/HRV-Scientific-Users-Guide.pdf).

Para el lector operativo del repositorio HRV verificado, usar TXT. Su lector
rechaza el CSV de una columna con encabezado; el CSV completo tiene columnas
adicionales, pero sus brechas requieren revisión explícita antes del análisis.

La vista rápida muestra el tramo continuo más largo (sus últimos cinco minutos,
o una ventana corta exploratoria). No adjudica automáticamente el desenlace
basal principal. En la modalidad de 10 min, usar el primer segmento elegible
preespecificado, sin elegir el de mayor RMSSD.

La frecuencia respiratoria de ACC es **una estimación experimental**. No se
ha medido su exactitud contra una referencia humana; mantener la frecuencia
respiratoria protocolaria como faltante si no existe medición válida. El panel
omite estimaciones que no superan sus controles de señal y no genera una
clasificación clínica, de recuperación o de aptitud.

Fuentes locales consultadas: Manual de Operaciones ASTRA 2026 v2.8 (actualizado
2026-10-01), §2.3 y §4.7.6; Protocolo de línea de base única ASTRA 2026, §2–3;
Guía controlada de adquisición y análisis ASTRA 1 y 2, 2026-09-27, §2–3.
