from pathlib import Path
import csv

root = Path(__file__).resolve().parents[1]
def write(name, text):
    (root / name).write_text(text, encoding='utf-8')

write('README.md', '''# ASTRA y MATB — III CEINNA 2026

**Presentación terminada y revisada · 21 de septiembre de 2026 · Español.**

SMSM DIEGO L MALPICA
Especialista en Medicina Aeroespacial
Subdirección Científica Aeroespacial – DIMAE

## Entregables

- [Presentación editable PowerPoint](entregables/ASTRA_MATB_III_CEINNA_es.pptx)
- [Presentación PDF](entregables/ASTRA_MATB_III_CEINNA_es.pdf)
- [Notas del ponente](entregables/Notas_del_ponente_es.md)
- [Preguntas y respuestas del comité](entregables/Preguntas_y_respuestas_del_comite.md)
- [Referencias APA](entregables/Referencias_APA.md) y [glosario](entregables/Glosario.md)
- [Informe de verificación](entregables/Informe_de_verificacion.md)

La presentación contiene 16 diapositivas, incluidas las láminas institucionales de apertura y cierre. Conserva la plantilla suministrada, su formato 16:9, tipografía Bell MT, emblemas, franja y lema. El contenido desarrolla la pregunta, el diseño longitudinal, las mediciones, la trazabilidad, los resultados técnicos y la interpretación científica.

El guion programa **11:30 de exposición**, deja **0:30 de margen** dentro del límite de 12 minutos y reserva **3:00 para preguntas**. Las notas contienen 1229 palabras de exposición. Una lectura sintética local duró 9:41 sin pausas añadidas; las 14 láminas con discurso caben individualmente en su ventana. No se realizó un ensayo humano cronometrado.

Se leyeron íntegramente los dos Markdown adjuntos y se auditó el repositorio. Scite y las fuentes primarias respaldan seis referencias de 2020–2025. La figura de hábitat creada con imagegen está identificada como ilustración conceptual; la captura de OpenMATB procede de la documentación del repositorio. Los resultados presentados son comprobaciones técnicas de generación, reproducción y conversión de archivos sintéticos. ASTRA se describe conforme a su programación; el paquete no contiene resultados humanos de las misiones.

## Evidencia y revisión

- [Conciliación documental](evidencia/conciliacion_documental.md), [contexto ASTRA](evidencia/contexto_astra.md) y [auditoría MATB](evidencia/auditoria_matb.md).
- [Matriz de afirmaciones](evidencia/matriz_afirmaciones.csv) y [búsquedas Scite](evidencia/busquedas_scite.md).
- [Revisión científica](revision/revision_cientifica.md), [bibliográfica](revision/revision_bibliografica.md) y [visual](revision/revision_visual.md).
- [Verificación final](revision/verificacion_final.json) y [correcciones](revision/registro_correcciones.md).
- [Plan implementado](PLAN_DE_PRESENTACION.md) y [encargos ejecutados](ENCARGOS_PARA_AGENTES.md).

Las tres copias de los adjuntos conservan sus SHA-256 originales, registrados en [fuentes/manifest.json](fuentes/manifest.json). La revisión final comprobó 16 páginas PDF, 16 diapositivas con notas, cero relaciones internas rotas y cero desbordamientos detectados. Se inspeccionaron visualmente todas las láminas.

## Reproducción local

Requiere Windows, PowerPoint de escritorio, Python y pdftotext. Ejecutar desde la raíz del repositorio; la exportación usa PowerPoint COM.

```powershell
& .\\CEINNA\\construccion\\build_presentation.ps1
& .\\CEINNA\\construccion\\ensayo_sintetico.ps1
pdftotext -layout .\\CEINNA\\entregables\\ASTRA_MATB_III_CEINNA_es.pdf .\\CEINNA\\revision\\texto_pdf.txt
python .\\CEINNA\\construccion\\finalizar_paquete.py
```

La entrega Git se limita a CEINNA en el repositorio privado strikerdlm/MATB, por solicitud del investigador. No se ha enviado material al Congreso. Los audios WAV regenerables y la copia intermedia del PowerPoint se excluyen mediante .gitignore; se conservan sus informes. La ejecución no modificó el software MATB.
''')

