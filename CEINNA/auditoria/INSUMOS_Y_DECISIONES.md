# Auditoría preliminar de insumos y decisiones

**Fecha:** 2026-09-21. Registro histórico de la inspección inicial para formular el plan. Sus estados pendientes describen esa etapa, no la entrega actual. La lectura integral, investigación, ejecución técnica y revisión visual se completaron posteriormente; consultar el [informe final](../entregables/Informe_de_verificacion.md). El fallo inicial de PowerPoint COM se resolvió mediante la ejecución autorizada en el entorno de escritorio.

## 1. Procedencia y alcance de la inspección

Se copiaron los tres adjuntos a `../fuentes/` sin cambiar sus bytes. Los SHA-256 de origen y destino coinciden; el [manifiesto](../fuentes/manifest.json) conserva rutas originales y nombres de copia.

Se leyeron el control documental, el calendario y los apartados relevantes de MATB del manual, así como el calendario maestro, las reservas, rotaciones y reglas de postmisión del cronograma. Se indexaron los encabezados y cambios de versión. **La lectura integral por A1 sigue siendo una tarea explícita de producción.**

Se inspeccionaron `README.es.md`, los documentos de fundamento científico y calificación, y símbolos/rutas del convertidor de métricas y los servicios de evidencia. El código observado estaba en `fd5e1318dc6f036b538dd36ed3c5fe42ad8be7d0`. No se ejecutaron simulaciones, pruebas de software ni sesiones humanas para este plan.

Se leyó la orientación local de las skills `imagegen`, `pptx` y la guía de edición de plantillas. Se confirmó disponibilidad de herramientas Scite y se consultó su descripción; no se ejecutaron búsquedas bibliográficas.

## 2. Requisitos extraídos de la plantilla

| Propiedad | Hallazgo | Uso en el plan |
|---|---|---|
| Número de láminas | 8 | Se pueden duplicar las láminas de contenido; no se identificó límite textual de ocho |
| Tamaño | 12 192 000 × 6 858 000 EMU | 16:9; 13⅓ × 7½ pulgadas |
| Tipografía aplicada | Bell MT en los textos de las láminas 1–7 | Conservarla al reemplazar texto |
| Tema XML | Aptos Display / Aptos | No confundir tema con tipografía efectivamente aplicada |
| Título institucional | 138 pt | Mantener apertura original |
| Título de ponencia | 72 pt | Verificar ajuste de un título científico largo |
| Títulos de contenido | 44 pt | Mantener jerarquía |
| Cuerpo y lema | 24 y 18 pt | Preservar estilo y espacio del pie |
| Colores explícitos | `000F4D`, `002060`, `242424`, `FFFFFF`, `D90000`, `23B53B`, `26B53B` | Conservar objetos existentes; no usar todos como nueva paleta de gráficas |
| Diapositiva 4 | Referencia genérica a 15 min | La comunicación posterior del Congreso fija 12 min de exposición + 3 de preguntas; objetivo 11:30 |
| Diapositiva 7 | Solicita al menos cinco referencias utilizadas de 2020–2025 | Mínimo verificable en bibliografía y contenido |
| Diapositiva 8 | Sin texto; un objeto de imagen | Inspección completa antes de usarla como cierre |

El texto exacto por diapositiva está en [plantilla_texto.txt](plantilla_texto.txt); la estructura resumida está en [plantilla_estructura.json](plantilla_estructura.json).

La [miniatura original](plantilla_miniatura_original.jpeg) muestra fondo blanco, título azul, franja roja lateral, emblemas institucionales y lema al pie. Es una vista pequeña de la apertura; no acredita el aspecto de todas las láminas.

La exportación completa mediante PowerPoint COM falló con `0x80070520` al crear la instancia. Se encontró PowerPoint instalado y `BELL.TTF`, pero no LibreOffice en su ubicación habitual. Queda previsto usar una sesión de renderización funcional y comprobar todas las láminas antes de cerrar la producción. No se modificó el archivo original.

## 2.1. Normas estrictas aportadas durante la planificación

El investigador proporcionó la comunicación del Congreso; se conserva en [Indicaciones_CEINNA_comunicadas_por_el_investigador.md](../fuentes/Indicaciones_CEINNA_comunicadas_por_el_investigador.md). Sus reglas se incorporaron al plan v1.1 y a todos los encargos:

- Jornadas orales del 13–14 de octubre de 2026.
- 12 min de exposición y 3 min separados de preguntas/comentarios; total 15 min.
- Uso obligatorio del Formulario 3.
- Evaluación del dominio temático, desarrollo/implementación, impacto/relevancia, claridad de comunicación y respuesta a evaluadores.

Se corrigió el presupuesto de exposición a 11:30 más 0:30 de margen y se añadió la matriz de los cinco criterios y preparación del comité. La mención de 15 min en el texto extraído de la plantilla se conserva como evidencia del original, no como duración autorizada de exposición.

## 3. Hechos documentales para la cronología

Las líneas siguientes se refieren a las copias exactas guardadas en `fuentes/`.

