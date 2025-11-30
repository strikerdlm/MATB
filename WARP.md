# WARP.md

This file provides guidance to WARP (warp.dev) AI agent when working with code in this repository.

## Project Overview
OpenMATB is a Python-based Multi-Attribute Task Battery (MATB) for aviation research requiring Python 3.9+. The system simulates complex multi-tasking scenarios for fighter aircraft operators and UAV pilots, with integrated physiological monitoring capabilities.

**Key Features:**
- Fighter aircraft and UAV operator task modules
- Real-time physiological monitoring (HRV via Polar H10 BLE sensor)
- Combat scenario simulation and task automation
- Comprehensive performance logging and analysis

**Documentation Structure:**
- **Primary**: `Docs/Manual.md` (MUST consult before implementing new features)
- **Updates**: `README.md` (project overview) and `CHANGELOG.md` (version history only)
- **Framework**: `pyglet` for UI/Graphics rendering

## Development Workflow

### Installation
```bash
python -m pip install -r requirements.txt
```

**Key Dependencies:**
- `pyglet`: Graphics/UI framework
- `pylsl`: Lab Streaming Layer for data streaming
- `bleak`: BLE communication (Polar H10)
- `neurokit2`: HRV analysis
- `pytest`, `hypothesis`: Testing frameworks

### Running the Application
```bash
python main.py
```

**Configuration:**
- Primary config: `config.ini` (loaded at startup)
- Scenarios: `includes/scenarios/*.txt`
- Output: `sessions/user_<id>/<date>/`

### Testing
**Coverage Target: ≥90% on critical modules**

Run all tests:
```bash
pytest tests/ -v --cov=core --cov=plugins
```

**Test Strategy:**
- Unit tests for all core components
- Property-based tests with `hypothesis` for algorithms
- Integration tests for plugin lifecycle
- Treat warnings as errors: `pytest -W error`

### Quality Checks (Mandatory — Zero Warnings Policy)
All checks MUST pass before committing:

```bash
# Type checking (strict mode)
mypy --strict .

# Linting and formatting
ruff check .
black --check .
isort --check-only .

# Security scanning
bandit -r plugins/ core/
pip-audit
```

**Auto-fix formatting:**
```bash
black .
isort .
ruff check --fix .
```

## Architecture

### Core Components (`core/`)
- **`scenario.py`**: Scenario engine and parsing.
- **`logger.py`**: Centralized logging system.
- **`scheduler.py`**: Task scheduling.
- **`performance_summary.py`**: Post-run KPI generation.

### Plugins (`plugins/`)
All features are implemented as plugins inheriting from `plugins.abstractplugin.AbstractPlugin`.

**Plugin Lifecycle:**
1. `__init__()`: Initialize state, validate config
2. `create_widgets()`: Build UI components (Pyglet)
3. `do_on_command(command, value)`: Handle scenario events
4. `log_performance(metric, **kwargs)`: Record performance data

**Critical Plugins:**
- `physiomonitor.py`: Real-time HRV monitoring
- `polarrlink.py`: Polar H10 BLE interface
- `automationhooks.py`: Task automation and MQTT integration

### Data Flow
```
Scenario Files → main.py → core.scenario → core.scheduler → plugins
                                 ↓
                          core.logger → sessions/
```

**Input:**
- Scenario definitions: `includes/scenarios/*.txt`
- Configuration: `config.ini`

**Processing:**
1. `main.py`: Entry point, loads config
2. `core.scenario`: Parses scenario timeline
3. `core.scheduler`: Dispatches timed events
4. `plugins`: Execute tasks, log performance

**Output:** `sessions/user_<id>/<date>/`
- `performance_log.csv`: Raw event stream (timestamp, plugin, metric, value)
- `summary.json`: Aggregated KPIs and statistics
- `hrv/`: HRV time-series and analysis (if Polar H10 connected)

## Coding Standards

### Python Guidelines (Strictly Enforced)

**Code Structure:**
- **Type Hints**: Mandatory for all public functions; strict mypy compliance
- **Docstrings**: Google-style required (Args, Returns, Raises)
- **Function Size**: ≤60 executable lines, cyclomatic complexity ≤10
- **Cohesion**: Pure functions preferred; make side effects explicit

