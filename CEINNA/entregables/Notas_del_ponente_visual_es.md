# Notas del ponente · edición visual

CEINNA · 17 láminas · 720 segundos de exposición previstos.

## 1. III CEINNA — 0 s

Pantalla institucional de espera. No consume exposición programada. La transición se incorpora al ensayo. Fuente: Formulario 3 original.

## 2. Carga mental y desempeño multitarea en ASTRA — 20 s

GUION ORAL (único texto que se pronuncia):
Soy Diego L. Malpica, especialista en Medicina Aeroespacial, de la Subdirección Científica Aeroespacial de la DIMAE. Presentaré el diseño longitudinal para estudiar carga mental y desempeño multitarea en ASTRA mediante MATB, la batería de tareas de atributos múltiples.

NOTAS DE APOYO (no leer):
Autoría de portada confirmada por el investigador: SMSM DIEGO L MALPICA; Especialista en Medicina Aeroespacial; Subdirección Científica Aeroespacial – DIMAE. MATB: Multi-Attribute Task Battery. DIMAE: Dirección de Medicina Aeroespacial. Fuente: confirmación del investigador; [1] Cegarra et al. (2020). Transición: aportes de las implementaciones MATB.

## 3. Aportes de la familia MATB — 55 s

GUION ORAL (único texto que se pronuncia):
MATB reúne una familia de implementaciones con aportes complementarios. NASA estableció las tareas de referencia; la Fuerza Aérea de Estados Unidos amplió la generación de guiones y la sincronización externa. OpenMATB aportó personalización, código abierto y replicabilidad. La implementación del laboratorio aeromédico del Ejército estadounidense incorpora transiciones de demanda y automatización adaptativa. Sobre OpenMATB, el trabajo de la Fuerza Aeroespacial Colombiana organiza escenarios reproducibles, registros trazables y métricas versionadas. ASTRA sitúa esta arquitectura en una pregunta longitudinal: cómo cambia la respuesta multitarea dentro de cada persona. El aporte se expresa en la conexión entre el procedimiento experimental y la interpretación de sus observaciones.

NOTAS DE APOYO (no leer):
Fuentes: [1] Cegarra et al. (2020), Requirements for an updated implementation y Experiment replicability; [5] Vogl et al. (2024), §1.2, §2 y §3. NASA/AF-MATB se resumen según la revisión histórica de Vogl; el informe DTIC 2014 se identificó pero no se obtuvo su texto completo. NASA NTRS permitió verificar metadatos; PDF no accesible en esta consulta. No presentar las implementaciones como una escala de superioridad ni como métricas equivalentes. FAC: Fuerza Aeroespacial Colombiana; USAF: United States Air Force; USAARL: U.S. Army Aeromedical Research Laboratory. Integración local: auditoria_matb.md y resultados técnicos de lámina 11. Las cifras de pruebas de los dos resúmenes adjuntos describen instantáneas anteriores, no son resultados actuales. Transición: qué necesidad metodológica responde este diseño.

## 4. De la literatura al diseño ASTRA — 50 s

GUION ORAL (único texto que se pronuncia):
La revisión de Pontiggia incluyó diecinueve estudios que compararon niveles de demanda con MATB. Según sus autores, siete describieron la configuración con suficiente detalle para permitir replicación o revisión. Este hallazgo orienta una decisión concreta: documentar parámetros, versión y secuencia de eventos, además de conservar el contexto de medición. Distinguimos la demanda programada, el desempeño observado y la carga percibida. Nuestra pregunta es cómo varían estos dos últimos componentes entre condiciones y a lo largo de ASTRA. Esta separación permite estudiar las respuestas de cada persona con una exposición experimental explícita.

NOTAS DE APOYO (no leer):
Fuente primaria [2] Pontiggia, Gomez-Mérino et al. (2024), §3 y §3.3, configuración MATB: 19 publicaciones incluidas; siete suficientemente detalladas para replicación o revisión. La proporción describe la información reportada en ese conjunto de estudios: no es una tasa de replicación exitosa ni representa toda la literatura MATB. Cinco no describían la configuración; no agrupar las otras doce como estudios inválidos. No se efectuó metaanálisis debido a heterogeneidad y pequeño número de trabajos. Las decisiones para ASTRA son una síntesis metodológica del proyecto, no resultados experimentales de la revisión. Condiciones LOW/MEDIUM/HIGH parametrizadas, sin equivalencia universal. Transición: contexto longitudinal ASTRA.

