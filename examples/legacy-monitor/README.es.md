# Flujos del monitor de aeronaves heredado

[English](README.md)

Estos lanzadores nativos ejecutan los modos heredados de aircraft-monitor con
`--seed 42`, `--headless` y el retardo mínimo compatible de `0.05` segundos.
No cambian el comportamiento de la aplicación.

## Ejecutar un modo

El lanzador Bash acepta un modo y, opcionalmente, un directorio de salida
seleccionado por quien lo ejecuta. Por defecto usa `combined` y solo entrega
ese directorio a la aplicación en modo `experiment`.

```bash
examples/legacy-monitor/run.sh uav
examples/legacy-monitor/run.sh fighter
examples/legacy-monitor/run.sh combined
examples/legacy-monitor/run.sh experiment /tmp/legacy-monitor
```

El lanzador PowerShell tiene el mismo contrato y restringe el modo a los cuatro
valores admitidos:

```powershell
.\examples\legacy-monitor\run.ps1 -Mode uav
.\examples\legacy-monitor\run.ps1 -Mode fighter
.\examples\legacy-monitor\run.ps1 -Mode combined
.\examples\legacy-monitor\run.ps1 -Mode experiment -OutputDir C:\Temp\legacy-monitor
```

Para `experiment`, el lanzador añade los identificadores sintéticos
`SYNTH-P01` y `SYNTH-S01`, además de `--research-output-dir`. Por ello, los
artefactos del experimento se escriben solo debajo del directorio que usted
selecciona. Las otras tres simulaciones no reciben un directorio de salida de
investigación.

## Finalización, interrupción y limpieza

Las ejecuciones correctas imprimen `Simulation complete!`. Presione Ctrl-C
para detener una ejecución; la aplicación informa que fue terminada por el
usuario y finaliza con normalidad.

Inspeccione un directorio de salida de experimento antes de conservar o
compartir cualquier archivo:

```bash
find /tmp/legacy-monitor -maxdepth 2 -type f
```

La ubicación predeterminada de los experimentos es
`examples/output/legacy-monitor`. Para eliminar solo esos artefactos de ejemplo
predeterminados, use:

```bash
rm -rf examples/output/legacy-monitor
```

No use esa limpieza para un directorio seleccionado por usted salvo que sea el
directorio que realmente desea eliminar.
