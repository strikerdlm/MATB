# Preguntas y respuestas del comité

Preparación para **3 minutos de preguntas y comentarios**, separados de los 12 minutos de exposición. Las respuestas son orientaciones de 20–40 s a velocidad conversacional, no un libreto que deba completarse íntegro. Responder primero a la pregunta recibida. Fuentes [1–6]: `evidencia/referencias_apa.md`; M: Manual ASTRA; C: Cronograma. Corte documental: 21-09-2026.

## 1. ¿Cuál es la pregunta específica y por qué MATB?

**Respuesta breve, 25–30 s.** Queremos estudiar cómo varían el desempeño multitarea y la carga percibida entre condiciones de demanda y a lo largo de ASTRA. MATB reúne cuatro tareas concurrentes con parámetros definidos y medidas por tarea. Esto permite repetir procedimientos y comparar dentro de la misma persona, conservando el contexto de cada visita.

**Ampliación:** demanda parametrizada, desempeño y carga subjetiva son componentes distintos. Se examinan sus relaciones sin asumir una respuesta uniforme. **Fuentes:** [1–3]; M §4.7. **Respaldo:** láminas 4 y 7.

## 2. ¿Qué pertenece a OpenMATB y qué aporta este repositorio?

**Respuesta breve, 25–30 s.** OpenMATB proporciona las cuatro tareas y su entorno de ejecución. Este repositorio incorpora generación de escenarios, manifiestos de procedencia, conversión de registros y contratos de métricas y evidencia. La demostración presentada produjo tres escenarios reproducibles y convirtió tres archivos sintéticos. Las capacidades descritas se distinguen de las efectivamente ejecutadas en esta revisión.

**Ampliación:** ver `evidencia/auditoria_matb.md` para código y nivel de comprobación. La consola fisiológica del repositorio HRV es un sistema diferente. **Fuentes:** [1]; auditoría técnica y `verificacion_tecnica/resultado_verificacion.json`. **Respaldo:** láminas 7, 9 y 10.

## 3. ¿Qué diferencia las tres condiciones de demanda?

**Respuesta breve, 25–35 s.** Las condiciones cambian parámetros explícitos de tarea: tamaño de la zona de seguimiento, pérdida de recursos y oportunidades de supervisión y comunicación. También varía la frecuencia de sondas ISA. Conservamos esos parámetros en cada manifiesto. La respuesta se estudiará mediante medidas de desempeño y carga percibida, sin asumir equivalencia universal de las etiquetas entre implementaciones.

**Ampliación:** demostración: dificultad 0,20/0,50/0,80; proporción objetivo TRACK 0,80/0,50/0,20; pérdida RESMAN 200/600/1000 unidades/min; sondeo ISA 90/60/45 s. Los recuentos efectivos están en la auditoría. **Fuentes:** [2]; `scenario_builder.py` y resultado de verificación. **Respaldo:** láminas 4 y 8; tabla técnica de apoyo.

## 4. ¿Cómo se distinguen carga mental, desempeño, somnolencia y VFC?

**Respuesta breve, 25–35 s.** El desempeño se observa en respuestas a tareas; NASA-TLX recoge carga percibida; ISA aporta valoración instantánea y KSS, somnolencia subjetiva. La VFC describe variación entre intervalos cardíacos y requiere contexto y control de señal. Son resultados complementarios, con métodos y unidades propios. Una asociación entre ellos se interpreta según el diseño y las condiciones de medición.

**Ampliación:** RTLX resume seis ítems completos; no sustituye TLX ponderado. KSS colombiana publicada [6] es un antecedente específico; equivalencia literal de versión local se revisa separadamente. **Fuentes:** [3,6]; M §§4.1 y 4.7.3; `metrics_spec.json`. **Respaldo:** láminas 8 y 12.

## 5. ¿Cómo se manejan aprendizaje, orden, hora y estación?

**Respuesta breve, 25–35 s.** V cero incluye familiarización y las visitas siguientes mantienen recordatorio de controles. Los niveles se contrabalancean entre participantes. Una rotación distinta distribuye las seis visitas intramisión entre tres franjas y dos estaciones. Conservamos orden basal, identificador, hora y estación reales, además de incidencias, para interpretar las trayectorias y describir cualquier desviación del plan.

**Ampliación:** cada persona pasa una vez por cada combinación hora/puesto; mantener orden de niveles cuando el alias cambia de aspirante a tripulante. El contrabalanceo no elimina por sí solo aprendizaje. **Fuentes:** M §§4.7.1–2 y 4.7.6.3; C §4.1. **Respaldo:** láminas 6, 8 y 11.

## 6. ¿Cómo analizar seis personas por misión y basales a distinta distancia?

**Respuesta breve, 25–35 s.** Priorizaremos trayectorias y contrastes dentro de cada persona, con magnitud e incertidumbre. Los bloques se anidan en visitas y participantes; no aumentan el número de personas independientes. Conservaremos la distancia basal de seis y veintitrés días y las fechas reales. La complejidad del modelo se ajustará a la información disponible y a resultados previamente especificados.

**Ampliación:** misiones secuenciales no son una asignación aleatoria de aislamiento; un modelo parsimonioso debe ser estimable. Evitar múltiples desenlaces principales definidos después de observar resultados. **Fuentes:** M §4.7.4; C §§2 y 4.1; `contexto_astra.md`. **Respaldo:** láminas 6, 11 y 12.

## 7. ¿Qué evidencia corresponde al corte del congreso?

