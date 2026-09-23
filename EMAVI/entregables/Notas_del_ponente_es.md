# Notas del ponente — EMAVI

Pública clasificada · SMSM DIEGO L MALPICA · DIMAE

Guion de referencia: 11:15. El evento EMAVI no tiene un tiempo confirmado; reservar 3:00 adicionales para preguntas. No se ha realizado ensayo humano.

## 1. Apertura institucional — 0 s

Pantalla de apertura; avanzar al aviso de privacidad.

Apoyo y fuentes: Plantilla FAC, diapositiva 1.

## 2. Políticas de privacidad — 0 s

Aviso de información pública clasificada.

Apoyo y fuentes: Plantilla FAC, diapositiva 4; clasificación declarada por el usuario.

## 3. MATB y ASTRA — EMAVI — 20 s

Soy Diego L. Malpica, especialista en Medicina Aeroespacial de la Subdirección Científica Aeroespacial de la DIMAE. Presentaré el diseño de investigación de ASTRA mediante MATB y una demostración de las principales funciones de la aplicación.

Apoyo y fuentes: Autoría reutilizada de CEINNA, confirmada por el investigador.

## 4. Agenda — 20 s

El recorrido conecta la pregunta científica con las medidas, la preparación de tareas y la revisión de evidencia. Al final se presentan el análisis previsto y la siguiente etapa.

Apoyo y fuentes: Estructura de la presentación EMAVI.

## 5. Pregunta y diseño — 45 s

La pregunta central es cómo varían el desempeño multitarea y la carga percibida entre condiciones de demanda y a lo largo de ASTRA. La unidad de seguimiento es la persona, observada en varias visitas y bloques. Separar demanda, desempeño y percepción permite interpretar respuestas diferentes ante una misma tarea. Presentaré el diseño y un recorrido de la aplicación. Las capturas corresponden a una demostración local con registros sintéticos; los datos humanos de las misiones se obtendrán mediante la ejecución del protocolo.

Apoyo y fuentes: CEINNA/guion/diapositivas.md, láminas 4, 11; Manual ASTRA §4.7.

## 6. Fundamento y reproducibilidad — 45 s

Las implementaciones MATB aportan herramientas complementarias. OpenMATB enfatiza personalización y replicabilidad, mientras USAARL documenta transiciones de demanda y automatización adaptativa. La revisión de Pontiggia encontró siete configuraciones suficientemente descritas entre diecinueve estudios. Esa proporción se refiere a la calidad del reporte, no al éxito de replicaciones. La decisión metodológica del proyecto es conservar los parámetros y la secuencia de eventos junto con la versión que los produjo. Así podemos reconstruir la exposición experimental que antecede a cada resultado.

Apoyo y fuentes: [1] Cegarra et al., 2020; [2] Pontiggia, Gomez-Mérino et al., 2024, §3; [5] Vogl et al., 2024. Lectura documentada en CEINNA/evidencia/lectura_comparativa_y_aportes.md.

## 7. ASTRA: seguimiento longitudinal — 50 s

ASTRA contempla dos misiones secuenciales, con hasta seis personas previstas en cada una. El seguimiento incluye una visita basal, seis visitas intramisión y una posterior al egreso. Cada visita reserva noventa minutos y contiene tres escenarios de quince minutos, además de preparación y pausas. El orden de las condiciones se contrabalancea. LOW, MEDIUM y HIGH identifican preajustes de ingeniería cuya relación con la respuesta humana requiere calibración. En el análisis se conservarán las fechas reales, el horario, la estación y la distancia respecto a la evaluación basal.

Apoyo y fuentes: CEINNA/fuentes/Manual_de_Operaciones_ASTRA_2026.md §4.7; CEINNA/fuentes/Cronograma_ASTRA_1_y_2_2026.md. Diseño previsto, no ejecución constatada.

## 8. Qué se mide en cada bloque — 45 s

Las cuatro tareas aportan medidas específicas. La supervisión de sistemas registra detecciones y omisiones; el seguimiento registra desviación del objetivo; comunicaciones y gestión de recursos aportan sus propias respuestas. KSS describe somnolencia subjetiva antes del bloque, ISA recoge autoevaluación durante la tarea y NASA-TLX caracteriza carga percibida después. La interpretación exige conservar la definición y la unidad de cada métrica. El recorrido que sigue muestra cómo la aplicación organiza la preparación, la ejecución y la revisión de estas observaciones.

