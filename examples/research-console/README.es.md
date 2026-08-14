# Recorrido de la consola de investigación

[English](README.md)

Este recorrido local y sintético usa solamente `SYNTH-P01` y el fixture LOW
incluido. No representa a una persona ni un despliegue operativo. Para detalle
de endpoints y pantallas consulte la [guía del backend](../../webui/backend/README.md)
y la [guía del frontend](../../webui/frontend/README.md).

## Requisitos y desarrollo nativo

Se requieren Python 3.12 y Node.js 20 o posterior. En la raíz cree el entorno
Python e instale dependencias; después instale las dependencias Node del
frontend:

```bash
python3 -m venv .venv-suas
.venv-suas/bin/python -m pip install -r requirements-dev.txt
cd webui/frontend
npm install
```

Ejecute la API y la UI en terminales separadas. Los puertos por defecto son
8000 (API) y 3100 (frontend).

```bash
cd webui/backend
../../.venv-suas/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd webui/frontend
npm run dev -- --hostname 127.0.0.1 --port 3100
```

En Windows, PowerShell puede crear y activar un entorno Python 3.12, ejecutar
el módulo del backend desde `webui/backend` y ejecutar `npm install` y `npm run
dev` desde `webui/frontend`. Abra `http://127.0.0.1:3100`; por defecto consulta
la API local en `http://127.0.0.1:8000`, salvo que se defina
`NEXT_PUBLIC_API_URL`.

`MATB_DB_PATH` selecciona el archivo SQLite cuando está definido. Las cargas y
exportaciones quedan en la base y en un ZIP descargado; conserve estos datos en
directorios controlados por el propietario.

## Lanzador sin conexión

En Linux o WSL2, el lanzador crea el entorno, construye el frontend e inicia
ambos servicios locales:

```bash
MATB_VENV="$PWD/.venv-suas" bash scripts/install_suas.sh
MATB_VENV="$PWD/.venv-suas" bash scripts/run_suas.sh \
  --data-dir "$PWD/examples/output/research-console-service"
```

Usa 8000 y 3100 en loopback. Termine ordenadamente con `Ctrl-C`. Para un bind
que no sea loopback, defina antes `MATB_FRONTEND_ORIGINS` con orígenes
explícitos; no exponga el servicio de desarrollo por accidente.

## Recorrido de API

Con un servicio local iniciado, ejecute desde la raíz. `BASE_URL` y
`OUTPUT_DIR` cambian la dirección y el directorio del ZIP.

```bash
BASE_URL=http://127.0.0.1:8000 OUTPUT_DIR=/tmp/matb-console \
  bash examples/research-console/api_walkthrough.sh
```

```powershell
.\examples\research-console\api_walkthrough.ps1 -BaseUrl http://127.0.0.1:8000 -OutputDir C:\Temp\matb-console
```

El recorrido verifica salud, crea `SYNTH-P01` si falta, carga
`fixtures/low.csv` como visita 1/LOW, consulta tracker y contexto, y escribe
`research-bundle.zip`. Repetirlo en la misma base puede devolver 409: la
creación del participante se detecta, pero el SHA-256 duplicado y una celda
visita/nivel ya ocupada se rechazan intencionalmente. Use un `MATB_DB_PATH`
nuevo o limpie el directorio de datos de este ejemplo antes de repetir la carga.

La carga omite a propósito el manifiesto. Se acepta como `missing_manifest`; un
manifiesto malformado o inconsistente conserva sus problemas de validación. Un
solo bloque no es una visita completa ni un conjunto de análisis.

## Navegador y limpieza

Con el frontend en 3100, abra `/` (tracker), `/upload`, `/visualization`,
`/analysis` (análisis frecuentista, bayesiano y exportación), `/screen` y
`/participants`. Compruebe la API con `GET /health`. Detenga cada proceso con
`Ctrl-C`; para reiniciar, elimine únicamente la base SQLite o directorio de
datos dedicado al ejemplo después de detener los servicios, nunca una base de
estudio compartida.
