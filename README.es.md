# MATB — Investigación de factores humanos y aseguramiento de la seguridad operacional aeronáutica

[English](README.md) | [Español](README.es.md)

> Software exclusivo para investigación y aseguramiento de la seguridad operacional. MATB no es un dispositivo clínico,
> un sistema operacional certificado, un canal de control de aeronaves, un sistema de armas ni un
> sustituto de la aprobación humana responsable.

MATB reúne en un repositorio varios flujos que pueden instalarse de forma independiente:
herramientas de estudio compatibles con OpenMATB, una consola local de investigación, un simulador
determinista de sistemas de aeronaves pequeñas no tripuladas (sUAS), un sistema de gestión de la
seguridad operacional (SMS) FAC ISR con prioridad para el funcionamiento sin conexión y una demostración
conservada de monitor de aeronaves en terminal. Elija un flujo a continuación; no necesita instalar los demás.

<a id="identity-and-safety"></a>
## 1. Identidad, uso previsto y límite de seguridad operacional

La superficie activa de investigación en Python genera escenarios y procedencia, convierte registros
CSV de OpenMATB, calcula resultados descriptivos, frecuentistas y bayesianos, ajusta un modelo DEPDF
de Suhir intraparticipante y admite una evaluación neurocognitiva exploratoria. OpenMATB es externo y
no se incluye en este repositorio.

La Consola de Investigación es una aplicación FastAPI/Next.js enlazada a loopback, con SQLite y
almacenamiento local de artefactos. Su superficie sUAS es un simulador sintético, no cinético y de
supervisión. No contiene aeronaves reales, armas, selección de blancos, despacho autónomo, mapas del
mundo real, telemetría externa ni rutas de mando y control (C2).

El espacio de trabajo `SMS/` evalúa evidencia controlada, telemetría de solo lectura, compuertas de
seguridad operacional, registros organizacionales del SMS y artefactos de revisión institucional. Que un
componente pase, una compilación finalice correctamente o una matriz de verificación se complete no es
una autorización para operar. La evidencia dura ausente, vencida, no confiable o no aceptada produce un
bloqueo seguro; los revisores institucionales responsables conservan la autoridad de decisión.

Use únicamente identidades de investigación seudónimas. Mantenga los datos del estudio, la evidencia
controlada, el material de firma, el material TLS, los arrendamientos del controlador y las decisiones
institucionales fuera del repositorio y bajo los controles de custodia de la institución propietaria.

<a id="choose-a-workflow"></a>
## 2. Elija un flujo de trabajo

| Objetivo | Comience aquí | Entorno de ejecución | Ejemplo | Resultado esperado |
| --- | --- | --- | --- | --- |
| Generar escenarios de OpenMATB, convertir registros o probar el análisis DEPDF | `matb_integration/` | Python; OpenMATB externo solo para presentar la tarea a participantes | [Recorrido de investigación OpenMATB](examples/openmatb-research/README.es.md) | Tres escenarios/manifiestos, métricas JSONL sintéticas y un JSON DEPDF |
| Ingerir sesiones, dar seguimiento a visitas, visualizar datos, analizar y exportar | `webui/` | Python 3.12+, Node 20+, navegador local | [Recorrido de la Consola de Investigación](examples/research-console/README.es.md) | Registros SQLite locales y `research-bundle.zip` |
| Ejecutar una sesión de investigación sUAS determinista y segura para observadores | `matb_integration/suas/` y `webui/` | Python 3.12+; Node 20+ para el servicio de navegador | [Recorrido del simulador sUAS](examples/suas-simulator/README.es.md) | Eventos verificables por reproducción, métricas, informe final, manifiesto y sumas de comprobación |
| Evaluar contratos de paquetes de gestión de la seguridad operacional sin conexión | `SMS/` | Node 22.x; Docker solo para la imagen/paquete sin conexión | [Recorrido de capacidades del SMS](examples/sms-platform/README.es.md) | JSON determinista con un resultado del núcleo de seguridad operacional bloqueado deliberadamente |
| Demostrar el monitor de terminal anterior | `aircraft_monitor/` | Python y una terminal | [Guía del monitor heredado](examples/legacy-monitor/README.es.md) | Flujo de eventos de UAV, caza, combinado o experimento en modo sin interfaz gráfica |

El [índice de ejemplos](examples/README.es.md) compara los ejemplos rápidos sin conexión con los
procedimientos de servicio, navegador, Docker y entorno de ejecución externo.

<a id="architecture-and-data-flow"></a>
## 3. Arquitectura y movimiento de datos

```text
MATB/
├── matb_integration/       Python scenario, conversion, analysis, screen, and sUAS libraries
├── scenarios/              committed OpenMATB and synthetic sUAS scenarios
├── webui/                  FastAPI backend and Next.js Research Console
├── SMS/                    Node/TypeScript safety-management monorepo
├── aircraft_monitor/       retained Rich terminal demonstrations
├── examples/               deterministic synthetic workflow tours
├── scripts/                native sUAS install/launch and documentation verification
├── tests/                  Python, integration, sUAS, and documentation suites
└── docs/                   scientific, implementation, design, and verification detail
```

Los cuatro flujos principales se mantienen separados de forma deliberada:

```text
External OpenMATB -> session CSV + scenario manifest -> metrics -> DEPDF/statistics -> research bundle
Browser -> FastAPI Research Console -> local SQLite/artifacts -> tracker/analysis/export
Synthetic YAML -> deterministic sUAS engine -> observer-safe state -> replay/debrief artifacts
Signed local evidence + read-only telemetry -> edge API/safety kernel -> console/audit -> offline verification
```

La base de datos de investigación no es una base de datos operacional. `SMS/packages/research/`
y el dominio operacional del SMS tienen comprobaciones explícitas de separación. La telemetría es
de solo lectura y ninguna aplicación expone un canal de mando del vehículo.

<a id="prerequisites"></a>
## 4. Matriz de prerrequisitos

| Dependencia | Versión o función | Herramientas OpenMATB | Consola de Investigación | sUAS | `SMS/` | Monitor heredado |
| --- | --- | --- | --- | --- | --- | --- |
| Git | Clonación/control de versiones | Obligatorio | Obligatorio | Obligatorio | Obligatorio | Obligatorio |
| Python | El instalador de sUAS requiere 3.12+; use la misma versión para los flujos Python del repositorio | Obligatorio | Obligatorio | Obligatorio | No | Obligatorio |
| Node.js | El lanzador comprueba 20+; el frontend usa npm | No | 20+ obligatorio | 20+ para el servicio de navegador | **22.x obligatorio** | No |
| npm | Herramienta de dependencias/compilación basada en el archivo de bloqueo | No | Obligatorio para el frontend | Obligatorio para el servicio de navegador | Obligatorio | No |
| OpenMATB externo | Ejecutor de tareas independiente con sus propias dependencias | Específico del flujo | Solo para recopilar sesiones de tareas reales | No | No | No |
| Xvfb | Pantalla X virtual para OpenMATB/Pyglet externo en Linux sin interfaz gráfica | Específico del flujo | No | No; la interfaz nativa usa navegador/modo sin interfaz gráfica | No | No en modo `--headless` |
| Chromium | Uso del navegador; Chromium de Playwright solo se necesita para las compuertas E2E/accesibilidad del navegador | Opcional | Navegador obligatorio; recurso de Playwright opcional | Navegador obligatorio para la UI; opcional para CLI | Recurso opcional de prueba de consola | No |
| Docker | Motor de contenedores Linux e imagen base preparada | No | No | No | Específico del flujo para imagen/paquete sin conexión | No |
| WSL2 | Límite POSIX en Windows | Para `setup.sh` o el procedimiento Linux/Xvfb | Solo para el lanzador POSIX combinado | Obligatorio en Windows para `install_suas.sh`/`run_suas.sh` | Para scripts POSIX, permisos Linux y verificación Docker | No obligatorio |

Windows nativo admite los ejemplos PowerShell/Python/Node. No convierte los lanzadores de shell
POSIX, los puntos de entrada de contenedores Linux, el comportamiento de `chmod`/UID ni Xvfb en
procedimientos nativos de Windows. Use WSL2 para esas rutas. Los recorridos de API en PowerShell
requieren PowerShell 7+ porque usan `Invoke-RestMethod -Form`.

Compruebe solo las herramientas necesarias para el flujo seleccionado.

```bash
git --version
python3 --version
node --version
npm --version
```

```powershell
git --version
python --version
node --version
npm --version
$PSVersionTable.PSVersion
```