p = root / 'PLAN_DE_PRESENTACION.md'
s = p.read_text(encoding='utf-8')
s = s.replace('**Versión:** 1.1 · **Fecha:** 2026-09-21 · **Estado:** lista para asignación de agentes; producción pendiente.', '**Versión:** 1.2 · **Fecha:** 2026-09-21 · **Estado:** implementado; PPTX, PDF y paquete de apoyo entregados.\n\nEste documento conserva el diseño de trabajo y sus criterios originales. El estado comprobado de ejecución consta en [Informe de verificación](entregables/Informe_de_verificacion.md); las listas de control siguientes son especificaciones del plan, no un registro actualizado de pendientes.')
s = s.replace('Volver a verificar al iniciar producción.', 'Verificada durante la producción.')
s = s.replace('El trabajo actual termina con este plan. El lanzamiento de agentes para producir los materiales, el uso de Scite y la generación de imágenes corresponden a la siguiente fase.', 'El plan fue implementado mediante lectura documental, auditoría del repositorio, investigación con Scite, generación conceptual con imagegen, construcción desde la plantilla y revisiones independientes. La autoría y afiliación corresponden a la confirmación expresa del investigador.')
s = s.replace('Las carpetas de producción y los entregables finales aún no existen.', 'Las carpetas de producción y los entregables finales están disponibles; consultar README.md para el inventario efectivo.')
s = s.replace('No se requiere resolver estos pendientes para entregar este plan. Sí deben resolverse o quedar reflejados honestamente antes de declarar lista la presentación correspondiente.', 'Estos asuntos se conciliaron durante la implementación; las decisiones y límites de la entrega se documentan en evidencia/conciliacion_documental.md y entregables/Informe_de_verificacion.md.')
p.write_text(s, encoding='utf-8')
p = root / 'ENCARGOS_PARA_AGENTES.md'
s = p.read_text(encoding='utf-8').replace('**Estado:** instrucciones preparadas; agentes de producción aún no iniciados.', '**Estado:** encargos ejecutados: contexto, auditoría técnica, bibliografía, guion, construcción, ilustración y revisiones independientes completados. A0 integró los entregables; los agentes de contexto, auditoría y evidencia asumieron también las revisiones asignadas.')
s = s.replace('Los nombres de archivos siguientes son **salidas de producción previstas**, no archivos ya entregados.', 'Los nombres de archivos siguientes conservan el mapa original de responsabilidades. El inventario efectivo de la entrega figura en README.md y en entregables/Informe_de_verificacion.md.')
p.write_text(s, encoding='utf-8')
p = root / 'auditoria/INSUMOS_Y_DECISIONES.md'
s = p.read_text(encoding='utf-8')
s = s.replace('**Fecha:** 2026-09-21. Esta es una inspección para formular el plan, no la auditoría científica terminada.', '**Fecha:** 2026-09-21. Registro histórico de la inspección inicial para formular el plan. Sus estados pendientes describen esa etapa, no la entrega actual. La lectura integral, investigación, ejecución técnica y revisión visual se completaron posteriormente; consultar el [informe final](../entregables/Informe_de_verificacion.md). El fallo inicial de PowerPoint COM se resolvió mediante la ejecución autorizada en el entorno de escritorio.')
p.write_text(s, encoding='utf-8')

rows = list(csv.DictReader((root/'evidencia/discrepancias_astra.csv').open(encoding='utf-8-sig')))
lines = ['# Conciliación documental para la presentación', '', 'Fecha de corte: 21 de septiembre de 2026. Las decisiones siguientes fijan el alcance del discurso y no modifican los documentos operativos ni el software. Las fuentes y localizadores completos se conservan en [discrepancias_astra.csv](discrepancias_astra.csv), y su comprobación técnica en [auditoria_matb.md](auditoria_matb.md).', '', '| ID | Asunto | Decisión aplicada al discurso |', '|---|---|---|']
for row in rows:
    lines.append(f"| {row['id']} | {row['asunto']} | {row['decision_para_presentacion']} |")
