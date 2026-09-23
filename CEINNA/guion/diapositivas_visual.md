# Texto de diapositivas · edición visual

Extraído del PPTX de 17 diapositivas; la previsualización PDF es rasterizada.

## 1. III CEINNA

Tiempo: 0 s.

III CEINNA
III Congreso Internacional de Estudios en Innovación y Nuevas Tecnologías para la Seguridad y la Defensa
“Del conocimiento a la capacidad estratégica”

## 2. Carga mental y desempeño multitarea en ASTRA

Tiempo: 20 s.

“Del conocimiento a la capacidad estratégica”
Carga mental y desempeño
multitarea en ASTRA
Diseño longitudinal mediante MATB
SMSM DIEGO L MALPICA
Especialista en Medicina Aeroespacial
Subdirección Científica Aeroespacial – DIMAE
III CEINNA · 13–14 de octubre de 2026
2

## 3. Aportes de la familia MATB

Tiempo: 55 s.

“Del conocimiento a la capacidad estratégica”
Aportes de la familia MATB
NASA MATB-II · 2011
Tareas de referencia y configuración experimental
USAF AF-MATB · 2014
Generación de guiones y sincronización externa
OpenMATB · 2020
Personalización, código abierto y replicabilidad
USAARL MATB · 2024
Transiciones de demanda y automatización adaptativa
Integración FAC para ASTRA
Escenario reproducible → registro trazable → seguimiento longitudinal
[1,5] Cegarra et al., 2020; Vogl et al., 2024 (§1.2). Aportes complementarios.
3

## 4. De la literatura al diseño ASTRA

Tiempo: 50 s.

“Del conocimiento a la capacidad estratégica”
De la literatura al diseño ASTRA
7 / 19
Configuración suficiente para replicación o revisión
Decisión metodológica
Documentar parámetros y versión.
Separar demanda y respuesta.
Conservar contexto y secuencia.
¿Cómo varían el desempeño y la carga percibida entre condiciones de demanda y a lo largo de ASTRA?
[2] Pontiggia et al., 2024, §3. Revisión de 19 estudios; heterogeneidad sin metaanálisis.
4

## 5. ASTRA: contexto del estudio

Tiempo: 50 s.

“Del conocimiento a la capacidad estratégica”
ASTRA: contexto del estudio
Aerospace Simulation Training Research Analogs
2 misiones · 15 días
Hasta 6 participantes previstos por misión
Aislamiento y confinamiento
Evaluación intrapersonal
Ilustración conceptual generada con IA; no fotografía de ASTRA.
Manual ASTRA v2.5 y cronograma, 11-09-2026. Diseño previsto.
5

## 6. Ocho visitas por participante

Tiempo: 65 s.

“Del conocimiento a la capacidad estratégica”
Ocho visitas por participante
Dos series longitudinales: ASTRA 1 y ASTRA 2
V0
Basal
V1
DM2
V2
DM4
V3
DM7
V4
DM10
V5
DM13
V6
DM15
V7
D+1
Secuencia de visitas; separación gráfica no proporcional al tiempo.
V0: 29 sep. (ASTRA 1) · 28 sep. (ASTRA 2)
V7: 20 oct. (ASTRA 1) · 5 nov. (ASTRA 2)
Basal respecto al ingreso: D−6 y D−23, respectivamente.
Manual §4.7.6 y cronograma §§2, 4.1 y 7. DM = día de misión. Fechas previstas.
6

## 7. Cuatro tareas simultáneas

Tiempo: 60 s.

“Del conocimiento a la capacidad estratégica”
Cuatro tareas simultáneas
SYSMON
Supervisión de sistemas
TRACK
Seguimiento compensatorio
COMM
Comunicaciones
RESMAN
Gestión de recursos
Captura documental de OpenMATB (interfaz original en francés).
[1] Cegarra et al., 2020; plugins del repositorio MATB, revisión fd5e1318.
7

## 8. Estructura de una visita

Tiempo: 55 s.

“Del conocimiento a la capacidad estratégica”
Estructura de una visita
90 min de reserva
3 × 900 s de escenario
LOW · MEDIUM · HIGH
Orden contrabalanceado
KSS → ISA → NASA-TLX
Antes · durante · después
Ilustración conceptual generada con IA.
Manual §4.7; [6] Laverde-López et al., 2022. Preparación, reposo y pausas en la reserva.
8

## 9. Fisiología: adquisición separada

Tiempo: 30 s.

“Del conocimiento a la capacidad estratégica”
Fisiología: adquisición separada
Ilustración conceptual generada con IA; equipos no conectados.
Polar H10
Intervalos R–R si se verifica la ruta de captura
ActiGraph
Movimiento y actividad
HRV: descriptor derivado, sujeto a calidad de señal.
Manual ASTRA §§4.2.3, 4.7 y fisiología; adquisición distinta de las tareas MATB.
9

