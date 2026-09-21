# Revisión científica independiente — A6

> Registro de la primera versión. La ampliación posterior se documenta en revision_ampliacion_cientifica.md, revision_visual_ampliada.md y verificacion_final.json. Las cifras de guion y tiempos de esta revisión inicial se conservan como historial.

Fecha: 21-09-2026. Objeto revisado: texto visible y duraciones definidos en `construccion/build_presentation.ps1`; contraste con `evidencia/contexto_astra.md`, `evidencia/matriz_afirmaciones.csv`, `evidencia/auditoria_matb.md` y artefactos técnicos. Esta revisión evalúa contenido científico; la inspección visual y la comprobación de notas corresponden a controles diferenciados.

## Dictamen sobre el guion visible

La secuencia pregunta → diseño → medición → trazabilidad → resultados técnicos → análisis e interpretación es científicamente coherente. Expresa una investigación prospectiva y resultados de desarrollo; no presenta respuestas humanas, significación estadística ni predicción individual inventadas. Las tres condiciones se describen como demanda experimental. No se identificaron afirmaciones graves incompatibles con la evidencia revisada.

Los ajustes puntuales del registro siguiente mejoraron la precisión y quedaron resueltos en las lecturas posteriores documentadas abajo. Las notas y el banco de preguntas se revisaron en la segunda lectura. Este dictamen no equivale a un ensayo oral cronometrado ni a una aprobación de renderizados.

## Registro de hallazgos y acciones

| ID | Lámina | Hallazgo | Acción concreta | Gravedad |
|---|---:|---|---|---|
| C01 | 5 | «6 participantes previstos por misión» expresa objetivo de muestra; el documento fuente fija hasta seis sujetos a elegibilidad. | Usar «Hasta 6 participantes previstos por misión». | Precisión |
| C02 | 10 | La ejecución convirtió tres archivos CSV, cada uno con múltiples filas, a tres registros de métricas. «Tres registros CSV» puede confundirse con tres filas. | Usar «tres archivos CSV sintéticos convertidos». | Precisión |
| C03 | 12 | Aprendizaje no tiene la misma condición de registro directo que horario o distancia temporal. | Usar «Se consideran aprendizaje, horario y distancia entre visitas». Describir familiarización y repetición como contexto del análisis en notas. | Precisión |
| C04 | 2/primer uso | MATB está en el título y no se desarrolla en texto visible; ASTRA sí está definido. | Definir oralmente y en notas: Multi-Attribute Task Battery, batería multitarea; definir KSS, ISA y NASA-TLX al presentar mediciones. | Claridad |
| C05 | 11–12 | La lámina presenta análisis intrapersonal adecuado; el número máximo de personas y ausencia de control externo deben acompañar la interpretación oral. | Notas: máximo previsto 12 personas; bloques anidados no son participantes independientes; enfoque descriptivo y modelo parsimonioso según información disponible; no atribuir cambios exclusivamente al aislamiento. | Respaldo interpretativo |
| C06 | 8 | Se distingue 900 s de escenario y reserva de 90 min. Conviene conservar explícitamente el efecto de los cuestionarios sobre el reloj. | Notas: pausas/cuestionarios modifican tiempo real; registrar duración y no tratarla como exposición activa idéntica. | Respaldo interpretativo |
| C07 | 14–15 | El script carga referencias de JSON aún no disponible al inicio de la revisión. | Verificar referencias efectivamente insertadas y al menos cinco citas de 2020–2025 en entrega final. La matriz incluye seis fuentes de ese intervalo. | Comprobación final |

Los hallazgos C01–C03 se comunicaron al coordinador para corrección del guion. A6 no modificó el script de construcción.

## Verificaciones por dominio

**Duración.** Vector de tiempos: 0, 20, 10, 50, 50, 75, 60, 60, 70, 75, 65, 60, 75, 10, 10, 0 segundos. Suma: **690 s = 11:30**, dentro de 12:00, con margen de 0:30. Los tres minutos del comité quedan fuera de la exposición. Los tiempos son asignaciones, no duración observada del habla; las transiciones institucionales deben consumir parte del margen en el ensayo.

**Planificación.** Láminas 5–6 señalan participantes y fechas previstos. V0 29/28 septiembre, V7 20 octubre/5 noviembre y distancias D−6/D−23 coinciden con el informe A1. DM2/4/7/10/13/15 se conserva correctamente. La cronología representa una secuencia de visitas con espaciado gráfico uniforme; no debe interpretarse como escala temporal proporcional.

**Tareas y medición.** Las cuatro tareas coinciden con OpenMATB y los plugins del repositorio. La captura está rotulada documental y en francés; no se presenta como una sesión ASTRA ni como interfaz española ejecutada. Las escalas se asocian a momentos y constructos distintos. El texto no afirma validación de la traducción local ni equivalencia entre NASA MATB-II, OpenMATB y esta modificación.

**Resultado técnico.** Lámina 10 describe tres escenarios de 900 s, reproducción idéntica, SHA-256 y conversión. Está sustentada por `resultado_verificacion.json`, `verificar_demo.py`, escenarios/manifiestos y `metricas_sinteticas.json`. La etiqueta «Demostración técnica con datos sintéticos» es visible. No afirma ejecución gráfica, adquisición de eventos v3, medidas físicas, rendimiento humano ni ajuste DEPDF; ninguno se ejecutó en esa demostración. Fecha y commit coinciden. Mantener esta delimitación en las notas.