**Respuesta breve, 25–35 s.** Esta versión presenta protocolo y resultados técnicos con corte del veintiuno de septiembre. El calendario ubica el congreso en los días nueve y diez de ASTRA uno, y en premisión para ASTRA dos. Cualquier actualización humana requiere registros de ejecución, revisión de calidad y un corte explícito. V cuatro coincide con el catorce de octubre y depende además de la hora de presentación.

**Ampliación:** para 13oct estarían programadas previamente V0–V3 de A1 y V0 de A2; V5–V7 A1 y visitas intramisión/post A2 son posteriores. Se habla de fechas previstas, no datos adquiridos. **Fuentes:** C §§2, 5.2 y 7; indicaciones CEINNA. **Respaldo:** láminas 6, 10 y 12.

## 8. ¿Cómo se tratan trazabilidad y datos faltantes?

**Respuesta breve, 25–35 s.** Cada resultado conserva vínculo con identidad, visita, condición, escenario y versión de la métrica. Los manifiestos permiten comprobar integridad y los contratos distinguen propósito, calidad y elegibilidad. Los datos ausentes mantienen un motivo, y los cuestionarios incompletos conservan sus ítems disponibles. La inclusión en el análisis sigue reglas explícitas; la mera carga de un archivo no resuelve esa decisión.

**Ampliación:** distinguir CSV heredado de eventos reconciliados. Discriminabilidad observada requiere oportunidades objetivo/no objetivo válidas. Las huellas digitales comprueban archivos, no validez clínica. **Fuentes:** auditoría A2; `scenario_manifest.py`, `evidence/reconcile.py`, `study_analysis_eligibility.py`, `metrics_spec.json`. **Respaldo:** láminas 9 y 10.

## 9. ¿Qué relevancia tiene para factores humanos aeroespaciales?

**Respuesta breve, 25–30 s.** El estudio aporta un procedimiento para observar desempeño y carga percibida durante un ciclo de aislamiento y confinamiento, conservando condiciones repetibles y contexto individual. Su relevancia reside en caracterizar variación humana bajo demandas concurrentes. Las conclusiones se referirán a esta población, este análogo y estas mediciones; la transferencia a otras operaciones requerirá evidencia específica.

**Ampliación:** el hábitat terrestre no reproduce todos los peligros del vuelo espacial. No anticipar prevención de accidentes, selección óptima ni aptitud individual. **Fuentes:** M §§1.2 y 4.7; [1–4]. **Respaldo:** láminas 4, 12 y 13.

## 10. ¿Qué permite reproducir y comparar el estudio?

**Respuesta breve, 25–35 s.** Se conservan versión del software, escenarios, semillas, parámetros, secuencia de bloques y definición de métricas. Las fechas, dispositivos y condiciones reales completan la descripción. Así se puede repetir el procedimiento y examinar diferencias entre implementaciones. Para comparar resultados con otros estudios también hay que considerar población, duración y tareas, además de compartir las etiquetas de demanda.

**Ampliación:** [5] describe USAARL MATB y [1] OpenMATB; su parentesco conceptual no acredita equivalencia de funciones. Replicar archivos no equivale a replicar efectos humanos. **Fuentes:** [1,2,5]; auditoría A2 y manifiestos. **Respaldo:** láminas 9, 10 y 13.

## 11. ¿Qué significa el dato de siete de diecinueve estudios?

**Respuesta breve, 25–30 s.** Es un resultado de la revisión de Pontiggia: de diecinueve publicaciones incluidas, siete describían su configuración con suficiente detalle para replicación o revisión. Se refiere a la documentación metodológica, no al éxito de repetir un efecto. En ASTRA lo traducimos en una decisión concreta: conservar parámetros, versiones y secuencia experimental.

**Ampliación:** el conjunto se seleccionó para comparar niveles de demanda; no representa toda la literatura MATB. La heterogeneidad impidió metaanálisis. **Fuente:** [2], §3 y §3.3. **Respaldo:** lámina 4.

## 12. ¿Qué distingue la integración local de otras implementaciones MATB?

**Respuesta breve, 25–35 s.** Las implementaciones aportan funciones complementarias. OpenMATB proporciona la base abierta; el trabajo local vincula escenarios deterministas, registros y métricas versionadas con un seguimiento longitudinal en ASTRA. El aporte presentado es la trazabilidad de esa conexión. La comparación entre programas se formula mediante preguntas y evidencia específicas, sin inferir superioridad en desempeño humano.

**Ampliación:** NASA/AF se describen según la historia de Vogl; las funciones de USAARL no se atribuyen al código local. **Fuentes:** [1,5] y auditoría MATB. **Respaldo:** láminas 3, 9, 10 y 12.

## 13. ¿RTLX y NASA-TLX ponderado son la misma medida?

**Respuesta breve, 25–35 s.** Comparten seis dimensiones, pero su agregación difiere. El contrato local del ejemplo calcula RTLX como la media no ponderada de seis respuestas completas de cero a diez y la multiplica por diez. NASA-TLX ponderado requiere además comparaciones pareadas. El registro conserva qué versión se calculó y sus reglas; si faltan respuestas, se mantiene el motivo de ausencia del compuesto.

**Ampliación:** la regla de transformación no constituye una validación psicométrica de una traducción local. **Fuentes:** `metrics_spec.json`, `log_converter.py` y auditoría MATB. **Respaldo:** lámina 9.

## Distribución de un simulacro de 3 minutos

Ensayo propuesto: 0:00–0:15 pregunta; 0:15–0:50 respuesta; 0:50–1:05 repregunta; 1:05–1:40 respuesta; 1:40–1:55 tercera pregunta; 1:55–2:30 respuesta; 2:30–3:00 comentarios del comité/cierre. Esta es una pauta temporal, no constancia de ensayo oral humano realizado.