<a id="quick-start-openmatb"></a>
## 5. Inicio rápido de investigación OpenMATB

Este inicio rápido es completamente sintético. El entorno de ejecución externo de OpenMATB solo es
necesario cuando se presentan las tareas generadas a un participante.

<h3>Prerrequisitos</h3>

Use Git y Python 3.12+. Para presentar tareas a participantes, proporcione un checkout independiente
de OpenMATB. La presentación en Linux/sin interfaz gráfica también necesita Xvfb y una pantalla
Pyglet funcional; Windows nativo ejecuta directamente el entorno de escritorio externo.

<h3>Instalación</h3>

Bash de Linux o WSL2, desde la raíz del clon:

```bash
REPO_ROOT="$(pwd)"
python3 -m venv "$REPO_ROOT/.venv-openmatb"
"$REPO_ROOT/.venv-openmatb/bin/python" -m pip install -r "$REPO_ROOT/requirements-dev.txt"
```

`setup.sh` es solo para POSIX e instala el `requirements.txt` base, más limitado, para la integración
de recursos heredados/OpenMATB. No sustituye la instalación de dependencias de desarrollo anterior
cuando se ejecuta el ejemplo de DEPDF/estadísticas.

```bash
REPO_ROOT="$(pwd)"
MATB_VENV="$REPO_ROOT/.venv-openmatb" bash "$REPO_ROOT/setup.sh"
```

PowerShell 7+ en Windows nativo:

```powershell
$RepoRoot = (Get-Location).Path
python -m venv (Join-Path $RepoRoot ".venv-openmatb")
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") -m pip install -r (Join-Path $RepoRoot "requirements-dev.txt")
```

<h3>Configuración</h3>

La generación sintética no necesita configuración. Para instalar recursos en un checkout externo
derivado de la ubicación del clon:

```bash
REPO_ROOT="$(pwd)"
OPENMATB_DIR="$REPO_ROOT/../openmatb"
"$REPO_ROOT/.venv-openmatb/bin/python" "$REPO_ROOT/install_to_openmatb.py" "$OPENMATB_DIR"
```

```powershell
$RepoRoot = (Get-Location).Path
$OpenMatbDir = (Resolve-Path (Join-Path $RepoRoot "..\openmatb")).Path
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") (Join-Path $RepoRoot "install_to_openmatb.py") $OpenMatbDir
```

El checkout externo debe contener `includes/`. Configure su propio entorno y selector de escenarios
según ese entorno de ejecución. No apunte el instalador a este repositorio.

<h3>Ejecución</h3>

Genere la estructura del protocolo confirmado en el repositorio sin iniciar OpenMATB:

```bash
REPO_ROOT="$(pwd)"
"$REPO_ROOT/.venv-openmatb/bin/python" -m matb_integration.scenario_builder \
  --output-dir "$REPO_ROOT/examples/output/generated-scenarios" --block-duration 900 --seed 42
```

```powershell
$RepoRoot = (Get-Location).Path
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") -m matb_integration.scenario_builder `
  --output-dir (Join-Path $RepoRoot "examples\output\generated-scenarios") --block-duration 900 --seed 42
```

Para usar OpenMATB externo en Linux, ejecute su `main.py` dentro de su propio entorno. Use `DISPLAY`
y Xvfb solo en un host Linux/sin interfaz gráfica. Windows nativo no usa Xvfb.

<h3>Prueba del ejemplo sintético</h3>

```bash
REPO_ROOT="$(pwd)"
MATB_PYTHON="$REPO_ROOT/.venv-openmatb/bin/python" \
  bash "$REPO_ROOT/examples/openmatb-research/run.sh" "$REPO_ROOT/examples/output/openmatb-research"
