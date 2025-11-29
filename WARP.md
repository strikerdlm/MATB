# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview
OpenMATB is a Python-based Multi-Attribute Task Battery for aviation research (Python 3.9+). It includes fighter aircraft and UAV operator modules, physiological monitoring (HRV via Polar H10), and combat scenarios.

- **Primary Documentation**: `Docs/Manual.md` (consult before new features).
- **Framework**: `pyglet` for UI/Graphics.

## Development Workflow

### Installation
```bash
python -m pip install -r requirements.txt
```
*Note: Uses `pylsl`, `pyglet`, `bleak`, `neurokit2`.*

### Running the Application
```bash
python main.py
```
*Configuration is loaded from `config.ini`.*

### Testing
Run all tests:
```bash
pytest tests/
```
*Uses `hypothesis` for property-based testing.*

### Quality Checks (Mandatory)
Ensure zero warnings before committing:
```bash
ruff check .
black --check .
isort --check .
mypy --strict .
bandit -r plugins/ core/
```

## Architecture

### Core Components (`core/`)
- **`scenario.py`**: Scenario engine and parsing.
- **`logger.py`**: Centralized logging system.
- **`scheduler.py`**: Task scheduling.
- **`performance_summary.py`**: Post-run KPI generation.

### Plugins (`plugins/`)
All features are implemented as plugins inheriting from `plugins.abstractplugin.AbstractPlugin`.
- **Structure**: `do_on_command(command, value)` handles scenario events.
- **UI**: `create_widgets()` creates Qt/Pyglet widgets.
- **Logging**: Must use `self.log_performance("metric", key=val)`.

### Data Flow
1.  **Input**: Scenario files (`includes/scenarios/*.txt`) define events.
2.  **Processing**: `main.py` -> `core/` -> `plugins/`.
3.  **Output**: `sessions/user_<id>/<date>/...` containing:
    -   `performance_log.csv` (Raw events)
    -   `summary.json` (Aggregated KPIs)
    -   `hrv/` (Physiological data)

## Coding Standards

### Python Guidelines
-   **Type Hints**: Mandatory for all functions.
-   **Docstrings**: Google-style required.
-   **Function Size**: Max ~60 lines, Cyclomatic complexity ≤10.
-   **Control Flow**: No recursion. Bounded loops only.
-   **Immutability**: Prefer `tuple`, `frozenset`, `dataclasses(frozen=True)`.
-   **Concurrency**: Single model per component. No shared mutables. Use `asyncio.wait_for` for timeouts.

### Error Handling
-   **Validation**: Explicit checks raising specific exceptions (e.g., `ValueError`).
-   **Exceptions**: Never use bare `except:`. Use `raise ... from e`.
-   **Safety**: Fail closed on unexpected states.

### Security
-   **Deserialization**: No `pickle`. Use JSON with schema validation.
-   **Secrets**: No secrets in code. Use `.env`.

## Key Files

| Purpose | File |
| :--- | :--- |
| Project Roadmap | `Docs/Manual.md` |
| Plugin Base | `plugins/abstractplugin.py` |
| Scenario Engine | `core/scenario.py` |
| Logging System | `core/logger.py` |
| HRV Monitor | `plugins/physiomonitor.py` |
| Polar H10 Link | `plugins/polarrlink.py` |
| Automation Hooks | `plugins/automationhooks.py` |
