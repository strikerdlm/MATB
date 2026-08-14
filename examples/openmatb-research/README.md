# Offline OpenMATB research tour

[Español](README.es.md)

This fast, deterministic tour produces synthetic research artifacts without
starting OpenMATB. The external OpenMATB runner is separately installed when a
study needs to present the generated scenarios; it is not vendored or invoked
by this example.

## Install the selected research environment

The tour imports SciPy through the Suhir DEPDF fitter, and the continuation
commands use the statistics stack. Install `requirements-dev.txt`, which
includes the base and analysis dependencies, into a clone-local environment.

```bash
REPO_ROOT="$(pwd)"
python3 -m venv "$REPO_ROOT/.venv-openmatb"
"$REPO_ROOT/.venv-openmatb/bin/python" -m pip install -r "$REPO_ROOT/requirements-dev.txt"
```

```powershell
$RepoRoot = (Get-Location).Path
python -m venv (Join-Path $RepoRoot ".venv-openmatb")
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") -m pip install -r (Join-Path $RepoRoot "requirements-dev.txt")
```

## Run

From the repository root, choose any output directory you control. Direct
invocation is supported on both platforms:

```bash
REPO_ROOT="$(pwd)"
"$REPO_ROOT/.venv-openmatb/bin/python" examples/openmatb-research/run_example.py \
  --output-dir "$REPO_ROOT/examples/output/openmatb-research"
```

```powershell
$RepoRoot = (Get-Location).Path
$Python = Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe"
& $Python examples\openmatb-research\run_example.py `
  --output-dir (Join-Path $RepoRoot "examples\output\openmatb-research")
```

Or set `MATB_PYTHON` and use the native launcher, whose first optional argument
is the output directory. The wrapper validates the selected executable and
defaults to `python3` on Bash or `python` on PowerShell when the override is
absent.

```bash
REPO_ROOT="$(pwd)"
MATB_PYTHON="$REPO_ROOT/.venv-openmatb/bin/python" \
  bash examples/openmatb-research/run.sh "$REPO_ROOT/examples/output/openmatb-research"
```

```powershell
$RepoRoot = (Get-Location).Path
$env:MATB_PYTHON = Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe"
& .\examples\openmatb-research\run.ps1 `
  -OutputDir (Join-Path $RepoRoot "examples\output\openmatb-research")
```

The tour prints relative artifact names and ends with `External OpenMATB was
not started.` It writes only below the selected output directory:

- `scenarios/`: three fixed-seed, 900-second LOW/MEDIUM/HIGH scenario files;
- adjacent `*.txt.manifest.json` files: provenance including the scenario
  filename, SHA-256, workload level, duration, seed, and questionnaire setup;
- `metrics.jsonl`: one canonical converted record for each synthetic session;
- `suhir.json`: one DEPDF fit for `SYNTH-P01`.

Before conversion, the script parses every manifest and verifies that its
`scenario.sha256` matches the adjacent scenario file. A mismatch stops the
tour before any fit is written.

## What the synthetic sessions demonstrate

`fixtures/low.csv`, `medium.csv`, and `high.csv` use the OpenMATB converter
header and deliberately contain no participant data. They progressively vary
SYSMON response timing, misses, ISA `Workload`, and the six NASA-TLX fields:
`Mental demand`, `Physical demand`, `Time pressure`, `Performance`, `Effort`,
and `Frustration`.

Each fixture is converted with `matb_integration.log_converter.convert_session`.
The original parsed rows are retained for the DEPDF fitter, because its current
failure criterion derives time-to-failure from observed SYSMON `MISS` events.
All three levels therefore contain at least one deterministic miss. The tour
then calls `fit_participant` with LOW, MEDIUM, and HIGH records to estimate
G0, P0, and tau0; this is a small synthetic demonstration, not an inference
about a person or an operational system.

## Continue with analysis artifacts

The statistics CLIs take JSON arrays with the exact shapes returned by the
research console endpoints: `m.json` is the `GET /metrics/long` response and
`f.json` is the `GET /fits` response. The frequentist command is:

```bash
REPO_ROOT="$(pwd)"
"$REPO_ROOT/.venv-openmatb/bin/python" -m matb_integration.analysis.stats.cli run \
  --metrics-json m.json --fits-json f.json -o artifact.json
```

The separate Bayesian sensitivity command has the same two JSON-array inputs:

```bash
REPO_ROOT="$(pwd)"
"$REPO_ROOT/.venv-openmatb/bin/python" -m matb_integration.analysis.stats.cli bayes \
  --metrics-json m.json --fits-json f.json -o bayes.json \
  --seed 42 --draws 1000 --tune 1000 --chains 4
```

PyMC sampling is intentionally not part of this fast tour. Run the Bayesian
command only with an appropriate research dataset and sampling environment.
