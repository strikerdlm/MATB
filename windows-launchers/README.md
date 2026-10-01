# MATB UAS Windows launchers

For a new computer, use the top-level `Install MATB.cmd`, then `Start MATB.cmd`
for the full Console or `Start OpenMATB.cmd` for the desktop.
See [Windows setup](../WINDOWS.md) for automatic prerequisites and offline exports.

These Explorer-friendly launchers start the native sUAS console or run a
deterministic technical workload profile without changing study scenarios.
They require PowerShell 7, Python 3.12+, Node.js 20.9+, and npm.

Run `01 - Abrir consola UAS.cmd` for the interactive mouse-enabled console.
It now checks and repairs dependencies, refreshes a stale production build,
starts the local services, and opens the guided `/start` page. Use
`00 - Preparar MATB UAS.cmd` only when you want to prepare the station and run
focused checks without opening the console. Keep its supervisor window open and press `Ctrl+C`, or run
`99 - Detener MATB UAS.cmd`, to stop the exact tracked services.

`02 - Diagnosticar MATB UAS.cmd` performs a read-only check of the runtimes,
dependencies, production build, scenario, ports, tracked processes, HTTP
health, and latest sealed run. A stopped console with free ports is healthy.

The `PRACTICE`, `LOW`, `MEDIUM`, and `HIGH` shortcuts execute the complete
configured block duration headlessly, write to a unique directory under
`exports/windows-suas/runs/`, and verify replay plus checksums. These are
technical simulations, not valid participant sessions. Research sessions must
still start with `PRACTICE` and follow the participant's counterbalanced order.

The service binds only to loopback and stores its database, artifacts, logs,
and process state under the Git-ignored `exports/windows-suas/service/` root by
default. Set `MATB_DATA_ROOT` to an absolute external directory, or pass
`-DataRoot` to an internal PowerShell script, to relocate all mutable data.
The explicit parameter takes precedence over the environment variable. Relative
values are anchored to the repository, not the caller's current directory.
Repository, drive, and user-profile roots are rejected as unsafe data roots.
The stop launcher validates the recorded PID, exact executable, and start
time; when Windows permits that inspection, it also validates the command
line. It does not stop unrelated Python or Node processes.

Profile shortcuts are independent of the directory from which Explorer starts
them and support repository and data paths containing spaces or Unicode. Python
may be selected with either `MATB_PYTHON` (path or command name) or a
platform-native `MATB_VENV`. The console also detects the Git commit and worktree state before it
starts the backend. Experiment Designer provenance is `complete` only for a
verified clean clone; a modified tree, unavailable Git check, or ZIP without
Git metadata correctly remains provisional. After updating the launchers, stop
the old console with shortcut `99` and start it again with shortcut `01` so the
new backend process receives the provenance values.

`91 - Abrir resultados MATB UAS.cmd` opens the latest sealed technical run and
the service log directory in Explorer when present. It only opens paths below
the configured data root; shortcut `90` remains the full replay and checksum
verification action.
