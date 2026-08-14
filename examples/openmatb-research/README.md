# Offline OpenMATB research tour

[Español](README.es.md)

This fast, deterministic tour produces synthetic research artifacts without
starting OpenMATB. The external OpenMATB runner is separately installed when a
study needs to present the generated scenarios; it is not vendored or invoked
by this example.

## Run

From the repository root, choose any output directory you control:

```bash
python3 examples/openmatb-research/run_example.py --output-dir /tmp/matb-tour
```

Or use the native launcher, whose first optional argument is the output
directory:

```bash
examples/openmatb-research/run.sh /tmp/matb-tour
```

```powershell
.\examples\openmatb-research\run.ps1 -OutputDir C:\Temp\matb-tour
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
python3 -m matb_integration.analysis.stats.cli run \
  --metrics-json m.json --fits-json f.json -o artifact.json
```

The separate Bayesian sensitivity command has the same two JSON-array inputs:

```bash
python3 -m matb_integration.analysis.stats.cli bayes \
  --metrics-json m.json --fits-json f.json -o bayes.json \
  --seed 42 --draws 1000 --tune 1000 --chains 4
```

PyMC sampling is intentionally not part of this fast tour. Run the Bayesian
command only with an appropriate research dataset and sampling environment.