```

```powershell
$RepoRoot = (Get-Location).Path
$env:MATB_PYTHON = Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe"
& (Join-Path $RepoRoot "examples\openmatb-research\run.ps1") -OutputDir (Join-Path $RepoRoot "examples\output\openmatb-research")
```

<h3>Resultado esperado</h3>

El recorrido escribe tres archivos `scenarios/*.txt` con manifiestos adyacentes, `metrics.jsonl` y
`suhir.json`; después imprime `External OpenMATB was not started.` El recurso contiene únicamente
`SYNTH-P01`; no son datos de participantes.

<h3>Verificación</h3>

```bash
REPO_ROOT="$(pwd)"
"$REPO_ROOT/.venv-openmatb/bin/python" -m pytest \
  "$REPO_ROOT/tests/test_scenario_builder.py" \
  "$REPO_ROOT/tests/test_scenario_manifest.py" \
  "$REPO_ROOT/tests/test_log_converter.py" \
  "$REPO_ROOT/tests/analysis_stats" "$REPO_ROOT/tests/suhir" "$REPO_ROOT/tests/screen" -q
```

```powershell
$RepoRoot = (Get-Location).Path
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") -m pytest `
  (Join-Path $RepoRoot "tests\test_scenario_builder.py") `
  (Join-Path $RepoRoot "tests\test_scenario_manifest.py") `
  (Join-Path $RepoRoot "tests\test_log_converter.py") `
  (Join-Path $RepoRoot "tests\analysis_stats") (Join-Path $RepoRoot "tests\suhir") (Join-Path $RepoRoot "tests\screen") -q
```

<h3>Detención y limpieza</h3>

Detenga OpenMATB externo o Xvfb con Ctrl-C. Elimine solo la salida sintética seleccionada, nunca un
entorno de ejecución externo ni un almacén de sesiones.

```bash
REPO_ROOT="$(pwd)"
rm -rf -- "$REPO_ROOT/examples/output/openmatb-research" "$REPO_ROOT/examples/output/generated-scenarios"
```

```powershell
$RepoRoot = (Get-Location).Path
Remove-Item -Recurse -Force (Join-Path $RepoRoot "examples\output\openmatb-research"), (Join-Path $RepoRoot "examples\output\generated-scenarios") -ErrorAction SilentlyContinue
```

<h3>Solución de problemas</h3>

Un error `includes/ not found` indica que el checkout externo seleccionado es incorrecto.
`ModuleNotFoundError` suele indicar que el venv del repositorio o del entorno externo está inactivo.
En Linux, los fallos de pantalla/parpadeo/Pyglet pertenecen al límite externo OpenMATB/X11: valide
`DISPLAY`, use Xvfb en hosts sin interfaz gráfica y comience en modo de ventana. Consulte el
[ejemplo completo de OpenMATB](examples/openmatb-research/README.es.md).

<a id="quick-start-research-console"></a>
## 6. Inicio rápido de la Consola de Investigación

<h3>Prerrequisitos</h3>

Use Python 3.12+, Node 20+, npm y un navegador. La instalación inicial de dependencias necesita
acceso a la red o cachés preparados de Python/npm; el servicio instalado es local y puede funcionar
sin conexión.

<h3>Instalación</h3>

Lanzador combinado de Linux o WSL2:

```bash
REPO_ROOT="$(pwd)"
MATB_VENV="$REPO_ROOT/.venv-console" bash "$REPO_ROOT/scripts/install_suas.sh"
```

Instalación de desarrollo en PowerShell 7+ de Windows nativo:

```powershell
$RepoRoot = (Get-Location).Path
python -m venv (Join-Path $RepoRoot ".venv-console")
& (Join-Path $RepoRoot ".venv-console\Scripts\python.exe") -m pip install -r (Join-Path $RepoRoot "requirements-dev.txt")
Set-Location (Join-Path $RepoRoot "webui\frontend")
npm ci
Set-Location $RepoRoot
```

<h3>Configuración</h3>

Elija una raíz de datos dedicada. El lanzador POSIX configura `MATB_DB_PATH`,
`MATB_SIMULATION_OUTPUT_DIR`, `MATB_SIMULATION_SCENARIO_DIR` y
`MATB_FRONTEND_ORIGINS`. Para desarrollo nativo:

```bash
REPO_ROOT="$(pwd)"
export MATB_DB_PATH="$REPO_ROOT/examples/output/research-console-service/matb.db"
export MATB_FRONTEND_ORIGINS="http://127.0.0.1:3100"
```

```powershell
$RepoRoot = (Get-Location).Path
$DataRoot = Join-Path $RepoRoot "examples\output\research-console-service"
New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
$env:MATB_DB_PATH = Join-Path $DataRoot "matb.db"
$env:MATB_FRONTEND_ORIGINS = "http://127.0.0.1:3100"
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
```

<h3>Ejecución</h3>

Linux/WSL2 inicia ambos servicios compilados y aplica permisos POSIX exclusivos del propietario:

```bash
REPO_ROOT="$(pwd)"
MATB_VENV="$REPO_ROOT/.venv-console" bash "$REPO_ROOT/scripts/run_suas.sh" \
  --data-dir "$REPO_ROOT/examples/output/research-console-service"
```

Windows nativo usa dos terminales de PowerShell. Backend:

```powershell
$RepoRoot = (Get-Location).Path
Set-Location (Join-Path $RepoRoot "webui\backend")
& (Join-Path $RepoRoot ".venv-console\Scripts\python.exe") -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
$RepoRoot = (Get-Location).Path
Set-Location (Join-Path $RepoRoot "webui\frontend")
npm run dev -- --hostname 127.0.0.1 --port 3100
```

Abra `http://127.0.0.1:3100/`.

<h3>Prueba del ejemplo sintético</h3>

Con el servicio en ejecución:

```bash
REPO_ROOT="$(pwd)"
BASE_URL=http://127.0.0.1:8000 OUTPUT_DIR="$REPO_ROOT/examples/output/research-console-tour" \
  bash "$REPO_ROOT/examples/research-console/api_walkthrough.sh"
```

```powershell
$RepoRoot = (Get-Location).Path
& (Join-Path $RepoRoot "examples\research-console\api_walkthrough.ps1") `
  -BaseUrl http://127.0.0.1:8000 -OutputDir (Join-Path $RepoRoot "examples\output\research-console-tour")
```

<h3>Resultado esperado</h3>

La comprobación de salud tiene éxito; el participante sintético `SYNTH-P01` tiene un bloque de visita
LOW; se imprimen los JSON de seguimiento/contexto y se escribe `research-bundle.zip`. El estado de
manifiesto ausente es deliberado y no debe interpretarse como un estudio completo.

<h3>Verificación</h3>

```bash
curl --fail http://127.0.0.1:8000/health
```

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Los conjuntos de pruebas de backend y frontend se enumeran en la sección de operaciones.

<h3>Detención y limpieza</h3>

Presione Ctrl-C en el lanzador combinado o en ambas terminales de desarrollo nativo. Cuando los
servicios se hayan detenido, elimine solo los directorios dedicados del ejemplo:

```bash
REPO_ROOT="$(pwd)"
rm -rf -- "$REPO_ROOT/examples/output/research-console-service" "$REPO_ROOT/examples/output/research-console-tour"
```

```powershell
$RepoRoot = (Get-Location).Path
Remove-Item -Recurse -Force (Join-Path $RepoRoot "examples\output\research-console-service"), (Join-Path $RepoRoot "examples\output\research-console-tour") -ErrorAction SilentlyContinue
```

<h3>Solución de problemas</h3>

Un 409 al repetir la ejecución significa que ya existe el hash del CSV o la celda de visita/carga de
trabajo; use una base de datos dedicada nueva. Si 8000 o 3100 está ocupado, detenga el otro proceso
o indique puertos distintos al lanzador y alinee `NEXT_PUBLIC_API_URL`. Los fallos de política de
ejecución o de comillas de PowerShell pueden evitarse usando PowerShell 7 y el operador de llamada `&`
con `Join-Path`. Consulte la [guía de la Consola de Investigación](examples/research-console/README.es.md).

<a id="quick-start-suas"></a>
## 7. Inicio rápido del sUAS sintético

<h3>Prerrequisitos</h3>

La CLI necesita Python 3.12+. El servicio de navegador añade Node 20+, npm y un navegador.
`install_suas.sh` y `run_suas.sh` son contratos para Linux/WSL2; PowerShell de Windows nativo
puede ejecutar la CLI y puede llamar a un servicio alojado en WSL2.

<h3>Instalación</h3>

Instalación del servicio en Linux/WSL2:

```bash
REPO_ROOT="$(pwd)"
MATB_VENV="$REPO_ROOT/.venv-suas" bash "$REPO_ROOT/scripts/install_suas.sh"
```

Instalación exclusiva de la CLI en Windows nativo:

```powershell
$RepoRoot = (Get-Location).Path
python -m venv (Join-Path $RepoRoot ".venv-suas")
& (Join-Path $RepoRoot ".venv-suas\Scripts\python.exe") -m pip install -r (Join-Path $RepoRoot "requirements-dev.txt")
```

<h3>Configuración</h3>

El servicio usa de forma predeterminada los escenarios validados de `scenarios/suas/`, los puertos
loopback 8000/3100 y una raíz de salida dedicada. Se rechaza un enlace que no sea loopback salvo que
`MATB_FRONTEND_ORIGINS` se configure explícitamente. No exponga el servicio de desarrollo a una red
no confiable.

```bash
REPO_ROOT="$(pwd)"
export MATB_SIMULATION_SCENARIO_DIR="$REPO_ROOT/scenarios/suas"
```

```powershell
$RepoRoot = (Get-Location).Path
$env:MATB_SIMULATION_SCENARIO_DIR = Join-Path $RepoRoot "scenarios\suas"
```

<h3>Ejecución</h3>

Servicio de navegador en Linux/WSL2:

```bash
REPO_ROOT="$(pwd)"
MATB_VENV="$REPO_ROOT/.venv-suas" bash "$REPO_ROOT/scripts/run_suas.sh" \
  --data-dir "$REPO_ROOT/examples/output/suas-service"
```

En Windows nativo, inicie ese comando dentro de WSL2 y después abra la URL loopback desde Windows
o use el recorrido de PowerShell. El lanzador POSIX es responsable del inicio y la detención del
servicio, de los grupos de procesos y de los permisos Unix.

<h3>Prueba del ejemplo sintético</h3>

Recorrido rápido exclusivo de CLI en Linux/WSL2:

```bash
REPO_ROOT="$(pwd)"
MATB_VENV="$REPO_ROOT/.venv-suas" \
  bash "$REPO_ROOT/examples/suas-simulator/cli_demo.sh" "$REPO_ROOT/examples/output/suas-simulator"
```

Equivalente para Windows nativo, con el mismo escenario confirmado en el repositorio:

```powershell
$RepoRoot = (Get-Location).Path
$Python = Join-Path $RepoRoot ".venv-suas\Scripts\python.exe"
$Scenario = Join-Path $RepoRoot "scenarios\suas\reference_area_search.yaml"
$Output = Join-Path $RepoRoot "examples\output\suas-simulator"
& $Python -m matb_integration.suas.cli validate $Scenario
& $Python -m matb_integration.suas.cli record $Scenario --block PRACTICE --ticks 10 --session-id SYNTH-SUAS-01 --output $Output
& $Python -m matb_integration.suas.cli verify $Output
```

El recorrido de la API del servicio está disponible en Bash y PowerShell; usa un arrendamiento solo
en el encabezado `X-Simulation-Controller` y nunca envía un mando de aeronave.

<h3>Resultado esperado</h3>

El directorio de salida de la CLI contiene `events.jsonl`, `manifest.json`, `metrics.json`,
`debrief.json`, `replay-verification.json` y `checksums.sha256`. El servicio expone estado seguro para
observadores y metadatos de artefactos terminales sellados. Una desconexión del controlador pausa la
sesión; nunca la reanuda automáticamente.

<h3>Verificación</h3>

```bash
REPO_ROOT="$(pwd)"
"$REPO_ROOT/.venv-suas/bin/python" -m matb_integration.suas.cli verify "$REPO_ROOT/examples/output/suas-simulator"
```

```powershell
$RepoRoot = (Get-Location).Path
& (Join-Path $RepoRoot ".venv-suas\Scripts\python.exe") -m matb_integration.suas.cli verify (Join-Path $RepoRoot "examples\output\suas-simulator")
```

<h3>Detención y limpieza</h3>

Presione Ctrl-C en el lanzador. Cuando termine, elimine solo las raíces de demostración elegidas:

```bash
REPO_ROOT="$(pwd)"
rm -rf -- "$REPO_ROOT/examples/output/suas-service" "$REPO_ROOT/examples/output/suas-simulator"
```

```powershell
$RepoRoot = (Get-Location).Path
Remove-Item -Recurse -Force (Join-Path $RepoRoot "examples\output\suas-simulator") -ErrorAction SilentlyContinue
```

<h3>Solución de problemas</h3>

La grabación rechaza un directorio de salida que no esté vacío; seleccione uno nuevo. Los errores de
compilación ausente del frontend o de venv indican que `install_suas.sh` no se completó. Los usuarios
de WSL2 deben mantener el clon y los datos en un sistema de archivos WSL para obtener permisos
predecibles y comprobar el reenvío loopback de Windows a WSL. Consulte el
[recorrido de sUAS](examples/suas-simulator/README.es.md).

<a id="quick-start-sms"></a>
## 8. Inicio rápido del SMS FAC ISR

<h3>Prerrequisitos</h3>

Use Node.js 22.x y npm. Docker con compatibilidad para contenedores Linux solo es necesario para
`build:offline` y la verificación de contenedores, no para el recorrido de paquetes.

<h3>Instalación</h3>

```bash
REPO_ROOT="$(pwd)"
cd "$REPO_ROOT/SMS"
npm ci
```

```powershell
$RepoRoot = (Get-Location).Path
Set-Location (Join-Path $RepoRoot "SMS")
npm ci
```

`npm ci` puede necesitar la red en una estación de desarrollo; un host aislado debe tener preparada
de antemano la caché de dependencias bloqueadas.

<h3>Configuración</h3>

El recorrido de paquetes no requiere credenciales, material de firma, telemetría ni configuración de
servicios. Para el despliegue Docker, las instituciones suministran `SMS_DATA_DIR`,
`SMS_PACKAGE_DIR` de solo lectura y `SMS_TLS_DIR` mediante custodia aprobada. `SMS_EDGE_PORT`
solo cambia el puerto loopback del host. No cree claves de demostración ni coloque material controlado
en el repositorio.

<h3>Ejecución</h3>

```bash
REPO_ROOT="$(pwd)"
bash "$REPO_ROOT/examples/sms-platform/run.sh"
```

```powershell
$RepoRoot = (Get-Location).Path
& (Join-Path $RepoRoot "examples\sms-platform\run.ps1")
```

Los ejecutores instalan las dependencias bloqueadas, compilan los nueve paquetes e imprimen el
recorrido determinista de paquetes.

<h3>Prueba del ejemplo sintético</h3>

Después de la primera compilación, repita directamente el ejecutable que no usa la red:

```bash
REPO_ROOT="$(pwd)"
cd "$REPO_ROOT/SMS"
node ../examples/sms-platform/package-tour.mjs
```

```powershell
$RepoRoot = (Get-Location).Path
Set-Location (Join-Path $RepoRoot "SMS")
node ..\examples\sms-platform\package-tour.mjs
```

<h3>Resultado esperado</h3>

Un documento JSON contiene las nueve claves de paquete. El requisito duro sintético deja
deliberadamente bloqueado `safetyKernel.status` y `research.nonDispatchable` permanece true.
No se crea ningún servicio, decisión, liberación ni estado de preparación operacional.

<h3>Verificación</h3>

```bash
REPO_ROOT="$(pwd)"
cd "$REPO_ROOT/SMS"
npm test
npm run typecheck
npm run verify:no-c2
npm run verify:data-separation
```

```powershell
$RepoRoot = (Get-Location).Path
Set-Location (Join-Path $RepoRoot "SMS")
npm test
npm run typecheck
npm run verify:no-c2
npm run verify:data-separation
```

Ejecute la verificación Docker/sin conexión solo en Linux, WSL2 o un entorno de contenedores Linux
con todas las entradas fijadas previamente preparadas. Un *entorno de ejecución* sin conexión no
implica que una compilación sin preparar pueda acceder a dependencias o imágenes ausentes.

<h3>Detención y limpieza</h3>

El recorrido de paquetes no inicia servicios. Si inició un servidor de desarrollo, use Ctrl-C.
`SMS/node_modules/` y `SMS/packages/*/dist/` generados son productos locales; inspeccione
`git status` y elimine solo esas rutas generadas conocidas cuando quiera intencionalmente una
instalación limpia. Nunca elimine datos controlados ni un volumen Docker compartido como parte de
la limpieza de un ejemplo.

<h3>Solución de problemas</h3>

Una advertencia del motor indica que Node no es 22.x. Los errores del daemon de Docker o de imagen
base ausente pertenecen al límite de compilación preparada. La verificación de evidencia puede fallar
por discrepancia de hash, alteración, artefactos fuente ausentes o vencimiento; restaure evidencia
aprobada u obtenga una liberación autorizada vigente; nunca omita comprobaciones de vigencia, firma
o hash. Que la preparación permanezca false después de que pasen las pruebas es una separación
esperada entre verificación técnica y aceptación institucional. Consulte la
[guía del SMS](examples/sms-platform/README.es.md).

<a id="quick-start-legacy-monitor"></a>
## 9. Inicio rápido del monitor heredado

<h3>Prerrequisitos</h3>

Use Python 3.12+ y una terminal. Los lanzadores publicados fuerzan el modo sin interfaz gráfica,
la semilla 42 y el retardo mínimo admitido de 0.05 segundos entre eventos.

<h3>Instalación</h3>

```bash
REPO_ROOT="$(pwd)"
python3 -m venv "$REPO_ROOT/.venv-legacy"
"$REPO_ROOT/.venv-legacy/bin/python" -m pip install -r "$REPO_ROOT/requirements.txt"
```

```powershell
$RepoRoot = (Get-Location).Path
python -m venv (Join-Path $RepoRoot ".venv-legacy")
& (Join-Path $RepoRoot ".venv-legacy\Scripts\python.exe") -m pip install -r (Join-Path $RepoRoot "requirements.txt")
```

<h3>Configuración</h3>

No se requiere red ni servicio externo. Para ejecuciones manuales del experimento, use identificadores
seudónimos y un directorio de salida dedicado. Los lanzadores del ejemplo ya usan `SYNTH-P01` y
`SYNTH-S01`.

<h3>Ejecución</h3>

Con el venv seleccionado activo, elija un modo:

```bash
REPO_ROOT="$(pwd)"
PATH="$REPO_ROOT/.venv-legacy/bin:$PATH" bash "$REPO_ROOT/examples/legacy-monitor/run.sh" combined
```

```powershell
$RepoRoot = (Get-Location).Path
$env:PATH = "$(Join-Path $RepoRoot '.venv-legacy\Scripts');$env:PATH"
& (Join-Path $RepoRoot "examples\legacy-monitor\run.ps1") -Mode combined
```

Los modos disponibles son `uav`, `fighter`, `combined` y `experiment`.

<h3>Prueba del ejemplo sintético</h3>

```bash
REPO_ROOT="$(pwd)"
PATH="$REPO_ROOT/.venv-legacy/bin:$PATH" bash "$REPO_ROOT/examples/legacy-monitor/run.sh" experiment "$REPO_ROOT/examples/output/legacy-monitor"
```

```powershell
$RepoRoot = (Get-Location).Path
$env:PATH = "$(Join-Path $RepoRoot '.venv-legacy\Scripts');$env:PATH"
& (Join-Path $RepoRoot "examples\legacy-monitor\run.ps1") -Mode experiment -OutputDir (Join-Path $RepoRoot "examples\output\legacy-monitor")
```

<h3>Resultado esperado</h3>

La terminal finaliza con `Simulation complete!`. El modo experimento escribe eventos JSONL y una
salida de resumen solo en el directorio seleccionado por quien ejecuta el comando. Los demás modos
no reciben un directorio de salida de investigación.

<h3>Verificación</h3>

```bash
REPO_ROOT="$(pwd)"
"$REPO_ROOT/.venv-legacy/bin/python" -m aircraft_monitor --help
"$REPO_ROOT/.venv-legacy/bin/python" -m pytest \
  "$REPO_ROOT/tests/test_dashboard_behavior.py" \
  "$REPO_ROOT/tests/test_research_protocol.py" -q