## 5. ASTRA: contexto del estudio — 50 s

GUION ORAL (único texto que se pronuncia):
ASTRA significa Aerospace Simulation Training Research Analogs. El protocolo contempla dos misiones secuenciales en el hábitat de la Fundación Cydonia, en Tocancipá. Cada misión prevé hasta seis participantes y quince jornadas inclusivas, con catorce noches dentro del hábitat. La evaluación se integra en una rutina de aislamiento y confinamiento, con horarios de sueño, alimentación, experimentos y actividades operativas. Este contexto permite seguir a cada persona en diferentes momentos del ciclo de misión. La ilustración representa conceptualmente una estación de evaluación y está identificada como generada con inteligencia artificial. La muestra final y las actividades realizadas se documentarán mediante los registros de ejecución.

NOTAS DE APOYO (no leer):
ASTRA: Aerospace Simulation Training Research Analogs. Fuente: Manual v2.5, §§1.1–1.2 y 3.2; cronograma §§1–2. Seis participantes por misión es meta condicionada a elegibilidad, máximo 12 en conjunto. Quince días significa fechas inclusivas; la duración analítica procede de horas reales de cierre/apertura. Hábitat terrestre de aproximadamente 120 m². La imagen no representa una fotografía documental ni una verificación del equipamiento desplegado. Transición: secuencia de visitas.

## 6. Ocho visitas por participante — 65 s

GUION ORAL (único texto que se pronuncia):
Cada participante tiene ocho visitas. V cero corresponde a la evaluación premisión; después se programan seis visitas en los días dos, cuatro, siete, diez, trece y quince; V siete corresponde al día siguiente al egreso. Esta secuencia permite comparar condiciones dentro de una visita y seguir cambios entre visitas. Las evaluaciones basales se programan el veintinueve de septiembre para ASTRA uno y el veintiocho para ASTRA dos. Están, respectivamente, a seis y veintitrés días del ingreso. Conservaremos esas distancias y las fechas reales en el análisis. Además, la rotación distribuye a cada participante entre horarios y estaciones durante las visitas intramisión. El calendario del congreso coincide con los días nueve y diez de ASTRA uno; la ponencia se concentra en el protocolo y el desarrollo documentado.

NOTAS DE APOYO (no leer):
DM: día de misión; V: visita. Fuente: Manual §4.7.6.2–3; cronograma §§2, 4.1, 5.2 y 7; evidencia/cronologia_astra.csv. ASTRA1 ingreso 5oct, egreso 19oct y V7 20oct; ASTRA2 ingreso 21oct, egreso 4nov y V7 5nov. Intervalos intramisión: 2/3/3/3/2 días. CEINNA 13oct=DM9 y 14oct=DM10/V4 de A1; A2 en premisión. Disponibilidad futura de V4 depende de hora de ponencia, finalización y revisión. La rotación hora/estación es distinta del orden de niveles. Los códigos originales y el orden basal deben conservarse al vincular aspirante con misión. Transición: tareas que se repiten en cada visita.

## 7. Cuatro tareas simultáneas — 60 s

GUION ORAL (único texto que se pronuncia):
MATB presenta cuatro tareas simultáneas. SYSMON, supervisión de sistemas, exige detectar cambios en luces e indicadores. TRACK, seguimiento compensatorio, requiere mantener un cursor dentro de una zona objetivo. COMM, comunicaciones, exige reconocer el indicativo pertinente y responder mediante la radio correspondiente. RESMAN, gestión de recursos, requiere controlar bombas y niveles de depósitos. Cada tarea aporta medidas específicas: detecciones, omisiones y latencias; desviación del seguimiento; respuestas a comunicaciones; y desviación de los depósitos respecto al objetivo. La concurrencia exige distribuir la atención entre demandas diferentes. OpenMATB proporciona el entorno de tareas; la integración de este repositorio genera escenarios, organiza su procedencia y procesa los registros.