lines += ['', '## Cierre de la conciliación', '', '- Se adoptó la secuencia V0, DM2/4/7/10/13/15 y V7 D+1. Las fechas se presentan como previstas; la cronología gráfica declara que no está a escala temporal.', '- Cada bloque tiene 900 segundos programados de escenario; la reserva individual es de 90 minutos. Cuestionarios y pausas afectan el tiempo de reloj.', '- La auditoría sustenta las unidades y el contrato metrics_v2: RTLX requiere seis componentes válidos; la ponderación exige sus comparaciones y d′ exige oportunidades observadas explícitas. Completitud y elegibilidad de evidencia se tratan por separado.', '- El discurso se centra en cuatro tareas OpenMATB. No atribuye a la demostración automatización operativa, despliegue de estaciones, alias de identidad, adquisición fisiológica externa o validación predictiva.', '- Se indican hasta seis participantes por misión y hasta doce en total; 15 jornadas inclusivas y 14 noches. Se consideran aprendizaje, horario, distancia entre visitas y procedencia del sueño previo. Los bloques repetidos no son participantes independientes.', '- La generación/reproducción de escenarios y la conversión de CSV sintéticos son comprobaciones separadas. Los archivos de conversión no son respuestas obtenidas por ejecutar los escenarios.', '- El corte del Congreso coincide con DM9/DM10 de ASTRA 1 y premisión de ASTRA 2 según la programación. Se comunican diseño y resultados técnicos; no resultados humanos de misión.', '- Las variantes MATB de las publicaciones no se consideran equivalentes automáticamente. La referencia colombiana de KSS se verificó en la publicación original; no se afirma identidad literal entre esa versión y el texto del software.', '- Se aplican 12 minutos de exposición y 3 de preguntas. La autoría y afiliación se fijaron según la confirmación expresa del investigador.', '', 'Las 17 discrepancias quedan tratadas para el alcance de esta presentación. Las decisiones no constituyen una aprobación operativa de los protocolos de misión.']
write('evidencia/conciliacion_documental.md', '\n'.join(lines)+'\n')

write('revision/registro_correcciones.md', '''# Registro de correcciones y cierre

Fecha: 21 de septiembre de 2026.

| Dominio | Corrección | Comprobación |
|---|---|---|
| Exportación | Resolver acceso de PowerPoint COM en entorno de escritorio autorizado | PPTX, PDF y 16 PNG exportados |
| Identificación | Incorporar ponente, especialidad y afiliación confirmados; corregir metadatos | Texto y propiedades finales inspeccionados |
| Geometría | Restaurar alturas tras aplicar fuentes; ajustar cajas de láminas 9 y 10 | Cero desbordamientos detectados y revisión visual |
| Ciencia C01–C07 | Precisar capacidad de muestra, archivos CSV, aprendizaje, siglas, anidamiento, tiempo de reloj y bibliografía | Revisión científica independiente cerrada |
| Trazabilidad | Corregir fuentes de la nota 10 y separar generación de escenarios de conversión de fixtures | Evidencia de ejecución exitosa y notas finales |
| Cronología | Declarar separación gráfica no proporcional al tiempo, lámina 6 | Render final revisado |
| Tipografía | Evitar separación del nombre NASA‑TLX, lámina 8 | Render final revisado |
| Bibliografía | Verificar autores de KSS y DOI; precisar alcance de las seis fuentes | Revisión bibliográfica independiente |
| Ritmo | Acortar transición oral de lámina 15 | Las 14 lecturas sintéticas caben en sus ventanas |

Se revisaron las 16 diapositivas individualmente y se reinspeccionaron las láminas 6, 8, 9 y 10 después de sus últimos ajustes. Las notas integradas corresponden al guion final. La comprobación estructural detectó cero relaciones rotas; las tres copias originales conservaron sus hashes. La lectura sintética es un control de ritmo y no un ensayo humano.
''')

