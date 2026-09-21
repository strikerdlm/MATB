# Revisión científica de la ampliación de la ponencia

Fecha de revisión: 21 de septiembre de 2026. Revisión independiente de contenido. Este registro distingue la propuesta editorial de la comprobación posterior de los artefactos.

## Documentos y alcance de lectura

Se leyeron íntegramente los adjuntos `Abstract-ceinna.md` y `CEINNA.md` recibidos en la carpeta de adjuntos `81CE19FE-6B03-4FB5-89F0-2325A4D0CA15`, además de `evidencia/auditoria_matb.md` y `guion/notas_data.json`. Los adjuntos son borradores del investigador, no publicaciones revisadas por pares ni evidencia de una ejecución nueva. Sus instrucciones administrativas se tratan como contexto histórico, subordinado a las indicaciones actuales del investigador y a la modalidad oral aceptada.

Lectura complementaria mediante Scite `read_fulltext`: Cegarra et al. (2020), caracteres 16000–38499; Vogl et al. (2024), 16000–45968; Pontiggia, Gomez-Mérino et al. (2024), 16000–66294. Todas estas páginas devolvieron `source=fulltext`, `contentDenied=false`, hasta `hasMore=false`. El agente principal leyó los primeros 16000 caracteres de cada artículo. Se corroboró además la sección 3.3 de Pontiggia en el texto editorial de Frontiers. Los intervalos son un registro de lectura de esta sesión; no son identificadores permanentes de pasajes.

NASA NTRS y DTIC 2014 no se consideran textos completos leídos en esta ampliación. Las características históricas de NASA/AF-MATB se atribuyen a las descripciones retrospectivas de Cegarra y Vogl, con ese alcance. Las características contemporáneas se refieren a la versión descrita en cada publicación, sin afirmar vigencia universal de su disponibilidad, licenciamiento o tecnología.

## Tres aportes científicos para incorporar

1. **Aportes complementarios de las implementaciones.** Sustituir la agenda genérica por un mapa breve: NASA, cuatro tareas de referencia; AF-MATB, generación de guiones y registros; OpenMATB, personalización, extensión y replicabilidad; USAARL, transiciones de demanda y automatización; integración ASTRA, seguimiento longitudinal con procedencia documentada. La comparación explica el origen del diseño, sin establecer una jerarquía de calidad ni superioridad humana.
2. **Una necesidad metodológica cuantificada.** La revisión de 19 publicaciones identificó siete con configuración suficientemente detallada para una réplica o revisión, según sus autores. Es un resultado sobre descripción metodológica; no informa siete réplicas exitosas ni permite declarar inválidas las otras doce. La propuesta ASTRA responde conservando parámetros, eventos, versión, orden y contexto de cada medición (Pontiggia et al., 2024, §3.3).
3. **Trazabilidad expresada mediante una decisión concreta.** Usar RTLX como ejemplo: seis respuestas completas, media reescalada a 0–100, versión y procedencia. Si falta un ítem, se conservan los disponibles y el compuesto queda ausente con motivo. Esta regla permite al público comprender por qué el contrato de datos afecta la interpretación; procede del contrato local auditado, no de una afirmación sobre resultados humanos.

## Precisión de las afirmaciones

| Tema | Formulación apropiada | Razón |
|---|---|---|
| Conteos de pruebas de los adjuntos | Conservarlos como antecedentes de las instantáneas citadas; presentar la demostración actual de tres escenarios y tres conversiones | Los conjuntos 55/273/709/80 corresponden a ámbitos y cortes diferentes; no se ejecutaron nuevamente en esta revisión |
| Reproducción | Mismos parámetros, semillas y versión producen los archivos verificados | Un hash demuestra identidad de archivos; no demuestra identidad de respuestas humanas |
| Comparación | Aportes complementarios de cada implementación | No hay comparación experimental directa que establezca superioridad o equivalencia |
| Nivel LOW/MEDIUM/HIGH | Condiciones de demanda parametrizadas | Los nombres de condición no representan niveles universales de carga percibida |
| Lectura científica | Preguntas separadas sobre integridad, tiempo físico, respuesta humana y comparación | Cada dominio requiere su evidencia específica; la estructura se presenta en positivo, sin convertirla en una lista de asuntos pendientes |
| Sincronización | Marcadores y procedimientos documentados para vincular registros | La existencia de LSL o marcas de tiempo no cuantifica por sí sola el inicio físico de un estímulo |
| Lengua | Recursos y escenarios en español documentados en el repositorio | La demostración técnica del 21 de septiembre utilizó audio y cuestionarios ingleses |
| Población ASTRA | Hasta 12 participantes previstos, con observaciones dentro de persona | Las múltiples visitas y bloques no multiplican el tamaño muestral independiente |
| Fisiología | Medición complementaria bajo su protocolo específico | HRV no es un indicador exclusivo de carga mental; su interpretación depende de calidad, duración y contexto |