NOTAS DE APOYO (no leer):
Fuente: [1] Cegarra et al. (2020); auditoria_matb.md y openmatb/plugins/{sysmon,track,communications,resman}.py. SYSMON: system monitoring; TRACK: tracking; COMM: communications; RESMAN: resource management. Mantener en la imagen el rótulo de procedencia que incorpore el ensamblaje. Métricas vigentes: latencia en ms; TRACK en distancia normalizada; depósitos en unidades del escenario. Las proporciones calculadas por muestras no se describen como tiempo medido sin ponderación temporal. Transición: organización de los tres bloques y sus medidas subjetivas.

## 8. Estructura de una visita — 55 s

GUION ORAL (único texto que se pronuncia):
Cada visita reserva noventa minutos. Incluye preparación, reposo, tres escenarios de quince minutos, pausas, cuestionarios y cierre. El orden de las tres condiciones se contrabalancea entre participantes. Antes de cada bloque se registra somnolencia con la escala de Karolinska, KSS. Durante la tarea, ISA recoge una autoevaluación instantánea. Después se administra NASA-TLX, el índice de carga de tarea de la NASA. Su versión cruda, RTLX, resume seis dimensiones mediante una media reescalada de cero a cien. Estas medidas conservan sus constructos específicos. Los cuestionarios pueden pausar el software, por lo que registramos tanto los novecientos segundos del escenario como la duración real de la sesión.

NOTAS DE APOYO (no leer):
NASA-TLX: NASA Task Load Index; RTLX: Raw Task Load Index, media no ponderada de seis ítems completos. ISA: Instantaneous Self-Assessment. KSS: Karolinska Sleepiness Scale. Fuentes: Manual §§4.7.2 y 4.7.6.2; contrato metrics_spec.json; auditoria_matb.md; [3] Pontiggia, Fabries et al. (2024). [6] Laverde-López et al. (2022) es referencia complementaria de KSS colombiana; su publicación no acredita equivalencia literal con la implementación local. RTLX incompleto=valor ausente con motivo; TLX ponderado exige comparaciones pareadas. La figura LOW/MEDIUM/HIGH identifica condiciones, no una secuencia fija para todos. Transición: conservación de la evidencia.

## 9. Fisiología: adquisición separada — 30 s

GUION ORAL (único texto que se pronuncia):
ASTRA contempla una línea fisiológica separada de las cuatro tareas MATB. La banda pectoral Polar H10 puede aportar intervalos R–R cuando se verifica la ruta de captura; el dispositivo de muñeca registra movimiento y actividad. Los descriptores de variabilidad cardíaca se derivan después de revisar calidad, cobertura y tiempo. Su relación con la carga y el desempeño será exploratoria; esta ilustración no representa una adquisición humana.

NOTAS DE APOYO (no leer):
Manual ASTRA v2.5, sección de adquisición fisiológica y §4.2.3; matb_integration/physiology/contracts.py y analysis.py. El R–R directo del H10 requiere ruta/receptor verificados; ActiGraph registra movimiento y la ruta de frecuencia cardíaca puede no conservar R–R. HRV se deriva tras control de artefactos y calidad, no es una señal medida directamente. Los sensores no prueban despliegue ni resultados de participantes. No inferir diagnóstico, aptitud, predicción de fatiga o equivalencia con umbrales ventilatorios medidos. Ilustración conceptual generada con IA. Transición: trazabilidad de los registros.

## 10. Del escenario a una métrica interpretable — 65 s

GUION ORAL (único texto que se pronuncia):
La trazabilidad conecta escenario, registro, métrica y análisis. Un ejemplo concreto es la carga percibida. En el contrato local, las seis respuestas de cero a diez deben estar completas; su media, multiplicada por diez, produce el índice no ponderado de cero a cien, denominado RTLX. Se conservan respuestas, versión, unidad y regla de cálculo. Si falta una dimensión, se preservan los datos disponibles y se registra el motivo de ausencia del compuesto. Esta regla hace interpretable el resultado y permite revisar cómo se obtuvo. El mismo principio se aplica a los eventos y las métricas de desempeño: cada salida mantiene su vínculo con la condición y el registro de origen.

