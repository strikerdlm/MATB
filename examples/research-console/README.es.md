# Recorrido de la consola de investigación

[English](README.md)

Este es un recorrido local y sintético de la consola de investigación FastAPI.
Usa únicamente `SYNTH-P01` y el recurso LOW confirmado en el repositorio; no es
un registro de participante ni un despliegue operacional. Para conocer los
detalles de endpoints y pantallas, consulte la
[guía del backend](../../webui/backend/README.md) y la
[guía del frontend](../../webui/frontend/README.md).

## Requisitos y desarrollo nativo

Use Python 3.12 y Node.js 20.9 o posterior. Desde la raíz del repositorio, cree
un venv e instale las dependencias del backend; después instale las dependencias
Node del frontend:

```bash
python3 -m venv .venv-suas
.venv-suas/bin/python -m pip install -r requirements-dev.txt
cd webui/frontend
npm install
```

Ejecute la API en una terminal y la UI del navegador en otra. El puerto
predeterminado de la API es 8000 y el del frontend es 3100.

Use un único worker de Uvicorn por base de datos. La API adquiere un
arrendamiento durable de instancia; un segundo backend vivo contra el mismo
SQLite falla de forma segura en lugar de repartir trabajos bayesianos y
escrituras entre ejecutores locales de procesos distintos.

```bash
cd webui/backend
../../.venv-suas/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd webui/frontend
npm run dev -- --hostname 127.0.0.1 --port 3100
```

En Windows use **PowerShell 7+** (no Windows PowerShell 5.1) para crear y
activar un entorno Python 3.12, ejecutar el módulo del backend desde
`webui/backend` y ejecutar `npm install` y `npm run dev` desde
`webui/frontend`. El recorrido de API también requiere PowerShell 7+ porque
usa `Invoke-RestMethod -Form`. Abra `http://127.0.0.1:3100`; por defecto
consulta la API local en `http://127.0.0.1:8000`, salvo que se defina
`NEXT_PUBLIC_API_URL`.

La API almacena datos SQLite en `MATB_DB_PATH` cuando está definido; de lo
contrario se aplica su valor predeterminado de desarrollo. Los bloques cargados
y las solicitudes de exportación se convierten, respectivamente, en filas de
la base de datos y un ZIP descargado. Mantenga cada base de datos de estudio y
directorio de exportación bajo el control del propietario.

## Lanzador sin conexión

En Linux o WSL2, el lanzador crea el entorno Python, compila el frontend e
inicia ambos servicios. La instalación inicial de dependencias con `pip` y
`npm` requiere acceso a la red o una caché/espejo local de paquetes preparado.
Después de instalar las dependencias y los artefactos de compilación del
frontend, el servicio iniciado es local y capaz de funcionar sin conexión; no
es un servicio expuesto a Internet.

```bash
MATB_VENV="$PWD/.venv-suas" bash scripts/install_suas.sh
MATB_VENV="$PWD/.venv-suas" bash scripts/run_suas.sh \
  --data-dir "$PWD/examples/output/research-console-service"
```

El lanzador usa de forma predeterminada los puertos 8000 y 3100 en loopback.
Presione `Ctrl-C` en su terminal para una detención ordenada. Si elige un enlace
que no sea loopback, configure primero un valor explícito de
`MATB_FRONTEND_ORIGINS`; no exponga involuntariamente el servicio de desarrollo
predeterminado.

## Recorrido de API

Inicie primero cualquiera de los servicios locales y después ejecute uno de
estos comandos desde la raíz del repositorio. `BASE_URL` y `OUTPUT_DIR`
sustituyen la dirección loopback y el directorio de salida del ZIP. Cargue el
token de propietario creado por el lanzador para las mutaciones CLI.

```bash
export MATB_API_TOKEN="$(<examples/output/research-console-service/api-token)"
BASE_URL=http://127.0.0.1:8000 OUTPUT_DIR=/tmp/matb-console \
  bash examples/research-console/api_walkthrough.sh
```

```powershell
$env:MATB_API_TOKEN = Read-Host "Token API de MATB"
.\examples\research-console\api_walkthrough.ps1 -BaseUrl http://127.0.0.1:8000 -OutputDir C:\Temp\matb-console
```

El recorrido comprueba la salud, crea `SYNTH-P01` solo cuando no existe, carga
`fixtures/low.csv` como visita 1/LOW, solicita de forma segura `POST /analysis/run`,
imprime y valida los valores `analysis_status` por métrica devueltos, consulta el
seguimiento y el contexto de investigación, y escribe `research-bundle.zip`. Solo
admite los estados `ok`, `insufficient_data` o `not_estimable` del motor; se espera
que el recurso de una fila siga siendo insuficiente para muchos ajustes. Repetirlo contra la misma base
de datos puede devolver 409: se detecta la creación del participante, pero se
rechazan deliberadamente un SHA-256 de CSV duplicado y una celda de
visita/carga de trabajo ya ocupada. Limpie el directorio de datos del ejemplo
(o use un `MATB_DB_PATH` nuevo) antes de repetir una ingesta completa.

La carga omite deliberadamente un manifiesto de escenario. Esto se acepta y se
muestra como `missing_manifest`; un manifiesto malformado o no coincidente se
conserva con problemas de validación en vez de aceptarse silenciosamente. No
interprete el recorrido de una sola fila como una visita completa ni como un
conjunto de datos de análisis.

Esta superficie carga CSV heredado, no el flujo autoritativo v3 de
eventos/temporización. Cada registro derivado se marca como
`legacy_csv_derived_not_reconciled_to_authoritative_event_stream`; la
elegibilidad confirmatoria permanece falsa incluso con un manifiesto válido.
La ingesta JSONL emparejada y la reconciliación por ID de evento son una
compuerta explícita para la publicación pública.

## Navegador y limpieza

Con el frontend en el puerto 3100, visite:

- `http://127.0.0.1:3100/` para el seguimiento;
- `/upload` para ingerir el CSV y el manifiesto opcional;
- `/visualization` para gráficos descriptivos;
- `/analysis` para el análisis frecuentista y bayesiano y la exportación del paquete de investigación;
- `/screen` para la evaluación inicial; y
- `/participants` para las identidades seudonimizadas del estudio.

Use `GET /health` (o la primera solicitud del recorrido) para comprobar la API.
Detenga el desarrollo nativo con `Ctrl-C` en cada terminal. Para restablecer este
ejemplo, detenga los servicios y elimine únicamente el directorio de datos del
ejemplo seleccionado o su archivo SQLite dedicado; nunca una base de datos de
estudio compartida.

Las solicitudes nuevas de adquisición deben incluir `execution_purpose` (`study`
o `practice`). Los modos rápidos de screen/PVT requieren `practice`. Las vistas
incluyen `purpose_provenance_id`; la API local conserva el historial inmutable y
la intención histórica desconocida. Consulte el
[contrato del backend](../../webui/backend/README.md#acquisition-purpose-and-historical-provenance).
