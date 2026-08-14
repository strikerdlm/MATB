# Recorrido del simulador sUAS sintético

[English](README.md)

Este simulador es determinista, no cinético y solo para investigación. No se
conecta con aeronaves, mapas reales, telemetría, armas ni servicios externos.
La API nativa valida identidades sUAS como `P` seguido de dígitos, por eso usa
el `P01` sintético; el recorrido de consola de investigación usa `SYNTH-P01`.
Consulte la [guía del backend](../../webui/backend/README.md) y la
[guía del frontend](../../webui/frontend/README.md) para los contratos completos.

## Instalación en Linux y WSL2

Use Python 3.12 y Node.js 20 o posterior. El lanzador POSIX se ejecuta en Linux
o WSL2; en Windows ejecútelo dentro de WSL2. **PowerShell 7+** (no Windows
PowerShell 5.1) puede llamar la API de loopback una vez que WSL2 hospeda el
servicio y es la shell compatible para los recorridos publicados. No sustituye
al lanzador.

```bash
MATB_VENV="$PWD/.venv-suas" bash scripts/install_suas.sh
MATB_VENV="$PWD/.venv-suas" bash scripts/run_suas.sh \
  --data-dir "$PWD/examples/output/suas-service"
```

La instalación inicial de dependencias con `pip` y `npm` requiere acceso de red
o una caché/espejo local preparado. Una vez instaladas las dependencias y los
artefactos de construcción del frontend, el lanzador inicia un servicio local
capaz de funcionar sin conexión: FastAPI en `127.0.0.1:8000` y la consola en
`127.0.0.1:3100`. Guarda SQLite, artefactos sellados y logs bajo el directorio
propiedad del operador, sin telemetría externa. Termine ambos con `Ctrl-C`.
Para un bind fuera de loopback defina explícitamente `MATB_FRONTEND_ORIGINS`;
el valor por defecto es loopback intencionalmente.

Para desarrollo nativo, cree el mismo entorno Python 3.12 desde
`requirements-dev.txt`; en `webui/backend` ejecute `python -m uvicorn
app.main:app --host 127.0.0.1 --port 8000`; en `webui/frontend`, ejecute
`npm install` y `npm run dev`. La UI de misión está en `/mission/setup` y
`/mission`.

## Ejecución determinista solo CLI

No requiere servicio ni navegador:

```bash
MATB_VENV="$PWD/.venv-suas" bash examples/suas-simulator/cli_demo.sh \
  "$PWD/examples/output/suas-simulator"
```

El wrapper usa `MATB_PYTHON` cuando se define explícitamente; de lo contrario
usa `$MATB_VENV/bin/python` y valida el ejecutable resuelto. Sin ninguno de los
dos valores usa `python3`; después de la instalación documentada, mantenga
`MATB_VENV` para que la CLI use ese entorno con dependencias instaladas.

Valida `scenarios/suas/reference_area_search.yaml`, avanza PRACTICE 10 ticks,
graba `SYNTH-SUAS-01` y verifica exactamente el directorio del primer argumento.
El grabador escribe directamente allí `events.jsonl`, `manifest.json`,
`metrics.json`, `debrief.json`, `replay-verification.json` y
`checksums.sha256`: no adivina ni busca una carpeta de sesión anidada. Seleccione
un directorio vacío; para reiniciar elimine solo ese directorio de demostración.

## Recorrido de API solo de ciclo de vida

Con el lanzador Linux/WSL2 activo, ejecute contra loopback:

```bash
BASE_URL=http://127.0.0.1:8000 bash examples/suas-simulator/api_walkthrough.sh
```

```powershell
.\examples\suas-simulator\api_walkthrough.ps1 -BaseUrl http://127.0.0.1:8000
```

Los clientes verifican salud, aseguran `P01`, listan escenarios, preparan
`reference_area_search`, inician solo PRACTICE, consultan estado público como
observador, finalizan completo y obtienen debrief y metadatos. El lease único
solo existe en una variable local y el encabezado `X-Simulation-Controller`;
nunca se imprime ni se pone en una URL. No se envía ningún comando de control
de aeronave.

Un controlador posee las mutaciones de ciclo de vida; observadores sin lease
solo ven estado público redactado. Una desconexión del controlador pausa la
sesión y no la reanuda automáticamente. La recuperación explícita desde un
checkpoint conserva la auditoría append-only y marca una desviación. Los
artefactos terminales son sellados; los metadatos públicos usan rutas relativas
y hashes, y eventos/probes privados no se exponen. En Linux/WSL2 verifique un
artefacto CLI con `$MATB_VENV/bin/python -m matb_integration.suas.cli verify
OUTPUT_DIRECTORY`.

Compruebe el servicio con `GET /health` y termine con `Ctrl-C`. Conserve el
directorio de datos como propiedad exclusiva y elimine solo un directorio de
demostración dedicado después de detener el servicio.
