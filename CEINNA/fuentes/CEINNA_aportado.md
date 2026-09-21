---
title: Desarrollo y calificación científica de una plataforma MATB para investigación del factor humano en aviación militar colombiana
aliases:
  - CEINNA
  - Abstract CEINNA MATB
type: manuscript
status: draft-for-author-review
created: 2026-08-31
updated: 2026-09-01
hub: "[[_Research_MOC]]"
conference: III CEINNA 2026
project: MATB
submission_type: Investigación en Desarrollo
thematic_axis: 2. Formación y educación
research_line: 2.2. Simulación y realidad virtual
evidence_snapshot: 8346a3b91205fb6d86f5eba48eff9766a17e69f4
tags:
  - research-active
  - ceinna
  - matb
  - abstract
  - human-factors
---

# Desarrollo y calificación científica de una plataforma MATB para investigación del factor humano en aviación militar colombiana

<u>Diego L. Malpica</u>^a,*<br>
^a *Dirección de Medicina Aeroespacial, Subdirección de Ciencias Aeroespaciales, Fuerza Aeroespacial Colombiana, Bogotá D.C., Colombia*<br>
*Correo: diego.malpica@fac.mil.co*

## Resumen

### Introducción

Las operaciones aeronáuticas militares requieren estudiar bajo control experimental cómo la carga mental, la atención distribuida y la automatización se relacionan con el desempeño multitarea. NASA estableció MATB/MATB-II con cuatro tareas análogas al vuelo [1]. La USAF añadió generación de guiones, registros y sincronización externa [2]; OpenMATB aportó código y escenarios auditables [3]; y USAARL incorporó diseño visual y automatización adaptativa [4]. Persisten dos brechas: arquitecturas heredadas o cerradas y configuraciones de carga no universalmente transferibles [5]. Para disponer de una plataforma institucionalmente gobernable, en español, integrable con fisiología y trazable de extremo a extremo, la Fuerza Aeroespacial Colombiana (FAC) desarrolló una adaptación de OpenMATB. El objetivo fue comparar las principales implementaciones y verificar su aporte tecnológico y científico diferencial.

### Métodos y materiales

Se realizó investigación de desarrollo tecnológico y revisión comparativa de NASA MATB-II, USAF AF-MATB, OpenMATB y USAARL v2.2 [1–5]. En la instantánea `8346a3b` se evaluaron tareas, escenarios, automatización, registro, sincronización, extensibilidad y evidencia. Sobre OpenMATB 1.4.5 se integraron escenarios militares deterministas con manifiestos SHA-256, métricas v2, eventos JSONL y control temporal, LSL, exportación BIDS, SAGAT, ISA, NASA-TLX, Bedford y una consola FastAPI/Next.js. Contratos legibles por máquina separaron conformidad del software, temporización física, calibración y confiabilidad humanas y equivalencia entre implementaciones. Se ejecutaron pruebas automatizadas; no hubo participantes ni medición física de estímulos.

### Resultados

Los escenarios LOW/MEDIUM/HIGH reprodujeron huellas deterministas y conservaron versión, unidades, ecuaciones, reglas de datos faltantes y elegibilidad confirmatoria. La suite científica e integrativa aprobó 273 pruebas y omitió 9 condicionadas por disponibilidad; el entorno OpenMATB aprobó 709 pruebas. La comparación mostró aportes complementarios y límites distintos (Tabla 1).

**Tabla 1. Comparación de las implementaciones MATB y contribución diferencial del desarrollo FAC (fuentes [1–4]).**

| Implementación y tecnología | Características distintivas | Utilidad principal | Diferencia o límite relevante |
| --- | --- | --- | --- |
| **NASA MATB-II** — C++/Windows | Cuatro tareas canónicas, modos de entrenamiento/prueba, GUI y archivos de eventos configurables | Referente histórico con mayor continuidad empírica | Arquitectura heredada y menor extensibilidad/sincronización multimodal nativa |
| **USAF AF-MATB** — implementación Windows/MCR documentada | Generación automatizada de parámetros y guiones, registros detallados, automatización de tareas y disparadores externos | Investigación militar de carga, estrategia, confianza y psicofisiología | Código/licencia no abiertos y pila tecnológica heredada |
| **US Army USAARL MATB v2.2** — MATLAB App Designer/Runtime | Línea temporal visual, generación con semilla, transición dinámica de demanda, confiabilidad 0–100, sistema VOGL de traspasos y LSL | Referente contemporáneo para automatización adaptativa y confianza | Fuente cerrada y madurez empírica menor que la línea NASA/USAF |
| **FAC MATB** — Python/OpenMATB + FastAPI/Next.js | Escenarios militares deterministas, métricas versionadas, SAGAT y escalas, JSONL/LSL/BIDS, control temporal, consola, análisis y compuertas de evidencia | Flujo local de extremo a extremo para estudios longitudinales y multimodales auditables | Calibración humana, temporización física, confiabilidad test–retest y equivalencia aún pendientes |

### Análisis

La innovación FAC no sustituye las tareas canónicas: integra escenario → evento → métrica → sincronización → análisis con procedencia verificable y cierre seguro. Responde a las brechas de replicabilidad de OpenMATB [3] y estandarización señaladas en 19 estudios [5], y permite escenarios en español, fusión fisiológica y análisis longitudinal. NASA/USAF conservan mayor madurez empírica; USAARL mantiene ventajas en diseño visual y automatización adaptativa.

### Discusión

Las pruebas sustentan conformidad del software, no validez humana, clínica u operacional. LOW/MEDIUM/HIGH siguen siendo preajustes de ingeniería; los siguientes pasos son revisión ética, prerregistro, calibración en personal de aviación militar, medición física, test–retest y equivalencia cruzada. Hasta entonces, el uso se restringe a investigación y desarrollo sin diagnóstico, selección, aptitud ni decisión operacional.

**Palabras clave:** MATB; aviación militar; carga mental; factor humano; reproducibilidad.

## Referencias

[1] Y. Santiago-Espada et al. *The MATB-II Software for Human Performance and Workload Research*. NASA/TM-2011-217164, 2011. [NASA NTRS](https://ntrs.nasa.gov/citations/20110014456).

[2] W.D. Miller Jr. et al. *An Updated Version of the U.S. Air Force MATB*. ADA611870, 2014. [https://doi.org/10.21236/ADA611870](https://doi.org/10.21236/ADA611870).

[3] J. Cegarra et al. *Behavior Research Methods* 52 (2020) 1980–1990. [https://doi.org/10.3758/s13428-020-01364-w](https://doi.org/10.3758/s13428-020-01364-w).

[4] J. Vogl et al. *Frontiers in Neuroergonomics* 5 (2024) 1435588. [https://doi.org/10.3389/fnrgo.2024.1435588](https://doi.org/10.3389/fnrgo.2024.1435588).

[5] A. Pontiggia et al. *Frontiers in Physiology* 15 (2024) 1408242. [https://doi.org/10.3389/fphys.2024.1408242](https://doi.org/10.3389/fphys.2024.1408242).

## Alcance del hallazgo

La evidencia disponible demuestra funcionamiento programado reproducible y una arquitectura de calificación científica más amplia que la de las implementaciones comparadas en los documentos públicos consultados. No demuestra superioridad del desempeño humano, validación clínica, equivalencia entre programas ni autorización operacional.