```

```powershell
$RepoRoot = (Get-Location).Path
$Python = Join-Path $RepoRoot ".venv-legacy\Scripts\python.exe"
& $Python -m aircraft_monitor --help
& $Python -m pytest `
  (Join-Path $RepoRoot "tests\test_dashboard_behavior.py") `
  (Join-Path $RepoRoot "tests\test_research_protocol.py") -q
```

<h3>Detención y limpieza</h3>

Ctrl-C devuelve el control normalmente. Elimine solo el directorio dedicado del experimento:

```bash
REPO_ROOT="$(pwd)"
rm -rf -- "$REPO_ROOT/examples/output/legacy-monitor"
```

```powershell
$RepoRoot = (Get-Location).Path
Remove-Item -Recurse -Force (Join-Path $RepoRoot "examples\output\legacy-monitor") -ErrorAction SilentlyContinue
```

<h3>Solución de problemas</h3>

Si el lanzador resuelve el Python equivocado, active el venv seleccionado o coloque primero su
directorio `bin`/`Scripts` en `PATH`. Use `--headless` en terminales no interactivas. Consulte la
[guía del monitor heredado](examples/legacy-monitor/README.es.md).

<a id="module-catalog"></a>
## 10. Catálogo de módulos

Cada tabla apunta al ejemplo ejecutable más pequeño. Las explicaciones científicas, de endpoints,
liberación y evidencia detalladas se mantienen en sus guías especializadas.

### Módulos de investigación Python/OpenMATB

| Módulo | Propósito | Usuario | Entradas → salidas | Entorno de ejecución | Ejemplo | Verificación | Limitación |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `matb_integration/scenario_builder.py` | Generar escenarios LOW/MEDIUM/HIGH contrabalanceados | Diseñador del estudio | Protocolo, duración, semilla → escenarios de texto OpenMATB | Python | [Recorrido OpenMATB](examples/openmatb-research/README.es.md) | `pytest tests/test_scenario_builder.py tests/test_scenario_manifest.py tests/test_log_converter.py tests/suhir tests/analysis_stats tests/screen -q` | Las tareas generadas requieren OpenMATB externo para su presentación |
| `matb_integration/scenario_manifest.py` | Calcular hashes de escenarios y validar la procedencia de la sesión | Custodio de datos | Escenario/etiquetas/sondeos esperados → manifiesto adyacente y problemas de validación | Python | Recorrido OpenMATB | Mismo conjunto | La integridad del hash no establece la validez del protocolo ni el consentimiento |
| `matb_integration/log_converter.py` | Convertir CSV de OpenMATB en métricas canónicas | Analista de investigación | CSV + seudónimo/carga de trabajo → métricas JSONL | Python | Recorrido OpenMATB | Mismo conjunto | La calidad de la entrada y las tareas ausentes limitan la inferencia |
| `matb_integration/questionnaires/` | Recursos EN/ES de NASA-TLX, Bedford, ISA y SAGAT | Diseñador del estudio | Texto/YAML controlado → contenido configurado de cuestionario/sondeo | OpenMATB externo o cargador sUAS | Recorridos OpenMATB y sUAS | Pruebas de cuestionarios/SAGAT | Las escalas deben administrarse bajo un protocolo aprobado |
| `matb_integration/analysis/` | Resultados descriptivos, motores frecuentistas MixedLM/rmcorr/rmANOVA/FDR y motores bayesianos de sensibilidad PyMC | Estadístico | Arreglos JSON `/metrics/long` y `/fits` → artefactos versionados | Python; el muestreo PyMC es opcional/lento | [Comandos de análisis OpenMATB](examples/openmatb-research/README.es.md) | Pruebas de análisis | Los conjuntos pequeños/incompletos pueden no ser estimables; los diagnósticos bayesianos gobiernan la interpretación |
| `matb_integration/suhir/` | Ajustar parámetros DEPDF de Suhir y resúmenes de investigación de resultados de misión | Investigador de factores humanos | Tres registros de carga de trabajo → G0/P0/tau0 y curvas | Python/SciPy | Recorrido OpenMATB | Pruebas de Suhir; [guía DEPDF](matb_integration/suhir/README.md) | Modelo comparativo intraparticipante; tres niveles identifican exactamente los parámetros; no está certificado |
| `matb_integration/screen/` | Puntuar tareas de reacción/2-back/seguimiento y mapear HCF/F/F0 exploratorio | Investigador | Ensayos sin procesar/cohorte → puntuaciones y mapeo exploratorio | Python mediante backend | Consola de Investigación `/screen` | Pruebas de evaluación/backend | No es un instrumento diagnóstico, de selección ni predictivo validado |

### Consola de Investigación

| Módulo | Propósito | Usuario | Entradas → salidas | Entorno de ejecución | Ejemplo | Verificación | Limitación |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Seguimiento e ingestión de `webui/backend/` | Cuadrícula seudónima de participantes/visitas, comprobaciones CSV/manifiesto y ajustes | Custodio de datos | CSV + manifiesto opcional → filas SQLite de bloque/procedencia | FastAPI, Python 3.12+, puerto 8000 | [Recorrido de la consola](examples/research-console/README.es.md) | `cd webui/backend && python -m pytest -q` | Los controles de duplicados/relleno son controles de calidad de datos, no consentimiento |
| Análisis y exportación de `webui/backend/` | Almacenar en caché resultados frecuentistas/bayesianos y construir paquetes reproducibles | Analista | Métricas/ajustes/figuras almacenados → registros de análisis y ZIP | FastAPI/PyMC en segundo plano | Recorrido de la consola | Pruebas de análisis/exportación del backend | La exportación sigue siendo datos de investigación bajo custodia del propietario |
| Seguimiento, ingestión y visualización de `webui/frontend/` | Cuadrícula del navegador, carga y gráficos descriptivos | Personal de investigación | JSON del backend → UI local interactiva/PNG | Next.js, Node 20+, puerto 3100 | Recorrido de la consola | `npm test`, `npm run typecheck`, `npm run build` | Los gráficos descriptivos no son conclusiones inferenciales |
| Evaluación, análisis y exportación de `webui/frontend/` | Administrar la evaluación inicial, revisar análisis y solicitar el paquete | Personal de investigación | Ensayos sin procesar/artefactos del backend → resúmenes UI/solicitud de exportación | Navegador/Next.js | Recorrido de la consola | La evaluación es exploratoria; el navegador no es un dispositivo clínico |

Los contratos de endpoints y evaluación se mantienen en la [guía del backend](webui/backend/README.md)
y la [guía del frontend](webui/frontend/README.md).

### Simulador sUAS sintético

| Módulo | Propósito | Usuario | Entradas → salidas | Entorno de ejecución | Ejemplo | Verificación | Limitación |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `matb_integration/suas/scenarios/` | Validar esquemas YAML, manifiestos y perfiles de carga de trabajo | Autor de escenarios | YAML sintético → definición inmutable del escenario | Python 3.12+ | [Recorrido de la CLI sUAS](examples/suas-simulator/README.es.md) | `python -m matb_integration.suas.cli validate ...` | Solo coordenadas y condiciones sintéticas |
| `matb_integration/suas/engine/` | Lógica determinista de reloj, ruta, energía, enlace, sensor, separación y reductor | Desarrollador del simulador | Escenario + mandos de supervisión → estado del mundo/eventos | Python, no se requiere servicio | Recorrido de la CLI sUAS | `pytest tests/suas -q` | Sin adaptador para vehículos reales ni despacho autónomo |
| Sesión/ciclo de vida de `matb_integration/suas/` | Preparar, iniciar, pausar, reanudar, finalizar, interrumpir y recuperar sesiones de forma explícita | Operador de investigación | Seudónimo + visita + escenario → ciclo de vida auditado | Python/FastAPI | Recorrido de la API sUAS | Pruebas de backend y sUAS | La recuperación se marca como desviación; una interrupción nunca reanuda automáticamente |
| Arrendamiento de controlador en `webui/backend/app/routers/simulation.py` | Imponer un único controlador de mutación | Operador | Encabezado de arrendamiento de un solo uso → mutación autorizada del ciclo de vida | FastAPI loopback | Recorrido de la API sUAS | El arrendamiento es sensible; nunca lo registre ni lo coloque en una URL |
| Flujo de observador de `webui/backend/app/websocket/simulation.py` | Resincronización ordenada y estado de observador redactado, sin arrendamiento | Observador/investigador | Cursor de secuencia → instantánea/envolventes | WebSocket | Recorrido del navegador | El observador no puede mutar; la verdad oculta y los sondeos permanecen privados |
| Reproducción de `matb_integration/suas/recording/` | Anexar eventos/puntos de control y reproducirlos de forma determinista | Auditor/investigador | Eventos + manifiesto → verificación de reproducción | CLI Python | Recorrido de la CLI sUAS | La verificación demuestra coherencia interna, no validez en el mundo real |
| Informe final de `matb_integration/suas/metrics/` | Calcular métricas terminales de investigación e informe final | Investigador | Estado/eventos terminales sellados → JSON de métricas/informe final | Python | Recorrido de la CLI sUAS | El informe final es un artefacto de investigación, no un juicio operacional |
| `matb_integration/suas/recording/artifacts.py` | Sellar manifiesto, sumas de comprobación, metadatos públicos y artefactos privados | Custodio de datos | Registros de sesión → conjunto de artefactos con hashes de rutas relativas | Python/sistema de archivos local | Recorrido de la CLI sUAS | Mantenga la raíz de artefactos exclusiva del propietario; los hashes no desidentifican el contenido |

### Aplicaciones del SMS FAC ISR

| Módulo | Propósito | Usuario | Entradas → salidas | Entorno de ejecución | Ejemplo | Verificación | Limitación |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SMS/apps/edge-api/` | Ingesta local de paquetes Fastify, compuertas, misiones, posvuelo, auditoría, modo seguro y límites de datos | Revisor de seguridad operacional/custodio de despliegue | Paquetes locales verificados + telemetría de solo lectura → resultados SQLite/auditoría/API | Node 22.x; contenedor Linux reforzado para despliegue sin conexión | [Recorrido del SMS](examples/sms-platform/README.es.md) | Pruebas del espacio de trabajo y `/healthz` | Entorno sin C2 y sin Internet; sin autoridad de despacho |
| `SMS/apps/console/` | Consola React accesible para evidencia, riesgo, telemetría, listas de verificación y límites de investigación | Revisor humano | Resultados de la API edge → vistas de revisión | Node/Vite; puertos 5173 de desarrollo o 4173 de vista previa controlada | Guía del SMS | Pruebas unitarias, de accesibilidad y E2E de Playwright | Mostrar un resultado aprobado no registra aceptación humana |