**Control Flow:**
- **No recursion** (use iteration with bounded counters)
- **Bounded loops only**: finite iterables or explicit `max_iterations`
- **No dynamic control**: no `eval`/`exec`, no dynamic imports
- All I/O operations must have finite timeouts

**Memory Safety:**
- **Immutability**: Prefer `tuple`, `frozenset`, `dataclasses(frozen=True, slots=True)`
- **Bounded collections**: Use `deque(maxlen=N)`, `lru_cache(maxsize=N)`
- **Context managers**: Always use for files, sockets, locks
- No global mutable state (pass state explicitly)

**Concurrency (when needed):**
- Single model per component (asyncio OR threads, not mixed)
- No shared mutable state; use queues/immutable messages
- All async ops wrapped in `asyncio.wait_for(timeout=N)`
- Track tasks and propagate exceptions

### Error Handling (Fail-Safe Design)

**Input Validation:**
- Explicit pre/postcondition checks with precise exceptions
- Target ~2+ defensive checks per function
- Use `ValueError`, `TypeError`, `RuntimeError` (never generic `Exception`)

**Exception Handling:**
- Never use bare `except:` — catch specific exceptions only
- Preserve context: `raise NewError(...) from original_error`
- Never ignore return values; use `_ = result  # intentionally unused` if needed

**Assertions:**
- Use `assert` ONLY for internal invariants (never for validation)
- Do not rely on asserts in optimized mode (`-O`)

**Failure Mode:**
- Fail closed: log error + raise on unexpected states
- Include sufficient context in error messages

### Security (Zero Trust)

**Data Handling:**
- **No `pickle` or `marshal`** on untrusted data
- JSON only, with schema validation (e.g., `jsonschema`)
- `yaml.safe_load()` only (never `yaml.load()`)

**Secrets Management:**
- No credentials in code or config files
- Use environment variables (`.env` for local dev)
- Rotate and audit secrets regularly

**Dependencies:**
- Run `pip-audit` and `bandit` before every commit
- Pin versions with hashes in `requirements.txt`

## Key Files Reference

| Purpose | File | Notes |
| :--- | :--- | :--- |
| **Documentation** | `Docs/Manual.md` | Primary feature docs — consult before coding |
| **Entry Point** | `main.py` | Application bootstrap |
| **Plugin Base** | `plugins/abstractplugin.py` | Abstract class for all plugins |
| **Scenario Engine** | `core/scenario.py` | Parses and executes scenario timelines |
| **Logging System** | `core/logger.py` | Centralized CSV logging |
| **Task Scheduler** | `core/scheduler.py` | Event dispatch system |
| **Performance KPIs** | `core/performance_summary.py` | Post-run analysis |
| **HRV Monitor** | `plugins/physiomonitor.py` | Real-time heart rate variability |
| **Polar H10 BLE** | `plugins/polarrlink.py` | Bluetooth sensor interface |
| **Automation** | `plugins/automationhooks.py` | MQTT hooks and task automation |

## WARP Agent Guidelines

**Before Starting Work:**
1. Check `Docs/Manual.md` for existing feature documentation
2. Review relevant plugin implementations in `plugins/`
3. Verify current test coverage: `pytest --cov`

**When Adding Features:**
- Document in `Docs/Manual.md` (never create new markdown files)
- Update `README.md` only for high-level project changes
- Update `CHANGELOG.md` with version/date/changes
- Add tests achieving ≥90% coverage for new code
- Run full quality checks before committing

**When Fixing Bugs:**
- Add regression tests first (TDD approach)
- Document fix in `CHANGELOG.md`
- Verify no new linter/type warnings introduced

**Code Generation Checklist:**
- [ ] Full type hints + Google-style docstrings
- [ ] Explicit input validation with specific exceptions
- [ ] Bounded loops and finite timeouts on I/O
- [ ] Context managers for all resources
- [ ] Immutable data structures where possible
- [ ] No recursion, eval/exec, or dynamic imports
- [ ] Tests with pytest + hypothesis (if applicable)
- [ ] Zero warnings from mypy, ruff, black, bandit

**Forbidden Patterns:**
- ❌ Recursion or unbounded loops
- ❌ `eval()`, `exec()`, `compile()` on user input
- ❌ `pickle` or `marshal` for data persistence
- ❌ Bare `except:` clauses
- ❌ Global mutable state
- ❌ Creating new markdown files (use existing docs only)
- ❌ Hardcoded secrets or credentials