Apoyo y fuentes: [1] Cegarra et al., 2020; [6] Laverde-López et al., 2022; CEINNA/evidencia/auditoria_matb.md; matb_integration/metrics_spec.json.

## 9. Adquisición fisiológica — 30 s

ASTRA incluye una línea fisiológica propia. Polar H10 puede aportar intervalos R–R cuando se verifica la ruta de captura; ActiGraph registra movimiento y actividad. La variabilidad cardíaca se calcula después de revisar calidad, cobertura y sincronización. La demostración de EMAVI solo presenta preparación y requisitos; no conectó sensores ni registró señales humanas.

Apoyo y fuentes: Manual ASTRA v2.5, adquisición fisiológica; matb_integration/physiology/contracts.py y analysis.py; EMAVI/video/ALCANCE_Y_VERIFICACION.md, Polar H10. Ilustración conceptual generada con IA, no evidencia.

## 10. Demostración — 0 s

Comienza el recorrido por capturas reales. La demostración no requiere conexión durante la presentación.

Apoyo y fuentes: Capturas locales; base de demostración aislada.

## 11. Elegir una actividad — 35 s

La entrada del participante reúne las actividades disponibles. Cada opción describe qué hará la persona, qué equipo necesita y cómo interpretar el resultado. El propósito de la sesión se declara antes de continuar: práctica o participación en un estudio. Esta distinción acompaña el registro y permite revisar después a qué procedimiento pertenece. La captura muestra el catálogo real de la consola; la disponibilidad de cada componente depende de la instalación local.

Apoyo y fuentes: webui/frontend/src/app/start/page.tsx; README.es.md, identidad y propósito.

## 12. Diseñar el escenario — 40 s

El diseñador permite revisar la distribución temporal de tareas y eventos. En esta demostración se compila un escenario breve con una semilla explícita. La aplicación presenta restricciones de diseño y las huellas del escenario y de su especificación. Estos identificadores sirven para reconocer qué configuración se ejecutó. La compilación verifica contratos de software; la calibración de demanda en personas requiere un procedimiento experimental independiente.

Apoyo y fuentes: webui/frontend/src/components/experiments/ExperimentDesigner.tsx; webui/frontend/src/lib/experiment-designer.ts.

## 13. Preparar OpenMATB — 35 s

La preparación de OpenMATB conecta el escenario con el entorno de tareas de escritorio. La vista previa permite revisar cómo se organizan los paneles antes de iniciar una sesión. Es necesario distinguir esta preparación en el navegador de la presentación efectiva de estímulos y la captura en OpenMATB. La apariencia forma parte del contexto de medición y debe conservarse junto con el resto de parámetros cuando se comparan sesiones.

Apoyo y fuentes: webui/frontend/src/app/openmatb/appearance/page.tsx; componentes AppearanceWorkbench; README.es.md.

## 14. Somnolencia y vigilancia — 35 s

La secuencia KSS y PVT registra primero la somnolencia percibida y después presenta las instrucciones de vigilancia. En la pantalla se utiliza un código sintético creado para esta demostración. Este ejemplo ilustra cómo se conserva el orden de administración y se vincula la actividad con una ocasión de medición. El PVT constituye una actividad adicional de vigilancia; su resultado debe interpretarse dentro del protocolo y de la calidad temporal documentada.

Apoyo y fuentes: webui/frontend/src/app/pvt/page.tsx; webui/frontend/e2e/participant-journey.spec.ts; [6] para KSS.

## 15. Supervisar una misión — 40 s

El módulo sUAS ofrece una tarea distinta, centrada en supervisión de una misión sintética. El investigador puede observar el mapa, la flota y las alertas, mientras el sistema registra los eventos. La captura corresponde al modo técnico y conserva esa identificación en pantalla. Es una demostración del entorno de supervisión. Su relación con el rendimiento en personas y su comparabilidad con las tareas OpenMATB requieren diseños específicos.