## Hallazgos de la lectura ampliada

Cegarra et al. (2020) sitúan la replicabilidad en el acceso al código, los guiones legibles, la documentación de diferencias y la combinación de guion con versión. Describen personalización mediante escenarios, arquitectura de complementos y registros con marcas temporales. Por tanto, se puede presentar el manifiesto versionado de ASTRA como una concreción local de ese principio, sin atribuirle validación humana publicada.

Vogl et al. (2024) describen en USAARL la generación mediante parámetros y semilla, la visualización temporal de eventos, marcadores LSL y automatización con traspasos de control. Sus salidas incluyen puntuaciones normalizadas respecto de umbrales del investigador. El artículo presenta funciones y usos posibles de una implementación; no demuestra equivalencia de esas puntuaciones con las métricas del repositorio ASTRA ni superioridad en desempeño humano. Su descripción de los antecedentes puede respaldar el mapa comparativo si se atribuye expresamente.

Pontiggia et al. (2024) señalan heterogeneidad de configuración y descripción; la sección 3.3 sustenta el dato siete de 19. Sus recomendaciones relacionan entrenamiento, orden de condiciones, descripción de eventos y combinación de desempeño con autoinforme. De ello se deriva editorialmente la pregunta central de la ponencia: qué información hace interpretable y reproducible una observación multitarea a lo largo de una misión. Esta derivación es la síntesis del equipo, no una conclusión empírica de ASTRA.

## Estado de revisión de la versión ampliada

Se revisaron las diapositivas 3, 4, 9, 12 y 13 en `construccion/build_presentation.ps1`, junto con sus textos pronunciados y notas de apoyo en `guion/notas_data.json`, después de la ampliación. Resultado: **contenido aprobado, sin incidencias científicas bloqueantes**.

| Comprobación | Resultado |
|---|---|
| Mapa de implementaciones | Aportes complementarios; características NASA/AF atribuidas a la descripción histórica de Vogl; no contiene jerarquía de superioridad |
| Siete de 19 | La exposición lo atribuye a los autores y las notas distinguen calidad de descripción de éxito de réplica; la diapositiva muestra el denominador |
| Ejemplo RTLX | Seis respuestas completas de 0–10, media ×10 y resultado 0–100; compuesto ausente con motivo si incompleto; versión no ponderada explícita |
| Cinco dominios del marco | Las notas lo identifican como síntesis del proyecto y no como taxonomía validada ni cinco resultados ya demostrados |
| Conclusiones | Corresponden al método y a la comprobación técnica; adquisición y análisis humanos expresados prospectivamente |
| Duración | Script y notas tienen 16 entradas, vectores idénticos y suma de 690 segundos; margen de 30 segundos hasta los 12 minutos |
| Guion | 1270 palabras pronunciadas en el corte revisado; la suma de tiempos es un presupuesto y no acredita duración de ensayo humano |

Este documento acredita revisión de contenido y congruencia entre script y notas. La legibilidad y la geometría del PowerPoint exportado corresponden a la revisión visual posterior.

## Referencias

Cegarra, J., Valéry, B., Avril, E., Calmettes, C., & Navarro, J. (2020). OpenMATB: A Multi-Attribute Task Battery promoting task customization, software extensibility and experiment replicability. *Behavior Research Methods, 52*, 1980–1990. https://doi.org/10.3758/s13428-020-01364-w

Pontiggia, A., Gomez-Mérino, D., Quiquempoix, M., Beauchamps, V., Boffet, A., Fabries, P., Chennaoui, M., & Sauvet, F. (2024). MATB for assessing different mental workload levels. *Frontiers in Physiology, 15*, 1408242. https://doi.org/10.3389/fphys.2024.1408242

Vogl, J., McCurry, C. D., Bommer, S., & Atchley, J. A. (2024). The United States Army Aeromedical Research Laboratory Multi-Attribute Task Battery. *Frontiers in Neuroergonomics, 5*, 1435588. https://doi.org/10.3389/fnrgo.2024.1435588