NOTAS DE APOYO (no leer):
Fuentes de replicabilidad: [1] Cegarra et al. (2020), Experiment replicability; [5] Vogl et al. (2024), data handling y parameter generation. Regla RTLX verificada en matb_integration/metrics_spec.json y log_converter.py, auditoria_matb.md: seis dimensiones 0–10, media ×10, resultado 0–100, null si incompleto. RTLX: Raw Task Load Index, índice no ponderado; distinguir de NASA-TLX ponderado que requiere comparaciones pareadas. Un ejemplo de transformación de escala no demuestra validación psicométrica local. Completitud de archivo, calidad y elegibilidad de análisis se registran por separado. SHA-256 comprueba integridad de bytes; el tiempo físico corresponde a su procedimiento de medición. Transición: comprobaciones técnicas efectivamente ejecutadas.

## 11. Resultados de desarrollo — 65 s

GUION ORAL (único texto que se pronuncia):
Los resultados de desarrollo proceden de una demostración local con datos sintéticos. Se generaron tres escenarios, uno por condición, de novecientos segundos cada uno. Al repetir parámetros y semillas, los tres archivos resultaron idénticos. Sus huellas digitales coincidieron con las registradas en los manifiestos. Además, tres archivos CSV sintéticos se convirtieron en salidas de métricas versionadas. Estos resultados documentan reproducción e integridad, y comprueban por separado la generación de escenarios y la conversión de registros. La ejecución está fechada el veintiuno de septiembre y vinculada a una revisión del repositorio. Los artefactos conservan las entradas y los resultados de comprobación, de modo que otra revisión pueda repetir este procedimiento. La respuesta de los participantes constituye el objeto de la adquisición experimental prevista.

NOTAS DE APOYO (no leer):
Fuente primaria ejecutada: evidencia/verificacion_tecnica/resultado_verificacion.json; verificar_demo.py; escenarios, ejecucion_generador.txt y ejecucion_verificacion.txt. Commit fd5e1318dc6f036b538dd36ed3c5fe42ad8be7d0. Verificación: 3/3 hashes, 3/3 escenarios reproducidos idénticos y 3/3 CSV convertidos. No se presenta esta demostración como dato humano. La CLI auditada usó audio y cuestionarios ingleses; recursos españoles del repositorio se documentan separadamente. Se realizaron aserciones focales; no atribuir batería global de pruebas ni ajuste DEPDF al experimento. Transición: estructura de análisis de las futuras observaciones. Los CSV son fixtures sintéticos independientes; no son respuestas adquiridas durante la ejecución de los escenarios generados.

## 12. Análisis de medidas repetidas — 65 s

GUION ORAL (único texto que se pronuncia):
La unidad de seguimiento es la persona. Los bloques están anidados en visitas y las visitas en participantes. El análisis comenzará con trayectorias individuales, contrastes entre condiciones y cambios entre visitas. Se conservarán orden, hora, estación, sueño previo y distancia desde la evaluación basal. El experimento de Pontiggia muestra la utilidad de considerar conjuntamente contexto de sueño y demanda multitarea; el seguimiento antártico de Tortello aporta un antecedente de evaluación temporal en aislamiento. Sus poblaciones y duraciones son diferentes de ASTRA. Para este estudio, los modelos se ajustarán a la información disponible y se acompañarán de magnitud e incertidumbre. La cantidad de bloques mejora la descripción longitudinal, mientras que el número de participantes define el alcance de la comparación entre personas.

NOTAS DE APOYO (no leer):
Fuentes: [3] Pontiggia, Fabries et al. (2024), medidas repetidas en hipoxia/sueño; [4] Tortello et al. (2020), 13 varones durante un año y tarea de producción temporal; Manual §4.7.4. Tortello no estudió MATB ni valida causalidad en ASTRA. Hasta 12 personas; máximo programado 96 sesiones y 288 bloques. Preespecificar resultado principal, secundarios, reglas de exclusión y multiplicidad. Modelo parsimonioso condicionado a estimabilidad; los bloques no son observaciones independientes. Transición: relación entre medición e interpretación.

## 13. Marco de calificación científica — 55 s

