# Auditoría técnica de MATB para III CEINNA

Fecha: 21 de septiembre de 2026. Revisión: `fd5e1318dc6f036b538dd36ed3c5fe42ad8be7d0`.

## Resultado verificable para la presentación

**Se generaron tres escenarios de 900 s, se verificaron sus SHA-256 y su reproducción idéntica con semilla fija, y se convirtieron tres CSV sintéticos a métricas versionadas.** La demostración acredita generación, integridad y conversión; el estudio ASTRA examinará la respuesta humana a las condiciones de demanda parametrizadas. Artefactos en `verificacion_tecnica/`; no se adquirieron datos humanos ni se ejecutó la interfaz en esta revisión.

Texto visible sugerido: «Tres condiciones reproducibles · Manifiestos con SHA-256 · Métricas con versión y procedencia». Pie obligatorio si se muestran salidas: «Verificación técnica con datos sintéticos, 21-09-2026».

## Cuatro tareas y variables

| Tarea | Procedimiento implementado | Resultado de interés / contrato |
|---|---|---|
| SYSMON, supervisión de sistemas | Detectar cambios de luces e indicadores; oportunidades objetivo y no objetivo identificadas | Aciertos, omisiones, falsas alarmas; latencia en ms y discriminabilidad d′ con oportunidades válidas |
| TRACK, seguimiento | Mantener cursor en zona objetivo | Desviación cuadrática media en distancia normalizada; proporción de muestras dentro del objetivo |
| COMM, comunicaciones | Atender indicativo, seleccionar radio y ajustar frecuencia | Respuesta a oportunidades de comunicación y su clasificación; presentación auditiva y ventana de respuesta explícitas |
| RESMAN, gestión de recursos | Controlar bombas para conservar niveles de depósitos | Desviación absoluta del objetivo en unidades del depósito; proporción de muestras dentro de tolerancia |

Código: `openmatb/plugins/{sysmon,track,communications,resman}.py`. Cálculo: `matb_integration/log_converter.py` funciones `_sysmon_metrics`, `_track_metrics`, `_comm_metrics`, `_resman_metrics`; definiciones: `matb_integration/metrics_spec.json`. Los porcentajes etiquetados «tiempo» en el software se calculan por muestras; para la ponencia se recomienda «muestras dentro del objetivo/tolerancia».

## Condiciones verificadas en la generación actual

| Parámetro / recuento generado | LOW | MEDIUM | HIGH |
|---|---:|---:|---:|
| Semilla | 42 | 43 | 44 |
| Tiempo de escenario, s | 900 | 900 | 900 |
| Dificultad parametrizada | 0,20 | 0,50 | 0,80 |
| TRACK, proporción de zona objetivo | 0,80 | 0,50 | 0,20 |
| RESMAN, pérdida por minuto (unidades del escenario) | 200 | 600 | 1000 |
| Intervalo de sondeo ISA, s | 90 | 60 | 45 |
| Oportunidades SYSMON objetivo | 16 | 40 | 65 |
| Oportunidades SYSMON no objetivo | 16 | 40 | 50 |
| Comunicaciones programadas | 4 | 10 | 16 |

Fuente ejecutada: `verificacion_tecnica/resultado_verificacion.json`. Los recuentos son planes de eventos sintéticos, no respuestas observadas. El encabezado de `scenario_builder.py` da 65 oportunidades no objetivo HIGH **antes de reducciones de factibilidad**; la ejecución genera 50. Usar los valores producidos y archivados, no el ejemplo preliminar del comentario. La duración de escenario no equivale necesariamente al tiempo de reloj, porque los cuestionarios bloqueantes pausan las tareas. La densidad de sondeos ISA también varía entre condiciones: describirla y considerarla al interpretar carga percibida.

La CLI canónica utilizada fija audio inglés (`openmatb-english-male-wav-v1`) y cuestionarios ingleses. El repositorio contiene recursos españoles y configuración `es_CO`; su existencia no convierte esta demostración en una sesión española ni acredita equivalencia de perfiles auditivos. Esta precisión se conserva en notas; para la presentación basta describir las cuatro tareas y la parametrización.

El generador dispone de las seis permutaciones de tres condiciones (`COMPLETE_COUNTERBALANCE_3`), distintas de la rotación de estación/hora del cronograma ASTRA. Su uso concreto debe quedar registrado por participante y visita; disponer del generador no prueba su aplicación en las misiones.

## Trazabilidad y criterios de uso de métricas