## 10. Del escenario a una métrica interpretable

Tiempo: 65 s.

“Del conocimiento a la capacidad estratégica”
Del escenario a una métrica interpretable
Escenario
Parámetros
Semilla
Orden
→
Registro
Identidad
Visita
Eventos
→
Métricas
Definición
Unidades
Versión
→
Análisis
Calidad
Elegibilidad
Trazabilidad
Ejemplo: carga percibida con RTLX
6 respuestas completas (0–10) → media × 10 → índice 0–100
Cada resultado conserva versión, unidad, regla de cálculo y procedencia.
[1,5] Replicabilidad y registro. Ejemplo local: metrics_spec.json y log_converter.py.
10

## 11. Resultados de desarrollo

Tiempo: 65 s.

“Del conocimiento a la capacidad estratégica”
Resultados de desarrollo
Demostración técnica con datos sintéticos
Generación
Tres escenarios de 900 s: LOW, MEDIUM y HIGH.
Reproducción
Archivos idénticos al repetir parámetros y semillas.
Integridad y conversión
Hashes SHA-256 verificados; tres archivos CSV sintéticos convertidos.
Ejecución local: 21-09-2026 · commit fd5e1318 · evidencia/verificacion_tecnica/.
11

## 12. Análisis de medidas repetidas

Tiempo: 65 s.

“Del conocimiento a la capacidad estratégica”
Análisis de medidas repetidas
Unidad de seguimiento: la persona
Persona → visita → bloque
Trayectorias individuales
Contrastes entre condiciones
Cambios entre visitas
Contexto de medición
Orden de bloques
Hora y estación
Sueño previo
Días desde V0
[3,4] Pontiggia et al., 2024 (experimento); Tortello et al., 2020. Manual §4.7.
12

## 13. Marco de calificación científica

Tiempo: 55 s.

“Del conocimiento a la capacidad estratégica”
Marco de calificación científica
Reproducción
¿Se repite el escenario programado?
Fidelidad temporal
¿Cuándo se presenta el estímulo físico?
Respuesta humana
¿Cómo se relacionan demanda y respuesta?
Estabilidad
¿Qué variación aparece al repetir la medición?
Comparabilidad
¿Qué se conserva entre implementaciones?
Cada pregunta se vincula con su procedimiento y evidencia específicos.
Marco del proyecto: resúmenes CEINNA y contratos locales; contexto metodológico [1,2,5].
13

## 14. Conclusiones y recomendaciones

Tiempo: 65 s.

“Del conocimiento a la capacidad estratégica”
Conclusiones y recomendaciones
1
Describir la demanda hace interpretable la comparación entre condiciones.
2
La trazabilidad vincula escenario, evento y métrica en cada visita.
3
ASTRA sitúa la respuesta multitarea en la trayectoria de cada persona.
Siguiente etapa: ejecución protocolizada y análisis de las visitas.
Síntesis del diseño ASTRA y de la verificación técnica de MATB.
14

## 15. Bibliografía I

Tiempo: 10 s.

“Del conocimiento a la capacidad estratégica”
Bibliografía I
[1] Cegarra et al. (2020). OpenMATB: A Multi-Attribute Task Battery promoting task customization, software extensibility and experiment replicability. Behavior Research Methods, 52(5), 1980–1990. https://doi.org/10.3758/s13428-020-01364-w
[2] Pontiggia et al. (2024). MATB for assessing different mental workload levels. Frontiers in Physiology, 15, Article 1408242. https://doi.org/10.3389/fphys.2024.1408242
[3] Pontiggia et al. (2024). Combined effects of moderate hypoxia and sleep restriction on mental workload. Clocks & Sleep, 6(3), 338–358. https://doi.org/10.3390/clockssleep6030024
Autorías abreviadas en pantalla. Referencias APA completas en notas y documento adjunto.
15

## 16. Bibliografía II

Tiempo: 10 s.

“Del conocimiento a la capacidad estratégica”
Bibliografía II
[4] Tortello et al. (2020). Subjective time estimation in Antarctica: The impact of extreme environments and isolation on a time production task. Neuroscience Letters, 725, Article 134893. https://doi.org/10.1016/j.neulet.2020.134893
[5] Vogl et al. (2024). The United States Army Aeromedical Research Laboratory Multi-Attribute Task Battery. Frontiers in Neuroergonomics, 5, Article 1435588. https://doi.org/10.3389/fnrgo.2024.1435588
[6] Laverde-López et al. (2022). Validation of the Colombian version of the Karolinska sleepiness scale. Sleep Science, 15(Spec 1), 97–104. https://doi.org/10.5935/1984-0063.20220006
Autorías abreviadas en pantalla. Referencias APA completas en notas y documento adjunto.
16

## 17. Cierre institucional

Tiempo: 0 s.