**Trazabilidad.** Lámina 9 describe capacidades localizadas en código y contrato; la verificación sintética demuestra solo parte de la cadena. Las notas deben distinguir implementación inspeccionada de ejecución realizada. El manifiesto, propósito de captura, fuente y reglas de elegibilidad se conservan como capas independientes. Los datos ausentes y valores no aplicables no se imputan a cero.

**Fuentes.** Cegarra 2020 respalda estructura y configurabilidad de OpenMATB. Pontiggia 2024 revisión respalda heterogeneidad de parametrizaciones; el experimento de Pontiggia 2024 aporta evidencia sobre mediciones complementarias bajo sus condiciones. Tortello 2020 da contexto de seguimiento ambiental, con tarea y duración diferentes; Vogl 2024 describe otra implementación y justifica documentar versiones. No se usa ninguna de esas referencias como validación automática de ASTRA o de modificaciones locales. Manual y cronograma sostienen planificación; el código y los artefactos sostienen implementación y ejecución.

**Narrativa.** Lenguaje positivo, de investigación y sin superlativos comerciales. No se afirma causalidad, aptitud, diagnóstico, beneficio operacional ni éxito de ambas misiones. El corte «protocolo y desarrollo documentado» respeta la temporalidad de septiembre y del Congreso de octubre. La fisiología se menciona como variable separada, sin inferir estrés o fatiga desde un único índice.

## Criterios oficiales

| Criterio | Cobertura observada |
|---|---|
| Dominio temático | Constructos separados, cuatro tareas, diseño y fuentes pertinentes. |
| Nivel de desarrollo | Demostración técnica fechada y reproducible; implementación diferenciada de resultados humanos. |
| Impacto y relevancia | Pregunta sobre evolución intrapersonal en aislamiento y confinamiento; contribución metodológica concreta. |
| Comunicación | Secuencia de una idea por lámina; tiempo asignado 11:30. Claridad oral se revisará con notas. |
| Respuesta al comité | Diez respuestas revisadas y simulacro documental de 180 s en `simulacro_comite.md`; no constituye ensayo oral humano. |

## Segunda lectura: notas, referencias y banco del comité

Se revisaron íntegramente `guion/notas_data.json`, `guion/preguntas_comite.md`, `guion/ensayo_estimado.csv`, `construccion/referencias_slide.json` y el texto exportado `construccion/diapositivas_texto.json`. Se confirma definición de MATB y escalas, separación entre guion hablado y notas de apoyo, muestra máxima de 12 personas, anidamiento, estimabilidad de modelos, datos faltantes, contexto fisiológico y atribución causal limitada. Los tiempos y ritmos se identifican expresamente como estimación textual, no ensayo humano.

| Hallazgo inicial | Estado tras segunda lectura | Evidencia |
|---|---|---|
| C01 | Resuelto | Texto exportado lámina 5: «Hasta 6 participantes previstos por misión». |
| C02 | Resuelto | Texto exportado lámina 10: «tres archivos CSV sintéticos convertidos». |
| C03 | Resuelto en lámina y notas | Lámina 12 usa «Se consideran»; guion oral final distingue documentar familiarización y considerar aprendizaje. |
| C04 | Resuelto | Lámina 2 define MATB en oral/apoyo; 5 define ASTRA; 7 tareas; 8 KSS, ISA, NASA-TLX, RTLX; 12 VFC/HRV. |
| C05 | Resuelto | Notas 11: hasta 12 personas, no independencia de bloques, preespecificación, modelo parsimonioso; oral 12 delimita causalidad. |
| C06 | Resuelto | Oral 8 diferencia 900 s de escenario y duración real, con pausas por cuestionarios. |
| C07 | Resuelto | Referencias 1–5, años 2020/2024, realmente citadas en cuerpo y notas; seis referencias 2020–2025 insertadas en 14–15. KSS [6] como complemento sin atribuir equivalencia local automática. |

Precisiones comunicadas al coordinador en esta lectura: (1) notas 10 deben citar `ejecucion_generador.txt` y `ejecucion_verificacion.txt`; `ejecucion_demo.txt` corresponde a un intento ampliado fallido por dependencia `yaml`; (2) el recorrido técnico verifica por separado generación de escenarios y conversión de fixtures, por lo que se recomienda esa expresión en vez de sugerir respuestas adquiridas de los escenarios; (3) en oral 12, «se documentarán familiarización, horario y distancia entre visitas, y se considerará el aprendizaje».

**Cierre de correcciones:** se cotejaron las tres precisiones en `notas_data.json` y `notas_del_ponente.md`: referencias corregidas a los dos registros exitosos, generación y conversión explícitamente separadas, nota que identifica los CSV como fixtures independientes y redacción sobre aprendizaje corregida. C01–C07 y estas tres precisiones quedan **resueltos**. No quedan hallazgos científicos abiertos dentro del alcance de esta revisión. El conteo final de `ensayo_estimado.csv` confirma **1229 palabras orales y 690 s asignados**, más 180 s separados para el comité.

El banco cubre las diez preguntas con fuentes y respaldo pertinentes. Se estimaron sus duraciones mediante conteo de palabras, sin reproducción de audio ni ensayo humano: las diez respuestas breves caben individualmente en 20–40 s a 100–120 palabras/min. Tres respuestas, junto con preguntas y comentarios, forman la pauta de 180 s documentada en `simulacro_comite.md`; no se pretende responder las diez en tres minutos.
