# Auditoría de actualización del póster MATB-FAC

Fecha de revisión: **23 de septiembre de 2026**. Revisión del repositorio: `e7173321ac8516ab14878695c416110a689ae443`.

## Entregables y alcance

- `EMAVI_2026_poster_Malpica_actualizado.pptx`: una diapositiva editable, 80 × 120 cm, vertical.
- `EMAVI_2026_poster_Malpica_actualizado.pdf`: exportación nativa de PowerPoint, una página del mismo tamaño.
- `revision_actualizacion/Actualizar_poster.ps1`: procedimiento reproducible de composición y exportación nativa.
- `revision_actualizacion/verificacion_powerpoint.json`: dimensiones, integridad del original y comprobaciones de ajuste del texto.

Se preservó el original `EMAVI_2026_poster_Malpica.pptx`. La composición conserva el banner institucional, autoría, contacto, colores y organización general en secciones. El contenido científico y los diagramas se reconstruyeron como texto y formas editables porque el original incluía diagramas dentro de una imagen de página completa. Esa imagen se conserva recortada al banner: los píxeles fuera del recorte no forman parte de la composición visible. No se importaron imágenes ni contenido clasificado de la presentación EMAVI. No se modificaron software, protocolos, manuscritos ni otros pósteres.

Esta actualización revisa implementación y evidencia existente. **No ejecutó un nuevo estudio, una nueva adquisición fisiológica ni una nueva recomputación científica.** Las verificaciones nuevas corresponden al contenido, estructura y exportación del póster.

## Matriz de afirmaciones y fuentes locales

Rutas relativas a la raíz del repositorio.

| Afirmación del póster | Fuente examinada | Alcance y límite |
| --- | --- | --- |
| OpenMATB reúne vigilancia, seguimiento, comunicaciones y recursos | `README.es.md`; `matb_integration/evidence/reconcile.py`, registro `METRICS` y reconciliación por tarea | Capacidades implementadas; no certifica validez humana de esta implementación. |
| Escenarios, duración y semilla; procedencia de configuración | `README.es.md`; `matb_integration/scenario_builder.py`; contratos de captura examinados desde `reconcile.py` | Demanda programada. Los preajustes de carga no equivalen a niveles humanos calibrados. |
| Práctica y estudio se distinguen | `webui/backend/app/purpose_service.py`, `declare_acquisition`; `matb_integration/evidence/reconcile.py` | La finalidad declarada queda vinculada a procedencia. Una captura no destinada a estudio conserva motivo de exclusión. |
| Integridad, eventos, definición versionada y motivos de exclusión | `matb_integration/evidence/reconcile.py`, `parse_capture` y construcción de métricas; `matb_integration/metrics_spec.json` | Se verifican hashes y recuentos; cada métrica puede conservar IDs fuente y razones de inelegibilidad. La ruta histórica de CSV no queda automáticamente reconciliada. |
| Seguimiento entre visitas | `webui/backend/app/study_protocol.py`; `README.es.md` | El calendario depende del protocolo. No se afirma un número universal de visitas. |
| Supervisión sUAS sintética | `matb_integration/suas/engine/runtime.py`; `README.es.md` | Simulación determinista; no control de aeronaves reales. |
| Simulación FPV opcional | `matb_integration/liftoff/session.py`, `metrics.py`; `README.es.md` | Registro y métricas de simulador. Nombre comercial omitido del contenido visible; rutas internas preservadas aquí para trazabilidad. No demuestra transferencia a vuelo real. |
| Polar H10 experimental | `docs/physiology/polar-h10-release-a.md`; `matb_integration/physiology/analysis.py` | Adquisición local opcional y descriptores fisiológicos. No se declara adquisición humana en esta revisión ni sincronización física calificada. |
| 11 métricas recomputadas; valores y enlaces coincidentes | `EMAVI/revision/verificacion_exportacion.json` | Evidencia histórica sintética: `metrics=11`, `recalculated_values_and_links_match=true`, `implementation_matches=true`, `environment_matches=true`. No corresponde a 11 sujetos, pruebas aprobadas o medidas necesariamente válidas para análisis confirmatorio. |
| Entorno de publicación pendiente de calificación | Mismo informe: `recorded_analysis_execution.dependency_lock_matches=false` y `verifier_execution.dependency_lock_matches=false` | Coincidir entre ejecución y verificador no implica coincidir con el archivo de bloqueo. La limitación aparece junto al resultado numérico. |
| Tiempo físico, calibración, confiabilidad y validez pendientes | `docs/research/qualification-workflow.md`; `docs/research/scientific-foundation-v2.md`; salida de elegibilidad de `reconcile.py` | Evidencia de software, temporización física, calibración humana y caracterización entre implementaciones son clases independientes. El gráfico del póster es una síntesis de límites inferenciales, no una certificación formal ni una declaración de aprobación integral. |