### Paquetes del SMS FAC ISR

| Módulo | Propósito | Usuario | Entradas → salidas | Entorno de ejecución | Ejemplo | Verificación | Limitación |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SMS/packages/evidence/` | JSON canónico, SHA-256, registros de fuente, afirmaciones, manifiestos y rechazo de retrocesos | Custodio de evidencia | Fuentes locales controladas → afirmaciones/manifiestos verificables | Node 22.x | Recorrido de paquetes del SMS | Pruebas del espacio de trabajo | Confianza, autoridad, alcance y vigencia siguen siendo controles externos |
| `SMS/packages/energy/` | Evaluación con unidades de energía de misión y reservas | Analista de rendimiento | Datos de aeronave/segmento respaldados por evidencia → resultado determinista de energía | Node 22.x | Recorrido de paquetes del SMS | Pruebas de espacio de trabajo/propiedades | El resultado del componente no es una autorización |
| `SMS/packages/fleet/` | Datos de configuración, capacidad, liberación de mantenimiento y calificación de tripulación | Revisor de flota | Evidencia aceptada + estado de flota → evaluación de capacidad | Node 22.x | Recorrido de paquetes del SMS | Pruebas del espacio de trabajo | La falta de evidencia de calificación/liberación produce un bloqueo seguro |
| `SMS/packages/geo/` | Coordenadas, rutas, terreno, visibilidad, meteorología, espacio aéreo, paquetes sin conexión y borradores de plan de vuelo | Revisor geográfico | Paquete geográfico controlado → datos/borrador geográfico determinista | Node 22.x | Recorrido de paquetes del SMS | Pruebas del espacio de trabajo | Sin transmisor ni autoridad geoespacial oficial |
| `SMS/packages/human-performance/` | Límites de servicio, calificación, fatiga, carga de trabajo, carga de alertas y CRM | Revisor de factores humanos | Política + estado explícitos → evaluación acotada | Node 22.x | Recorrido de paquetes del SMS | Pruebas de privacidad/contratos | No es un diagnóstico médico ni una decisión de aptitud |
| `SMS/packages/research/` | Protocolo, ética/consentimiento, instrumentos, MATB/sensores, reproducción, agregación y exportación desidentificada | Custodio de investigación | Eventos seudónimos consentidos → exportación de investigación nonDispatchable | Node 22.x | Recorrido de paquetes del SMS | Pruebas de límites/exportación | Separación estricta de la liberación operacional |
| `SMS/packages/safety-kernel/` | Aplicabilidad, vigencia, dependencias, riesgo, ciclo de vida, compuertas y auditoría deterministas | Revisor responsable | Datos respaldados por evidencia → decisiones pass/blocked/unknown | Node 22.x | Recorrido de paquetes del SMS | Pruebas doradas/de propiedades/integración | La evidencia dura desconocida produce un bloqueo seguro; nunca concede aceptación |
| `SMS/packages/sms/` | Peligros, SPI, auditorías, CAPA, ERP y gestión del cambio | Organización de seguridad operacional | Registros organizacionales → evaluaciones SMS controladas | Node 22.x | Recorrido de paquetes del SMS | Pruebas del espacio de trabajo | La evidencia responsable incompleta permanece bloqueada |
| `SMS/packages/telemetry/` | Canonizar y reproducir telemetría retardada/con pérdidas con procedencia de retención | Observador/analista | Eventos de solo lectura → flujo canónico/reproducido | Node 22.x | Recorrido de paquetes del SMS | Pruebas de contrato/reproducción | Deliberadamente no tiene ruta de mando |

### Herramientas, liberación y aceptación del SMS FAC ISR

| Módulo/flujo | Propósito | Usuario | Entradas → salidas | Entorno de ejecución | Ejemplo | Verificación | Limitación |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SMS/tools/map-packager/` | Inspeccionar/construir manifiestos y controlar firma/verificación de paquetes geográficos sin conexión | Custodio geográfico/de liberación | Directorio + metadatos + entrada controlada de firma/verificación → manifiesto del paquete | Node 22.x | Inventario CLI de la guía del SMS | Pruebas de herramienta y `verify` | La firma requiere material y autoridad controlados externamente |
| `SMS/tools/research/` | Registrar consultas de adquisición, adquirir/copiar/extraer fuentes y verificar hashes/sin conexión/sin C2 | Investigador de evidencia | Artefactos de fuente registrados → registros de procedencia/consulta | Node 22.x | Inventario CLI de la guía del SMS | Pruebas de herramienta; `verify:evidence-offline` | Los resultados de búsqueda no son evidencia hasta que se adquieren y verifican |
| `build:offline` / `verify:offline` | Compilar/probar la imagen Linux y ensamblar/verificar un paquete de transferencia desconectado | Custodio de despliegue | Dependencias bloqueadas, imagen fijada, evidencia local → archivo OCI/paquete | Contenedores Linux/Docker | [Guía sin conexión del SMS](examples/sms-platform/README.es.md) | `npm run verify:offline` | Las entradas de compilación deben prepararse; sin conexión describe el límite de ejecución/transferencia |
| `release:manifest` / `release:sign` / `release:verify` | Generar SBOM, informe de escaneo/prueba, manifiesto canónico, firma controlada y resultado de integridad | Custodio de liberación | Artefactos versionados + entrada de firma externa → evidencia de liberación | Node 22.x | Guía del SMS | `npm run release:verify` | Firma/integridad no es aceptación operacional |
| `verify:no-c2` / `verify:data-separation` | Inspeccionar la ausencia de rutas de mando y la separación investigación/operaciones | Revisor de seguridad de la información/investigación | Código compilado/espacios de trabajo → resultado de verificación | Node 22.x | Guía del SMS | Scripts npm nombrados | El alcance es el software del repositorio, no cada control de despliegue |
| `verify:matrix` / `verify:acceptance` | Ejecutar la matriz de evidencia y validar el estado de aceptación controlado | Revisor independiente | Registros de liberación/evidencia + UTC exacto → informe/estado de preparación | Node 22.x | Guía del SMS | Scripts npm nombrados | La matriz puede pasar mientras la preparación permanece false |
| `acceptance:packets` | Generar paquetes deterministas sin firmar para revisores | Coordinador de revisión | Directorio de salida vacío + UTC `--as-of` exacto + alcance aprobado opcional → paquetes | Node 22.x | Guía del SMS | `npm run verify:acceptance` | Los paquetes no son decisiones y permanecen sin firmar |
| `acceptance:record` | Ingerir una decisión institucional controlada suministrada por un humano | Custodio autorizado de registros | Paquete vigente + decisión autorizada real → registro controlado | Node 22.x; acción separada explícita | Sin ejemplo de decisión sintética | Ejecución de prueba y después proceso institucional | Nunca fabrique revisor, resultado, marca de tiempo, evidencia ni firma |