1. `scenario_manifest.py`: manifiesto v3 con semilla, duración, SHA-256, parámetros, cuestionarios, planes de oportunidades y procedencia de código. La CLI admite vincular participante seudónimo y visita; esta demostración genera plantillas exploratorias.
2. `contracts/events.py`: `ScientificEventV3` y `TimingObservationV1` validan identidades y relojes; `evidence/contracts.py` separa `study`, `practice` y `exploration`, exige participante/visita para estudio y registros de integridad para capturas selladas.
3. `evidence/reconcile.py`: enlaza eventos, observaciones temporales, identidad, manifiesto y cobertura. La consola preserva la vía de CSV heredado separada de capturas científicas reconciliadas (`webui/backend/app/ingestion.py`; `docs/implementation/classic-evidence-pipeline.md`).
4. `study_analysis_eligibility.py:evaluate`: evalúa propósito, fuente, preparación, condiciones físicas/humanas, protocolo, interrupciones y repeticiones según la política. Un valor calculado no acredita automáticamente su inclusión en un análisis.
5. `metrics_spec.json`: RTLX es la media de seis ítems 0–10, reescalada a 0–100. Un cuestionario incompleto conserva ítems pero devuelve `null` en el compuesto. TLX ponderado exige las 15 comparaciones pareadas. d′ observado exige oportunidades objetivo/no objetivo únicas, completas y enlazadas. Los datos ausentes se conservan como ausentes con razones.

La identidad de captura es un UUID determinista derivado de sesión; el manifiesto mantiene participante/visita originales y `routers/participants.py` crea contexto de estudio inmutable. En esta auditoría no se ejecutó una operación de cambio de alias; no afirmar esa operación como demostrada.

## Alcance de automatización y DEPDF

El repositorio documenta componentes experimentales de política de automatización y ajuste DEPDF en `matb_integration/suhir/pipeline.py`. El ajuste no es parte automática de toda captura científica: el flujo de evidencia declara Suhir `not_applicable` cuando no existen entradas de modelo declaradas por el protocolo. La ponencia se centrará en desempeño multitarea, carga percibida y trazabilidad; no atribuirá predicción individual, aptitud ni intervención adaptativa a esta demostración.

## Comprobaciones y reproducción

Desde la raíz del repositorio:

```powershell
python -m matb_integration.scenario_builder --output-dir CEINNA/evidencia/verificacion_tecnica/escenarios --block-duration 900 --seed 42
python CEINNA/evidencia/verificacion_tecnica/verificar_demo.py
```

Resultado: 3/3 hashes coinciden, 3/3 escenarios regenerados idénticos y 3/3 CSV sintéticos convertidos. Entorno: Python 3.14.6. Se usaron aserciones focales independientes del ejecutor de pruebas; no se ejecutó la batería global. `pytest` no está instalado en ese intérprete. El recorrido ampliado `examples/openmatb-research/run_example.py` no se completó por ausencia de `yaml`; se conserva el error en `ejecucion_demo.txt` y no se presenta un ajuste DEPDF como ejecutado.

## Captura documental

`../visuales/capturas_tecnicas/openmatb_captura_documentacion.png` reproduce sin modificación `openmatb/.img/capture.png`, usada en `openmatb/README.es.md`. Su incorporación al repositorio está en commit `9b57a226f21b7046ce4d85556c9b71607a95bfea`, 10-06-2026. SHA-256: `b40af5d10ca6441ed7e4d1c231bffb13f166b2944711e1e36fc64a0aadea6122`. Se inspeccionó visualmente: cuatro tareas y planificador, etiquetas francesas, sin datos humanos visibles. Rotular «Captura documental de OpenMATB; interfaz de referencia». No describirla como captura actual de ASTRA ni como nueva sesión ejecutada.

## Documentación contrastada y decisiones editoriales

Se leyeron README.es.md, openmatb/README.es.md, las secciones científicas/contratos de `scientific-foundation-v2.md`, `qualification-workflow.md`, `scales/scale_validation_es.md`, `classic-evidence-pipeline.md` y los módulos enumerados arriba. El documento científico contiene descripciones de envolturas anteriores; los contratos v3 y la documentación de captura más reciente acreditan la vía adicional actual, sin modificar los CSV históricos.

La evidencia psicométrica citada en `scale_validation_es.md` requiere comprobación primaria por A3: no usar sus coeficientes ni afirmar validación de la traducción local basándose solo en ese documento. Mantener separadas NASA MATB-II, OpenMATB y modificaciones locales. La relación VFC–desempeño y la medición física pertenecen a sus procedimientos científicos correspondientes, no se infieren de hashes ni eventos de software.

### KSS en el repositorio

La consola implementa KSS 1–9 en `webui/frontend/src/app/pvt/page.tsx:39` (`KSS_ES`), con extremos «Extremadamente despierto» y «Muy somnoliento, gran esfuerzo para mantenerse despierto, luchando contra el sueño». Solicita valorar los cinco minutos inmediatamente anteriores (línea 241). El backend valida entero 1–9 (`matb_integration/pvt_scoring.py:57`). La auditoría confirma rango y redacción implementada; la equivalencia literal con la versión colombiana publicada corresponde al cotejo de A3 y no se presupone a partir de estas etiquetas. Se leyeron las instrucciones `webui/frontend/AGENTS.md`; no se modificó la interfaz.