## Fecha y procedencia de la verificación histórica

El informe de las 11 métricas identifica el código de origen `24d37b52da7196e5c69f9a8cfc9481c04fd1221d`; la ejecución registrada tiene `source_dirty=false` y el verificador `source_dirty=true`. Las huellas de implementación coinciden según el propio informe. Este resultado no se reasigna al commit actual.

El JSON examinado no contiene una fecha explícita de ejecución. Por ello, el póster dice **«Informe revisado: 23-09-2026»** y la referencia [5] identifica la revisión del informe; no se inventó una fecha de ensayo. No se volvió a ejecutar el paquete científico para este trabajo.

## Discrepancias resueltas editorialmente

- El póster anterior proponía tres visitas. El código `astra-2026` define T0, DM8 y DM15; otro protocolo define seis visitas. La presentación EMAVI describe ocho visitas. Se conservó «seguimiento entre visitas» sin convertir ninguno de esos calendarios en propiedad general de MATB-FAC ni modificar los protocolos.
- Se eliminó la comparación no actualizada con cinco familias MATB y los lemas numéricos de capacidades. La introducción se apoya en literatura y los resultados en código y evidencia local identificados.
- Se retiraron las referencias que dejaron de sustentar el foco actual. No se reutilizaron las 57 pruebas ni los tiempos de vuelo sintético presentes en otra versión del póster.
- Se mantuvieron separados desempeño, carga percibida y fisiología. No se creó una puntuación global, diagnóstico ni afirmación de aptitud.

## Bibliografía verificada en fuentes primarias

Consultada el 23-09-2026. Los enlaces DOI iniciales no resolvieron en la herramienta; la comprobación se completó en los sitios de las revistas. Esta consulta verifica las referencias retenidas; no constituye una revisión sistemática de literatura hasta 2026.

1. Cegarra, J., Valéry, B., Avril, E., Calmettes, C., y Navarro, J. (2020). *OpenMATB: A Multi-Attribute Task Battery promoting task customization, software extensibility and experiment replicability*. Behavior Research Methods, 52, 1980–1990. [Página editorial](https://link.springer.com/article/10.3758/s13428-020-01364-w). Sustenta personalización y replicabilidad; no valida MATB-FAC.
2. Pontiggia, A., et al. (2024). *MATB for assessing different mental workload levels*. Frontiers in Physiology, 15, 1408242. [Artículo completo](https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2024.1408242/full). Sustenta la necesidad de documentar la configuración y las limitaciones de comparación entre estudios.
3. Vogl, J., McCurry, C. D., Bommer, S., y Atchley, J. A. (2024). *The United States Army Aeromedical Research Laboratory Multi-Attribute Task Battery*. Frontiers in Neuroergonomics, 5, 1435588. [Artículo completo](https://www.frontiersin.org/journals/neuroergonomics/articles/10.3389/fnrgo.2024.1435588/full). Documenta otra implementación y sus variantes; no demuestra equivalencia con MATB-FAC.

Las referencias [4] y [5] son fuentes locales, no publicaciones revisadas por pares. El póster abrevia los títulos para legibilidad y mantiene identificadores DOI o revisión de código.

## Verificación de los entregables

La primera composición mostró desbordamientos en resumen, nota de evidencia y referencias. Se corrigieron alturas, espaciado, márgenes y conectores y se repitió la exportación. Las propiedades del documento también se actualizaron para retirar el título y las palabras clave antiguos.

Los resultados finales de estructura, texto, dimensiones, integridad y hashes se registran en `revision_actualizacion/validacion_final.json`; la revisión visual independiente se resume en `revision_actualizacion/revision_visual.md`. Los archivos `poster_actualizado.png` y `poster_pdf.png` permiten revisar ambos renderizados. Las pruebas no implican nueva validación científica de MATB-FAC.