El inventario de compilación y verificación del SMS invocado por el usuario desde `SMS/package.json`
se muestra a continuación. Los comandos parametrizados de liberación y paquetes aún requieren los
argumentos y la custodia descritos en la [guía del SMS](examples/sms-platform/README.es.md).

```bash
cd SMS
npm run build
npm run build:packages
npm run build:tools
npm run build:apps
npm run build:research
npm test
npm run typecheck
npm run lint
npm run build:offline
npm run verify:offline
npm run verify:evidence-offline
npm run verify:no-c2
npm run verify:data-separation
npm run release:manifest
npm run release:sign
npm run release:verify
npm run verify:matrix
npm run acceptance:packets
npm run verify:acceptance
npm run verify:all
```

Los scripts de manifiesto restantes son hooks automáticos del ciclo de vida npm: `pretest` compila antes
de `test`; `preverify:evidence-offline` compila la herramienta de investigación; `preverify:no-c2`
compila la API edge; y `preverify:data-separation` compila el paquete de investigación y la API edge.
El script `acceptance:record` (invocado solo como `npm run acceptance:record` por un custodio autorizado)
forma parte del inventario, no es una instrucción rutinaria: es una acción independiente y potencialmente
modificadora que ingiere decisiones y requiere un paquete vigente y entrada humana genuina controlada
por la institución. No lo invoque solo porque está documentado.

