# MATB UAS Windows launchers

These Explorer-friendly launchers start the native sUAS console or run a
deterministic technical workload profile without changing study scenarios.
They require PowerShell 7, Python 3.12+, Node.js 20+, and npm.

Run `00 - Preparar MATB UAS.cmd` once, then use
`01 - Abrir consola UAS.cmd` for the interactive mouse-enabled console. Keep
its supervisor window open and press `Ctrl+C`, or run
`99 - Detener MATB UAS.cmd`, to stop the exact tracked services.

The `PRACTICE`, `LOW`, `MEDIUM`, and `HIGH` shortcuts execute the complete
configured block duration headlessly, write to a unique directory under
`exports/windows-suas/runs/`, and verify replay plus checksums. These are
technical simulations, not valid participant sessions. Research sessions must
still start with `PRACTICE` and follow the participant's counterbalanced order.

The service binds only to loopback and stores its database, artifacts, logs,
and process state under the Git-ignored `exports/windows-suas/service/` root.
The stop launcher validates the recorded PID, exact executable, and start
time; when Windows permits that inspection, it also validates the command
line. It does not stop unrelated Python or Node processes.