| Hecho | Fuente y localizador | Tratamiento |
|---|---|---|
| Definición de ASTRA | Manual, introducción, línea 36 | Expandir sigla en primera aparición |
| Manual v2.5, 11 septiembre | Manual, control documental, líneas 56–64 | Estado de edición; no prueba de ejecución |
| Cronograma en borrador | Cronograma, líneas 7 y 19–20 | Conservar condición prevista |
| Dos misiones de 15 días y seis tripulantes | Cronograma, §1, línea 24 | Muestra prevista, no analizada |
| Basales, ingreso, egreso y D+1 | Manual, líneas 102–120; cronograma, §2, líneas 38–54 | Usar la tabla vigente |
| V0 y seis visitas intramisión más V7 | Manual, §4.7.1, línea 1110; cronograma, línea 117 | Ocho visitas; V1 nominal en DM2 |
| 90 min y tres bloques de 15 min | Manual, líneas 1113–1127; cronograma, §4.1, líneas 129–133 | Diferenciar reserva de sesión y tareas |
| Dos estaciones, tres tandas | Cronograma, líneas 133–142 | Capacidad prevista; verificar recursos |
| Rotación hora/estación | Cronograma, líneas 144–153 | No confundir con orden de niveles |
| Postmisión en D+1 | Cronograma, §7, líneas 438–449 | Sustituye las reservas históricas D+2/D+5 |
| Desvíos y reprogramación | Cronograma, §8, líneas 451–462 | Conservar día/hora reales y motivo |

## 4. Asuntos para conciliación científica y técnica

| Asunto | Evidencia preliminar | Trabajo asignado / formulación de investigación |
|---|---|---|
| Descripción de niveles de demanda | Manual §4.7 atribuye parámetros a literatura; repositorio distingue parámetros y respuesta empírica | A2 verifica escenarios; A3 comprueba estudios. Guion: «tres condiciones de demanda parametrizadas» y medidas usadas para estudiar sus respuestas |
| Versiones antiguas del cronograma | Anexo A conserva DM1, D+2 y duraciones históricas | A1 utiliza cuerpo vigente DM2/D+1/90 min y conserva cambios como historia |
| Basal con distancia diferente al ingreso | V0 D−6 y D−23 | A1/A4 lo incorporan al diseño y a la interpretación longitudinal |
| Traducción y validación de escalas | Manual usa lenguaje de validación; existe un documento específico de escalas | A3 verifica idioma, población y versión antes de hacer una afirmación psicométrica |
| TLX y discriminabilidad SYSMON | Registro v2 separa métricas corregidas y alias históricos | A2 confirma nombres, denominadores, requisitos y unidades; A4 explica la medida realmente usada |
| CSV y evidencia de eventos | README distingue ingesta CSV de reconciliación de capturas | A2 documenta cada ruta; la presentación muestra trazabilidad sin equiparar estados |
| Orden de bloques y cambio de alias | Manual §4.7.6.3 pide conservar orden de V0 al cambiar Cxx a A1/A2-Pxx | A2 verifica implementación y persistencia; no recalcular por sufijo sin comprobar |
| Seis secuencias de tres niveles | Manual describe una estructura de contrabalanceo | A2 verifica asignación. Usar «seis órdenes contrabalanceados» si corresponde, sin confundir número de secuencias con orden de un cuadrado latino |
| Tiempo de tarea y pausas ISA | Manual usa 900 s y describe pausas de tareas | A2 distingue tiempo programado, activo y de reloj; A1 mantiene reserva de 90 min |
| Automatización y DEPDF | Manual contiene modos y ajuste al ingerir; código tiene contratos y condiciones de elegibilidad | A2 determina comportamiento de la revisión actual; limitar el guion a lo pertinente y comprobado |
| Repositorios y modalidades | Manual incluye Mission Control/HRV, MATB clásico y UAS | A2 delimita qué pertenece a este repositorio y A4 mantiene el foco de la ponencia |
| Resultados de ASTRA | Los adjuntos son documentos de planificación | A4 usa tiempos verbales prospectivos y resultados técnicos acreditados; A6 verifica que no se introduzcan resultados humanos ficticios |

La instrucción editorial del investigador del 21 de septiembre rige el guion: **discurso en positivo, exclusivamente de investigación, sin marketing**. Las verificaciones internas sirven para escoger afirmaciones precisas. La narrativa se construye con el diseño, las mediciones y el análisis del estudio.

## 5. Estado de comprobación

- [x] Carpeta CEINNA creada.
- [x] Tres adjuntos conservados y hashes comparados.
- [x] Texto y metadatos de ocho diapositivas extraídos.
- [x] Miniatura incrustada inspeccionada.
- [x] Requisitos de tiempo y referencias incorporados al plan.
- [x] Actualización estricta a 12 min de exposición + 3 min de preguntas y cinco criterios oficiales.
- [x] Inspección focal de documentos ASTRA y repositorio realizada.
- [x] Roles, propiedad de archivos, dependencias y controles definidos.
- [ ] Lectura integral documentada por agente de contexto.
- [ ] Revisión bibliográfica Scite ejecutada.
- [ ] Auditoría funcional de capacidades y capturas técnicas.
- [ ] Recursos imagegen y diagramas producidos.
- [ ] PPTX/PDF final construido, renderizado y revisado.

Las casillas abiertas corresponden a la producción futura solicitada en el plan, no a entregables omitidos de esta fase.