### Monitor de aeronaves heredado

| Módulo/modo | Propósito | Usuario | Entradas → salidas | Entorno de ejecución | Ejemplo | Verificación | Limitación |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `aircraft_monitor/` `uav` | Demostración determinista de UAV en terminal | Desarrollador/educador | Modelo con semilla → flujo de eventos en terminal | Python/Rich | [Guía heredada](examples/legacy-monitor/README.es.md) | Pruebas Python | Demostración sintética heredada, no monitoreo en vivo |
| `aircraft_monitor/` `fighter` | Demostración determinista de caza en terminal | Desarrollador/educador | Modelo con semilla → flujo de eventos en terminal | Python/Rich | Guía heredada | Pruebas Python | Contiene vocabulario de combate simulado, pero no ruta de armas/control |
| `aircraft_monitor/` `combined` | Demostración conjunta en terminal | Desarrollador/educador | Ambos modelos con semilla → flujo combinado | Python/Rich | Guía heredada | Pruebas Python | No es la superficie activa de recopilación de investigación |
| `aircraft_monitor/` `experiment` | Protocolo de factores humanos inspirado en MATB | Desarrollador de investigación | Seudónimo, sesión, modalidad, semilla → JSONL/resumen | Python/Rich | Guía heredada | Pruebas de investigación | Use seudónimos sintéticos o aprobados; no es OpenMATB |

<a id="operations-and-maintenance"></a>
## 11. Operaciones y mantenimiento

### Conjuntos de verificación

Ejecute solo los conjuntos correspondientes al flujo que modificó y después la compuerta de documentación:

```bash
python -m pytest tests/test_scenario_builder.py tests/test_scenario_manifest.py \
  tests/test_log_converter.py tests/analysis_stats tests/suhir tests/screen -q
python -m pytest tests/suas -q
cd webui/backend && python -m pytest -q
cd ../../webui/frontend && npm test && npm run typecheck && npm run build
cd ../../SMS && npm test && npm run typecheck && npm run lint
cd .. && python -m pytest tests/documentation/test_documentation.py -q
python scripts/verify_documentation.py
```

Los conjuntos E2E/accesibilidad del navegador también requieren recursos instalados de
Chromium/Playwright. La compilación sin conexión del SMS también requiere Docker, la imagen base
fijada, las dependencias bloqueadas y las entradas controladas por la institución.

### Puertos y límites de procesos

| Servicio | Valor predeterminado | Límite |
| --- | --- | --- |
| FastAPI de investigación/sUAS | `127.0.0.1:8000` | Loopback; salud en `/health` |
| Next.js de investigación/sUAS | `127.0.0.1:3100` | Loopback; seguimiento `/`, sUAS `/mission/setup` |
| Despliegue edge del SMS | Valor predeterminado del host `127.0.0.1:8443` | HTTPS en un despliegue controlado de contenedor |
| Consola Vite del SMS | 5173 desarrollo / 4173 vista previa controlada | Solo UI de desarrollo/revisión |

Mantenga los valores loopback predeterminados. Un enlace de investigación/sUAS que no sea loopback
requiere `MATB_FRONTEND_ORIGINS` explícito; también requiere controles institucionales de red,
autenticación, privacidad y amenazas que exceden este lanzador de desarrollo.

### Configuración