Apoyo y fuentes: webui/frontend/e2e/technical-test.spec.ts; webui/frontend/src/app/mission/test/page.tsx; README.es.md.

## 16. Revisar la evidencia — 40 s

La revisión comienza con los archivos que documentan la captura. El paquete pareado reúne manifiestos, eventos y observaciones temporales. La consola permite abrir una métrica y seguir los eventos que contribuyen a su cálculo. En esta demostración se utiliza el generador sintético de referencia del repositorio. Esta trazabilidad permite comprobar reglas y transformaciones sin presentar sus valores como resultados de participantes.

Apoyo y fuentes: webui/frontend/e2e/evidence.spec.ts; matb_integration/evidence/reference.py.

## 17. Del evento al resultado — 40 s

La inspección a nivel de evento muestra de dónde procede un resultado y cuál es su base temporal. Cuando una métrica requiere evidencia adicional, la aplicación mantiene visibles los motivos de elegibilidad. El paquete exportable permite revisar integridad y recomputación fuera de la consola. Este paso conecta el registro original con la interpretación científica y facilita detectar diferencias entre una observación de software y el inicio físico de un estímulo.

Apoyo y fuentes: webui/frontend/e2e/evidence.spec.ts; matb_integration/evidence; docs/research/qualification-workflow.md.

## 18. Del registro al análisis longitudinal — 50 s

La cadena de análisis parte del escenario y conserva la relación entre manifiestos, eventos y métricas. Un ejemplo es RTLX: con seis respuestas completas de cero a diez, se calcula la media y se multiplica por diez para obtener el índice de cero a cien. El análisis longitudinal organiza esas observaciones por persona, visita, bloque y condición. Antes de comparar trayectorias se revisan la calidad, los datos faltantes y la elegibilidad. Los valores de demostración mostrados en la consola no se incorporan al estudio.

Apoyo y fuentes: CEINNA/guion/diapositivas.md, láminas 9 y 11; matb_integration/log_converter.py; docs/research/scientific-foundation-v2.md.

## 19. Estado de la evidencia y siguiente etapa — 45 s

El paquete CEINNA documentó verificaciones técnicas de generación, integridad y conversión con datos sintéticos. Esta presentación añade un recorrido visual de interfaces reales. Las clases de evidencia conservan sus preguntas: reproducibilidad del software, temporización física del equipo, respuesta humana y estabilidad entre sesiones. Cada una requiere su propio procedimiento. La siguiente etapa del estudio es ejecutar las visitas previstas y analizar las observaciones con sus condiciones de adquisición y calidad.

Apoyo y fuentes: CEINNA/evidencia/verificacion_tecnica/resultado_verificacion.json: ejecución histórica del 21-09-2026, commit fd5e1318; revisión EMAVI identificada por su propio commit y fecha.

## 20. Conclusiones — 40 s

El diseño conecta cuatro elementos: una demanda documentada, un registro trazable, métricas explícitas y seguimiento de cada persona. La consola facilita organizar ese proceso desde la preparación hasta la revisión. ASTRA aporta el contexto longitudinal donde se estudiará la respuesta multitarea. La demostración deja visibles los pasos y la procedencia necesarios para interpretar después los datos del estudio.

Apoyo y fuentes: Síntesis del diseño y del recorrido de la aplicación; no inferencia sobre eficacia o validez clínica.

## 21. Referencias I — 10 s

Las referencias completas y su aplicación están disponibles en el documento de apoyo.

Apoyo y fuentes: Referencias_APA.md, referencias 1–3; verificación heredada de CEINNA.

## 22. Referencias II — 10 s

Estas fuentes sustentan las tareas, las decisiones metodológicas y las medidas complementarias.

Apoyo y fuentes: Referencias_APA.md, referencias 4–6; verificación heredada de CEINNA.

## 23. Aviso antes del cierre — 0 s

El aviso de privacidad se reitera antes del cierre institucional.

Apoyo y fuentes: Plantilla FAC, diapositiva 4.

## 24. Cierre institucional — 0 s

Espacio para preguntas.

Apoyo y fuentes: Plantilla FAC, diapositiva 12.