write('entregables/Informe_de_verificacion.md', '''# Informe de verificación — ASTRA/MATB, III CEINNA 2026

**Fecha de corte:** 21 de septiembre de 2026. **Estado:** producción y revisión completadas.

**Ponente:** SMSM DIEGO L MALPICA, Especialista en Medicina Aeroespacial. Subdirección Científica Aeroespacial – DIMAE.

## Producto y formato

Se entregan PowerPoint editable, PDF, notas del ponente, banco de diez preguntas con respuestas, glosario y referencias APA. La presentación utiliza la plantilla adjunta mediante duplicación de sus láminas; conserva formato 16:9, Bell MT, emblemas, franja y lema. Contiene 16 diapositivas y 16 páginas PDF, con notas integradas en el PowerPoint. Los diagramas de diseño y trazabilidad son editables.

Se leyeron íntegramente el manual y el cronograma adjuntos, se auditó el repositorio en `fd5e1318dc6f036b538dd36ed3c5fe42ad8be7d0` y se documentaron 17 asuntos de conciliación. Los tres originales permanecen sin cambios, con SHA-256 coincidentes. La [conciliación documental](../evidencia/conciliacion_documental.md) establece las decisiones de alcance.

## Ciencia y evidencia

El contenido presenta pregunta, diseño longitudinal, condiciones de demanda parametrizadas, mediciones, trazabilidad, comprobaciones técnicas y análisis previsto. Mantiene lenguaje de investigación en positivo y sin marketing. ASTRA se presenta conforme a su programación; no se atribuyen resultados humanos o validaciones no observados.

La demostración técnica generó tres escenarios de 900 segundos, comprobó sus hashes y reproducción determinista, y convirtió tres CSV sintéticos a métricas. La generación de escenarios y la conversión son comprobaciones independientes; los CSV no son registros humanos ni respuestas obtenidas al ejecutar esos escenarios. No se realizó una sesión gráfica en vivo. La captura documental se identifica con su procedencia y no demuestra un despliegue de misión.

Scite y las publicaciones primarias sustentan seis referencias de 2020–2025, de las cuales cinco sostienen el núcleo argumental y una complementa KSS. Se verificaron autores, año, DOI y alcance. La ausencia de avisos devueltos por Scite no se interpreta como garantía de ausencia de correcciones editoriales. Los detalles constan en la [revisión bibliográfica](../revision/revision_bibliografica.md).

La ilustración del hábitat se produjo con imagegen y está rotulada como conceptual, generada con IA y no como fotografía de ASTRA. No se emplearon imágenes generadas como datos ni resultados empíricos. Los activos y su procedencia están en [registro_activos.csv](../visuales/registro_activos.csv).

## Tiempo y preparación oral

- Exposición programada: **690 segundos = 11:30**.
- Margen hasta el límite oficial de 12 minutos: **30 segundos**.
- Preguntas y comentarios: **180 segundos**, separados de la exposición.
- Guion oral: **1229 palabras**.
- Lectura sintética local: **581,35 segundos = 9:41,35**, sin pausas añadidas; las 14 láminas con discurso caben en sus ventanas individuales.

La lectura sintética no sustituye el ensayo humano del ponente; no se realizó un ensayo oral humano cronometrado. El banco de diez preguntas prepara alternativas de respuesta, no una secuencia que deba contestarse completa en tres minutos. La documentación de revisión relaciona el discurso y las respuestas con los cinco criterios oficiales del Congreso.

## Controles finales

| Control | Resultado |
|---|---|
| Diapositivas / notas / páginas PDF | 16 / 16 / 16 |
| Notas finales presentes en el archivo | Comprobado |
| Relaciones internas rotas | 0 |
| Desbordamientos geométricos detectados | 0 |
| Referencias de 2020–2025 | 6 |
| SHA-256 de adjuntos conservados | 3 de 3 |
| Identificación del ponente y metadatos | Comprobados |
| Revisión visual independiente | 16 láminas; revisión posterior de 6, 8, 9 y 10 |
| Revisión científica y bibliográfica | Hallazgos tratados y documentados |

La verificación automática es complementaria a la inspección visual. Consultar [verificacion_final.json](../revision/verificacion_final.json), [revisión científica](../revision/revision_cientifica.md), [revisión visual](../revision/revision_visual.md) y [registro de correcciones](../revision/registro_correcciones.md).

## Alcance de la entrega

La implementación del plan está concluida para esta presentación. Los scripts permiten regenerar el paquete en Windows con PowerPoint de escritorio. La investigación prospectiva y la comprobación del software se distinguen explícitamente; el paquete no anticipa resultados de participantes ni constituye validación clínica u operacional. La entrega Git del paquete CEINNA al repositorio privado strikerdlm/MATB fue solicitada por el investigador. No se ha enviado material al Congreso. Se excluyen audios regenerables y la copia intermedia del PowerPoint; sus informes se conservan. No se modificó el software MATB.
''')
print('Documentación de cierre actualizada.')
