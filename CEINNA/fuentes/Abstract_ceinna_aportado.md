---
title: Abstract CEINNA 2026 — MATB
aliases:
  - Abstract-ceinna
  - Resumen CEINNA MATB
type: manuscript
status: draft
created: 2026-08-31
updated: 2026-08-31
hub: "[[CEINNA]]"
conference: III CEINNA 2026
project: MATB
submission_type: Investigación en Desarrollo
thematic_axis: 2. Formación y educación
research_line: 2.2. Simulación y realidad virtual
submission_status: blocked-pending-late-authorization
tags:
  - research-active
  - ceinna
  - matb
  - abstract
---

# Calificación científica y trazabilidad reproducible de una batería multitarea aeronáutica para investigación del factor humano

> [!important] Uso de este archivo
> Borrador científico para revisión de autores. La postulación debe transferirse al [Formato Abstract oficial](https://www.fac.mil.co/sites/default/files/Ceinna/2026/abstract_2.docx), aplicar su tipografía y no superar dos páginas. No enviar hasta recibir autorización extemporánea y resolver la cesión de derechos descrita en [[CEINNA]].

<u>Diego L. Malpica</u>\*  
*Dirección de Medicina Aeroespacial, Subdirección de Ciencias Aeroespaciales, Fuerza Aeroespacial Colombiana, Bogotá D.C., Colombia*  
*Correo: \* diego.malpica@fac.mil.co*

> [!todo] Autoría
> Confirmar coautores, orden de contribución, afiliaciones y autor de correspondencia antes de copiar al DOCX. El subrayado identifica al ponente.

## Resumen

La Multi-Attribute Task Battery (MATB) es un entorno experimental de tareas simultáneas análogas a funciones aeronáuticas, utilizado para estudiar carga mental, atención, automatización y desempeño humano [1]. Las implementaciones abiertas han ampliado la personalización, la integración psicofisiológica y la reproducibilidad [2], y desarrollos recientes incorporan transiciones dinámicas y automatización adaptativa [3]. Sin embargo, la riqueza funcional y las pruebas informáticas no demuestran calibración humana. El objetivo fue desarrollar y verificar una arquitectura de calificación científica y trazabilidad con cierre seguro para investigación del factor humano en aviación militar.

Se aplicó una estrategia versionada y aditiva sobre un entorno derivado de OpenMATB 1.4.5. La arquitectura separa conformidad del software, tiempo físico, calibración humana, confiabilidad test–retest y equivalencia entre implementaciones. Se implementaron perfiles de compatibilidad, contratos legibles por máquina, escenarios LOW/MEDIUM/HIGH con huellas SHA-256, registro de eventos, control de calidad temporal, validación de sesiones seudonimizadas, exportación compatible con BIDS y compuertas de liberación. El plan de calibración define personal de aviación militar como población inicial y tres sesiones contrabalanceadas con sincronización fisiológica. No se recolectaron datos de participantes ni se midió el tiempo físico; la evaluación se limitó al comportamiento del software.

La instantánea evaluada reprodujo huellas deterministas para los tres escenarios y conservó versiones, unidades, ecuaciones, reglas de datos faltantes y elegibilidad confirmatoria de cada métrica. La suite focal registró 55 pruebas aprobadas y 5 omitidas; también aprobaron 709 pruebas del entorno OpenMATB, 55 del subconjunto principal del backend y 80 del frontend. Las compuertas permanecieron cerradas mientras continúan pendientes calibración humana, medición física, equivalencia, privacidad y licenciamiento. Estos resultados demuestran conformidad y reproducibilidad del comportamiento programado, pero no establecen niveles universales de carga, inicio físico de estímulos, equivalencia con NASA MATB-II ni validez para diagnóstico, selección, aptitud aeromédica o decisiones operacionales.

**Tabla 1. Estado de la evidencia del marco de calificación.**

| Dimensión | Evidencia actual | Interpretación permitida |
| --- | --- | --- |
| Conformidad del software | Escenarios deterministas, contratos versionados y pruebas focales | Comportamiento reproducible de la instantánea inspeccionada |
| Tiempo físico | Protocolo y analizador implementados; medición no ejecutada | No permite afirmar latencia física ni aptitud para estudios evento-relacionados |
| Calibración humana | Diseño de estudio y contrabalanceo preparados; sin participantes | Niveles de carga aún no validados |
| Equivalencia | Perfiles comparadores definidos; prueba directa pendiente | No permite afirmar equivalencia con NASA MATB-II u OpenMATB canónico |
| Liberación | Compuertas de privacidad, licencias y evidencia activas | Estado de investigación en desarrollo; liberación confirmatoria bloqueada |

El aporte es una ruta auditable para convertir una plataforma de simulación en un instrumento científicamente calificable, no una nueva prueba diagnóstica. La separación de evidencias conserva la procedencia y evita presentar verificación informática como validez humana. Los siguientes pasos son la determinación ética, el prerregistro y calibración con personal de aviación militar, la medición física, la confiabilidad test–retest y la comparación preespecificada de implementaciones. Hasta entonces, el uso permanece restringido a investigación y desarrollo.

**Palabras clave:** MATB; simulación aeronáutica; carga mental; factor humano; reproducibilidad.

## Referencias

[1] S.M. Santiago-Espada, R.R. Myer, K.A. Latorella, J.R. Comstock Jr. *The Multi-Attribute Task Battery II (MATB-II) Software for Human Performance and Workload Research: A User's Guide*. NASA/TM-2011-217164, 2011. Disponible en: [NASA NTRS](https://ntrs.nasa.gov/citations/20110014456).

[2] J. Cegarra, B. Valéry, E. Avril, C. Calmettes, J. Navarro. OpenMATB: A Multi-Attribute Task Battery promoting task customization, software extensibility and experiment replicability. *Behavior Research Methods* 52 (2020) 1980–1990. [https://doi.org/10.3758/s13428-020-01364-w](https://doi.org/10.3758/s13428-020-01364-w).

[3] J. Vogl, C.D. McCurry, S. Bommer, J.A. Atchley. The United States Army Aeromedical Research Laboratory Multi-Attribute Task Battery. *Frontiers in Neuroergonomics* 5 (2024) 1435588. [https://doi.org/10.3389/fnrgo.2024.1435588](https://doi.org/10.3389/fnrgo.2024.1435588).

## Control previo al envío

- [ ] Autorización extemporánea escrita del comité CEINNA.
- [ ] Coautores, orden, afiliaciones y correo confirmados.
- [ ] Revisión de cada cifra contra el commit de evidencia.
- [ ] Revisión jurídica/institucional del Formulario 2.
- [ ] Confirmación de que la cesión no comprende código, repositorio, datos ni componentes de terceros.
- [ ] Transferencia al DOCX oficial y validación de máximo dos páginas.
- [ ] Aprobación final de todos los autores.
