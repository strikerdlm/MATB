# Recorrido de investigación OpenMATB sin conexión

[English](README.md)

Este recorrido rápido y determinista produce artefactos de investigación
sintéticos sin iniciar OpenMATB. El ejecutor externo de OpenMATB se instala por
separado cuando un estudio necesita presentar los escenarios generados; este
ejemplo no lo incluye ni lo invoca.

## Ejecutar

Desde la raíz del repositorio, elija un directorio de salida bajo su control:

```bash
python3 examples/openmatb-research/run_example.py --output-dir /tmp/matb-tour
```

También puede usar el lanzador nativo; su primer argumento opcional es el
directorio de salida:

```bash
examples/openmatb-research/run.sh /tmp/matb-tour
```

```powershell
.\examples\openmatb-research\run.ps1 -OutputDir C:\Temp\matb-tour
```

El recorrido imprime nombres relativos de artefactos y termina con `External
OpenMATB was not started.` Solo escribe debajo del directorio seleccionado:

- `scenarios/`: tres escenarios LOW/MEDIUM/HIGH de 900 segundos y semilla fija;
- archivos adyacentes `*.txt.manifest.json`: procedencia con nombre del
  escenario, SHA-256, nivel de carga, duración, semilla y cuestionarios;
- `metrics.jsonl`: un registro canónico convertido por cada sesión sintética;
- `suhir.json`: un ajuste DEPDF para `SYNTH-P01`.

Antes de convertir, el script analiza cada manifiesto y comprueba que
`scenario.sha256` coincide con el archivo de escenario adyacente. Una
discrepancia detiene el recorrido antes de escribir un ajuste.

## Qué muestran las sesiones sintéticas

`fixtures/low.csv`, `medium.csv` y `high.csv` usan la cabecera del conversor de
OpenMATB y no contienen datos de participantes. Varían progresivamente el
tiempo de respuesta y los errores SYSMON, ISA `Workload` y los seis campos
NASA-TLX: `Mental demand`, `Physical demand`, `Time pressure`, `Performance`,
`Effort` y `Frustration`.

Cada fixture se convierte con `matb_integration.log_converter.convert_session`.
Las filas originales analizadas se conservan para el ajustador DEPDF, porque su
criterio actual de fallo deriva el tiempo hasta el fallo de eventos SYSMON
`MISS` observados. Los tres niveles incluyen al menos un error determinista.
Después, el recorrido llama a `fit_participant` con los registros LOW, MEDIUM y
HIGH para estimar G0, P0 y tau0; es una demostración sintética pequeña, no una
inferencia sobre una persona ni un sistema operativo.

## Continuar con artefactos de análisis

Las CLI estadísticas reciben arreglos JSON con las formas exactas devueltas por
la consola: `m.json` es la respuesta de `GET /metrics/long` y `f.json` la de
`GET /fits`. El comando frecuentista es:

```bash
python3 -m matb_integration.analysis.stats.cli run \
  --metrics-json m.json --fits-json f.json -o artifact.json
```

El comando separado de sensibilidad bayesiana usa los mismos dos arreglos JSON:

```bash
python3 -m matb_integration.analysis.stats.cli bayes \
  --metrics-json m.json --fits-json f.json -o bayes.json \
  --seed 42 --draws 1000 --tune 1000 --chains 4
```

El muestreo PyMC se excluye intencionalmente de este recorrido rápido. Ejecute
el comando bayesiano solo con un conjunto de investigación y un entorno de
muestreo apropiados.
