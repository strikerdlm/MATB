# Legacy aircraft-monitor workflows

[Español](README.es.md)

These native launchers run the repository's legacy aircraft-monitor modes with
deterministic `--seed 42`, `--headless`, and the minimum supported event delay
of `0.05` seconds. They do not change application behavior.

## Run a mode

The Bash launcher accepts a mode and, optionally, a caller-selected output
directory. It defaults to `combined` and only passes that output directory to
the application in `experiment` mode.

```bash
examples/legacy-monitor/run.sh uav
examples/legacy-monitor/run.sh fighter
examples/legacy-monitor/run.sh combined
examples/legacy-monitor/run.sh experiment /tmp/legacy-monitor
```

The PowerShell launcher uses the same contract and restricts the mode to the
four supported values:

```powershell
.\examples\legacy-monitor\run.ps1 -Mode uav
.\examples\legacy-monitor\run.ps1 -Mode fighter
.\examples\legacy-monitor\run.ps1 -Mode combined
.\examples\legacy-monitor\run.ps1 -Mode experiment -OutputDir C:\Temp\legacy-monitor
```

For `experiment`, the launcher also supplies synthetic identifiers
`SYNTH-P01` and `SYNTH-S01`, plus `--research-output-dir`. Consequently,
experiment artifacts are written only below the output directory you select.
The other three simulations do not receive a research-output directory.

## Completion, interruption, and cleanup

Successful runs print `Simulation complete!`. Press Ctrl-C to stop a run; the
application reports that it was terminated by the user and returns normally.

Inspect an experiment output directory before retaining or sharing anything:

```bash
find /tmp/legacy-monitor -maxdepth 2 -type f
```

The launchers' default experiment location is
`examples/output/legacy-monitor`. To remove only those default example
artifacts, use:

```bash
rm -rf examples/output/legacy-monitor
```

Do not use that cleanup command for a caller-selected directory unless it is
the directory you intentionally want to remove.
