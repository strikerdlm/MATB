# Inicio Rápido — MATB en Windows

Guía de arranque en Windows (PowerShell 7) para los dos flujos más usados:
la **tarea MATB-FAC (OpenMATB)** y la **Consola de Investigación**.
Los comandos se ejecutan desde la raíz del repositorio `E:\Downloads\MATB`.

Requisitos generales: Git, Python 3.12 o posterior, PowerShell 7,
Node.js 20 o posterior y npm. En el README (`README.md`, secciones 5 y 6)
está la documentación completa de cada flujo.

---

## 1. Tarea MATB-FAC (OpenMATB)

### Primera instalación (solo una vez)

```powershell
$RepoRoot = (Get-Location).Path
python -m venv (Join-Path $RepoRoot ".venv-openmatb")
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") -m pip install -r (Join-Path $RepoRoot "requirements-dev.txt")
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") -m pip install -r (Join-Path $RepoRoot "openmatb\requirements.txt")
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") (Join-Path $RepoRoot "install_to_openmatb.py") (Join-Path $RepoRoot "openmatb")
```

### Arranque de la tarea (cada vez)

```powershell
$RepoRoot = (Get-Location).Path
Set-Location (Join-Path $RepoRoot "openmatb")
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") main.py
```

Con esto se abre la ventana de la tarea. En Windows nativo el runtime de
escritorio corre directamente (no se necesita Xvfb ni WSL2).

### Configuración de idioma y tema

El runtime ya viene en español colombiano (`es_CO`) con el tema claro
MATB-FAC (`fac_modern`) por defecto. Se confirma en `openmatb\config.ini`:

```ini
[Openmatb]
language=es_CO
visual_theme=fac_modern
```

Para un lanzamiento puntual con otro tema: `main.py --visual-theme cockpit`.
Para sesiones controladas, use un perfil estricto **publicado** desde
**Settings -> Appearance** (`/openmatb/appearance`); solo un perfil publicado
puede seleccionarse en una sesión controlada y su identidad (ID, versión,
SHA-256 y JSON resuelto) queda congelada en los artefactos de sesión.

### Notas

- La generación sintética no necesita configuración.
- `install_to_openmatb.py` instala los escenarios y cuestionarios del
  repositorio en el runtime rastreado en `openmatb/`.
- El controlador RC opcional (Hitec Aurora 9 + InterLink) se acepta como un
  único dispositivo de juego de Windows; calibre hardware, cable, puerto USB,
  compilación de Windows y mapeo antes de recolectar datos.

---

## 2. Consola de Investigación (Research Console)

### Primera instalación

```powershell
$RepoRoot = (Get-Location).Path
python -m venv (Join-Path $RepoRoot ".venv-console")
& (Join-Path $RepoRoot ".venv-console\Scripts\python.exe") -m pip install -r (Join-Path $RepoRoot "requirements-dev.txt")
Set-Location (Join-Path $RepoRoot "webui\frontend")
npm ci
Set-Location $RepoRoot
```

Si aparece `No module named sqlmodel`, `pytest` o `pip`, el entorno de la
consola no terminó de instalarse o se está usando otro Python. Repárelo desde
la raíz del repositorio con el mismo ejecutable que usa el backend:

```powershell
& .\.venv-console\Scripts\python.exe -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) { throw "No se pudo preparar pip" }
& .\.venv-console\Scripts\python.exe -m pip install -r .\requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "La instalación de dependencias no terminó" }
& .\.venv-console\Scripts\python.exe -m pip check
if ($LASTEXITCODE -ne 0) { throw "Hay dependencias incompatibles" }
```

No basta con instalar el paquete en el Python global: los comandos de
arranque y de prueba deben utilizar `.venv-console\Scripts\python.exe`.

Para exportaciones descriptivas y restauración sin conexión, prepare también
las ruedas de las versiones instaladas (repita este paso si actualiza las
dependencias). La ejecución del análisis no descarga paquetes:

```powershell
& .\.venv-console\Scripts\python.exe .\tools\prepare_study_wheels.py .\.test-tmp\repeatable-study\descriptive-wheels
if ($LASTEXITCODE -ne 0) { throw "No se pudo preparar el kit de reproducción sin conexión" }
```

### Configuración del entorno

En la terminal desde la que se lanzará el backend:

```powershell
$RepoRoot = (Get-Location).Path
$DataRoot = Join-Path $RepoRoot "examples\output\research-console-service"
New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
$env:MATB_DB_PATH = Join-Path $DataRoot "matb.db"
$env:MATB_FRONTEND_ORIGINS = "http://127.0.0.1:3100"
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
```

### Arranque: dos terminales

**Terminal 1 — backend (Uvicorn):**

```powershell
Set-Location "E:\Downloads\MATB\webui\backend"
& "E:\Downloads\MATB\.venv-console\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — frontend (Next.js):**

```powershell
Set-Location "E:\Downloads\MATB\webui\frontend"
npm run dev -- --hostname 127.0.0.1 --port 3100
```

Luego abra `http://127.0.0.1:3100/`.

### Elección de workspace

- **Participant** (`/start`): catálogo de experimentos.
- **Researcher** (`/tracker`): tracker de completitud.

La elección de workspace se recuerda en la pestaña del navegador actual.
Antes de preparar una sesión, declare explícitamente `practice` o `study`;
la elección de workspace **no** selecciona el propósito del estudio.

### Regla de un solo worker

Corra exactamente **un** worker de Uvicorn por base de datos de la Consola
de Investigación. El backend mantiene un lease exclusivo por instancia de
base de datos y rechaza un segundo proceso vivo.

---

## Atajos alternativos de Windows (consola sUAS)

La carpeta [`windows-launchers/`](windows-launchers/README.es.md) incluye
accesos `.cmd` que instalan dependencias faltantes, compilan, inician los
servicios locales y abren la guía en `http://127.0.0.1:3100/start`:

- `01 - Abrir consola UAS.cmd` — primer uso: prepara e inicia todo.
- `02 - Diagnosticar MATB UAS.cmd` — diagnóstico sin modificar datos.
- `99 - Detener MATB UAS.cmd` — detener los procesos registrados.

---

## Referencias

- [README.md](README.md) — guías completas (secciones 5, 6, 7 y 8).
- [openmatb/README.es.md](openmatb/README.es.md) — guía completa de OpenMATB en español.
- [windows-launchers/README.es.md](windows-launchers/README.es.md) — lanzadores de Windows para la consola sUAS.