GUION ORAL (único texto que se pronuncia):
El marco de calificación organiza cinco preguntas científicas. La reproducción comprueba si se repite el escenario programado. La fidelidad temporal caracteriza cuándo llega el estímulo físico al participante. La respuesta humana estudia la relación entre demanda, desempeño y carga percibida. La estabilidad cuantifica la variación al repetir la medición. La comparabilidad examina qué se conserva entre implementaciones. Cada pregunta tiene procedimientos y evidencias específicos. En esta ponencia mostramos reproducción del software y un diseño longitudinal para observar personas. Esta organización permite que cada conclusión corresponda a la evidencia que la sustenta y orienta el programa de investigación.

NOTAS DE APOYO (no leer):
Síntesis del marco del proyecto en fuentes/Abstract_ceinna_aportado.md y CEINNA_aportado.md, contrastada con contratos locales y evidencia/auditoria_matb.md. No atribuir este marco de cinco dimensiones como una taxonomía validada publicada por Cegarra/Pontiggia/Vogl: [1,2,5] fundamentan replicabilidad, especificación de demanda y diferencias entre versiones. Son dominios de evaluación, no cinco resultados ya demostrados. Reproducción comprobada con escenarios sintéticos. Medición temporal física requiere observación externa del estímulo; marcas digitales describen eventos de software. La estabilidad test–retest considera aprendizaje y condiciones; equivalencia exige comparación directa preespecificada y márgenes adecuados. Los resultados humanos corresponden al programa de adquisición previsto. Transición: conclusiones metodológicas de la ponencia.

## 14. Conclusiones y recomendaciones — 65 s

GUION ORAL (único texto que se pronuncia):
La primera conclusión es que describir la demanda hace interpretable la comparación entre condiciones. Por ello, el protocolo conserva parámetros, duración y secuencia. La segunda es que la trazabilidad permite reconstruir el paso del escenario al evento y del evento a la métrica; la demostración técnica aporta evidencia de reproducción e integridad. La tercera es que ASTRA sitúa la respuesta multitarea en la trayectoria de cada persona, considerando contexto y calidad del registro. El análisis presentará resultados por tarea junto con carga percibida, magnitud e incertidumbre. La siguiente etapa es ejecutar las visitas conforme al protocolo y a las reglas de análisis predefinidas. Así se articulan desarrollo tecnológico y una pregunta concreta de investigación del factor humano.

NOTAS DE APOYO (no leer):
Fuentes: síntesis de [1,2,5], Manual §4.7 y cronograma §§2/4/7; comprobaciones de evidencia/verificacion_tecnica/. Las conclusiones describen contribución metodológica y evidencia técnica. No anticipan dirección de cambios, tamaños de efecto humanos, superioridad, equivalencia entre variantes ni validez operacional. Mantener el registro de incidencias, familiarización, fuentes de sueño y tiempos reales. Las medidas fisiológicas mantienen su propio protocolo de calidad e interpretación. Transición: referencias y preguntas.

## 15. Bibliografía I — 10 s

GUION ORAL (único texto que se pronuncia):
Estas primeras referencias fundamentan las tareas MATB, la descripción de la demanda experimental y la complementariedad de las mediciones.

NOTAS DE APOYO (no leer):
Fuentes [1–3] completas en evidencia/referencias_apa.md. Las dos publicaciones Pontiggia son revisión y experimento, respectivamente, con coautorías diferentes. No leer autores completos ni DOI durante los diez segundos. Transición: antecedentes complementarios.

## 16. Bibliografía II — 10 s

GUION ORAL (único texto que se pronuncia):
Estas referencias completan el fundamento metodológico. Muchas gracias; quedo atento a sus preguntas y comentarios.

NOTAS DE APOYO (no leer):
Fuentes [4–5] completas en evidencia/referencias_apa.md; [6] KSS complementaria en notas/banco. Reservar íntegros tres minutos para preguntas y comentarios. Transición a cierre institucional.

## 17. Cierre institucional — 0 s

Pantalla institucional de cierre y preguntas. Tres minutos separados de la exposición. Usar preguntas_comite.md para preparación; responder a las preguntas recibidas, sin imponer un listado al comité.