| Variable | Alcance | Significado |
| --- | --- | --- |
| `MATB_PYTHON` | Envoltorios de ejemplos | Ejecutable Python exacto seleccionado para recorridos de CLI OpenMATB o sUAS |
| `MATB_VENV` | Instalación/lanzador POSIX | Ruta del entorno Python local del repositorio |
| `MATB_DB_PATH` | Backend de investigación/sUAS | Ruta SQLite dedicada |
| `MATB_SIMULATION_OUTPUT_DIR` | sUAS | Raíz de artefactos sellados exclusiva del propietario |
| `MATB_SIMULATION_SCENARIO_DIR` | sUAS | Directorio de escenarios YAML validados |
| `MATB_FRONTEND_ORIGINS` | Investigación/sUAS | Orígenes de navegador permitidos explícitamente |
| `NEXT_PUBLIC_API_URL` | Frontend de investigación | URL base de FastAPI visible para el navegador |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE` | Pruebas de navegador | Ejecutable Chromium aprobado |
| `SMS_DATA_DIR`, `SMS_PACKAGE_DIR`, `SMS_TLS_DIR` | Contenedor del SMS | Raíces controladas para datos modificables, paquetes de solo lectura y custodia TLS |
| `SMS_EDGE_PORT` | Contenedor del SMS | Sustitución del puerto loopback del host |
| `SMS_EVIDENCE_VERIFY_AS_OF` | Verificación de evidencia del SMS | Instante UTC autorizado exacto de verificación |
| `SMS_RESEARCH_DATABASE_URL`, `SMS_RESEARCH_DATA_DIR` | Separación del SMS | Ubicaciones separadas del almacén de investigación |

Los identificadores y entradas de firma/TLS/claves son asuntos del custodio de liberación. Nunca
coloque sus valores en el código fuente, ejemplos, historial de shell, registros ni tiquetes de soporte.

### Datos generados y limpieza restringida

Las rutas generadas esperadas incluyen directorios `examples/output/...` seleccionados, venvs de
Python, bases de datos SQLite, registros/artefactos sUAS, ZIP de paquetes de investigación,
`webui/frontend/.next/`, `node_modules/` de Node, árboles `dist/` de TypeScript y salidas sin conexión/
de liberación del SMS. Antes de eliminar algo, detenga los procesos de escritura, resuelva la ruta
exacta, confirme que sea una ruta dedicada de ejemplo/compilación y conserve los registros de estudio,
evidencia controlada, liberación o aceptación conforme a la política.

Capaz de funcionar sin conexión significa que el entorno instalado puede operar sin Internet. No
significa que la primera instalación de dependencias, una compilación Docker sin una imagen base
preparada o una verificación sin evidencia registrada puedan tener éxito sin conexión.

<a id="troubleshooting"></a>
## 12. Solución de problemas por síntoma

| Síntoma | Comprobación y respuesta segura |
| --- | --- |
| El instalador rechaza Python o Node | Use Python 3.12+ para sUAS/Python del repositorio, Node 20+ para el lanzador de la Consola de Investigación y Node 22.x para `SMS/`; vuelva a crear solo el venv/instalación de ese flujo. |
| Falta un módulo Python | Confirme que se ejecute el Python del venv seleccionado (`python -c "import sys; print(sys.executable)"`) e instale los requisitos correspondientes; no instale globalmente para ocultarlo. |
| No se encuentra OpenMATB externo | No se incluye en el repositorio. Apunte `install_to_openmatb.py` a un checkout independiente que contenga `includes/`. |
| OpenMATB parpadea o Pyglet/la pantalla falla | Este es el límite de escritorio/X11 externo. Comience en modo de ventana, valide Pyglet en su venv y, en Linux sin interfaz gráfica, valide Xvfb y `DISPLAY`. sUAS no necesita X11 ni Pyglet. |
| Se bloquea un script de PowerShell o falla una ruta con espacios | Use PowerShell 7+, invoque scripts con `&`, construya rutas con `Join-Path` y use una política de ejecución aprobada por la institución; no desactive globalmente los controles de seguridad de la información. |
| WSL2 no alcanza un servicio o cambia los permisos | Ejecute los lanzadores POSIX y las raíces de datos en el sistema de archivos WSL, confirme que el servicio se enlace a loopback/al puerto elegido y verifique el comportamiento loopback de Windows a WSL. No reemplace los controles `chmod`/UID con permisos amplios. |
| El puerto 8000 o 3100 está ocupado | Detenga el proceso conocido o indique valores únicos de `--backend-port`/`--frontend-port`; actualice de forma coherente `NEXT_PUBLIC_API_URL` y los orígenes permitidos. |
| La prueba de navegador/E2E no encuentra Chromium | Instale el recurso de navegador Playwright compatible con el repositorio o configure `PLAYWRIGHT_CHROMIUM_EXECUTABLE` con un binario local aprobado. Las pruebas unitarias/API/CLI no lo requieren. |
| Docker no está disponible | Use el recorrido de paquetes Node y los conjuntos sin contenedor, o proporcione un entorno aprobado de contenedores Linux. No llame paquete sin conexión a un directorio no compilado/no verificado. |
| La evidencia venció, falta o informa alteración/discrepancia de hash | Detenga el flujo, conserve el diagnóstico y obtenga evidencia autorizada vigente mediante los procedimientos de custodia. Nunca debilite comprobaciones de vigencia, firma, autoridad de fuente o hash. |
| Las pruebas pasan, pero la preparación permanece bloqueada | Es lo esperado: la automatización verifica contratos técnicos; `operationalReady=false` permanece hasta que toda revisión institucional dentro del alcance esté vigente y se registre una decisión humana autorizada. |

<a id="security-privacy-and-governance"></a>
## 13. Seguridad de la información, privacidad, investigación y gobernanza

- Sin C2 y no cinético son límites arquitectónicos: la telemetría es de solo lectura, las simulaciones
  son sintéticas y ningún paquete puede convertirse en una ruta de mando de aeronave/arma, selección
  de blancos, vuelo autónomo o despacho.
- Use identificadores seudónimos de participante/sesión. Almacene las claves de vinculación, el
  consentimiento, la información de salud, la identidad sin procesar y las exportaciones solo en
  ubicaciones controladas por la institución, con reglas de mínimo privilegio, retención y eliminación.
- NASA-TLX, Bedford, ISA, SAGAT, los mapeos de evaluación, los modelos estadísticos y los resultados
  DEPDF son instrumentos de investigación. No son hallazgos clínicos, decisiones de aptitud individual,
  hallazgos de aeronavegabilidad ni autorizaciones operacionales.
- La evidencia controlada debe conservar autoridad de fuente, alcance exacto, procedencia, datos
  SHA-256/integridad, versión y vigencia. La verificación dependiente del tiempo usa un instante UTC
  exacto explícito; nunca sustituya una hora local ambigua.
- Las firmas de liberación, SBOM, manifiestos, comprobaciones sin C2/de separación de datos, pruebas
  técnicas y matrices son evidencia necesaria, no aceptación. Una institución humana cualificada debe
  revisar los alcances aplicables de reglamentación/traducción, riesgo operacional, respuesta a
  emergencias, ciberseguridad/despliegue, datos geográficos oficiales, factores humanos, separación de
  investigación, capacitación y promoción de la seguridad operacional.
- Genere sin firmar los paquetes para revisores. Ejecute la ingesta de decisiones solo con un paquete
  vigente y una decisión humana auténtica, autorizada y controlada. Nunca fabrique identidades,
  aprobaciones, marcas de tiempo, evidencia, resultados ni firmas.

Para información avanzada, consulte la [revisión de evidencia de investigación](docs/research/military-aviation-platform/research_evidence_review.md),
la [validación de escalas](docs/research/scales/sagat_validation.md),
la [verificación de sUAS](docs/implementation/suas-c2-v1-verification.md),
la [matriz de verificación del SMS](SMS/docs/release/verification-matrix.md),
las [limitaciones conocidas](SMS/docs/release/known-limitations.md) y la
[lista de verificación de aceptación de aviación estatal](SMS/docs/release/state-aviation-acceptance-checklist.md).

<a id="repository-map"></a>
## 14. Mapa del repositorio

| Ruta | Función mantenida |
| --- | --- |
| `matb_integration/` | Puente del protocolo de investigación, métricas, estadísticas, DEPDF, evaluación y bibliotecas sUAS deterministas |
| `scenarios/military_aviation/` | Escenarios de estudio compatibles con OpenMATB |
| `scenarios/suas/` | Escenarios YAML sUAS sintéticos |
| `webui/backend/` | Servicio FastAPI de investigación/sUAS, persistencia, análisis y exportaciones |
| `webui/frontend/` | Seguimiento/análisis de investigación y consola sUAS del navegador |
| `SMS/apps/`, `SMS/packages/`, `SMS/tools/` | Aplicaciones SMS sin conexión, contratos y herramientas de liberación/evidencia |
| `SMS/docs/` | Procedencia controlada, investigación reglamentaria, evidencia de liberación y orientación de aceptación |
| `aircraft_monitor/` | Demostración sintética de terminal conservada |
| `examples/` | Recorridos seguros, deterministas y seudónimos |
| `tests/` | Comprobaciones de integración Python, simulador, aplicación y documentación |
| `docs/` | Revisiones científicas y registros de diseño/implementación |

<a id="glossary"></a>
## 15. Glosario

| Término | Significado aquí |
| --- | --- |
| C2 | Mando y control; ausente deliberadamente de los límites operacionales de MATB |
| DEPDF | Función de distribución de probabilidad doble exponencial usada para modelado comparativo de no fallo humano |
| HCF / F/F0 | Mapeo exploratorio del factor de capacidad humana a partir de la evaluación de investigación |
| Manifiesto | Metadatos canónicos y hashes que vinculan el contenido con la procedencia |
| MATB | Paradigma Multi-Attribute Task Battery de factores humanos |
| nonDispatchable | Datos/resultados de investigación que no pueden ingresar en una decisión de liberación operacional |
| OpenMATB | Entorno externo de presentación de tareas; no forma parte de este repositorio |
| Preparación operacional | Estado controlado por la institución que la automatización por sí sola no puede conceder |
| Seudónimo | Identificador del estudio que omite la identidad directa; sigue siendo un dato de investigación potencialmente vinculable |
| SMS | Safety Management System; aquí, el espacio de aseguramiento `SMS/` |
| sUAS | Sistema de aeronaves pequeñas no tripuladas; aquí, un simulador sintético de investigación supervisora |

<a id="references"></a>
## 16. Referencias y guías detalladas

- [Ejemplos y selector de flujos](examples/README.es.md)
- [Descripción general de la Consola de Investigación](webui/README.md), [API del backend](webui/backend/README.md) y [pantallas del frontend](webui/frontend/README.md)
- [Guía DEPDF de Suhir](matb_integration/suhir/README.md)
- [Revisión de evidencia de investigación](docs/research/military-aviation-platform/research_evidence_review.md) y [validación de escalas](docs/research/scales/sagat_validation.md)
- [Diseño de sUAS sintético](docs/superpowers/specs/2026-08-01-suas-c2-research-simulator-design.md) y [verificación](docs/implementation/suas-c2-v1-verification.md)
- [Registro de evidencia de capacidades del SMS](SMS/docs/provenance/capability-evidence-register.jsonl), [matriz de verificación](SMS/docs/release/verification-matrix.md) y [limitaciones conocidas](SMS/docs/release/known-limitations.md)

<a id="contributing"></a>
## 17. Contribuciones

Mantenga los cambios limitados a un flujo, preserve los límites de Linux/Windows nativo/WSL2 y añada
pruebas antes de cambiar el comportamiento. Los ejemplos deben ser deterministas, sintéticos,
seudónimos, seguros sin conexión después de instalar las dependencias y estar restringidos a directorios
de salida elegidos por quien ejecuta el comando. Nunca confirme en el repositorio datos de estudio
generados, credenciales, claves privadas, arrendamientos del controlador, firmas controladas ni
decisiones de aceptación fabricadas.

Antes de enviar cambios de documentación, ejecute:

```bash
python -m pytest tests/documentation/test_documentation.py -q
python scripts/verify_documentation.py
```

Después ejecute los conjuntos pertinentes de Python, frontend o SMS enumerados anteriormente. Explique
cualquier entorno externo, recurso de navegador, entrada Docker o evidencia controlada que no esté
disponible intencionalmente; no debilite una comprobación para que pase.

<a id="license"></a>
## 18. Licencia

MATB se proporciona bajo la [Licencia MIT](LICENSE). La licencia no certifica su aptitud para uso
clínico, de vuelo, defensa, crítico para la seguridad operacional ni operacional, y no sustituye la
legislación aplicable, la gobernanza institucional, la revisión ética ni la aceptación humana.
