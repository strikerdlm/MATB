# Install MATB on Windows

[English](WINDOWS.md) | [Español](WINDOWS.es.md)

1. Download the repository ZIP and **Extract all**, or clone it. Use a writable
   folder such as `C:\Users\YourName\MATB`; keep the complete repository together.
2. Double-click **Install MATB.cmd**. On Windows 10/11 (64-bit), it provisions
   missing PowerShell 7, Python 3.12 (64-bit), and Node.js 22 through WinGet.
   It creates `.venv-suas`, installs the Windows package lock, prepares offline
   export wheels, installs the locked frontend, builds it and runs focused checks.
   First setup needs Internet. Accept Windows' elevation prompt if a runtime
   installer requires it. Keep the setup window open until it finishes.
3. Double-click **Start MATB.cmd**. The browser opens
   `http://127.0.0.1:3100/start`. Choose OpenMATB or another activity and select
   practice or your assigned study session. Keep the supervisor window open.

| Shortcut | Action |
| --- | --- |
| `Install MATB.cmd` | Install or repair the research application |
| `Start MATB.cmd` | Open the Research Console |
| `Start OpenMATB.cmd` | Open desktop OpenMATB in Spanish, windowed on the first display |
| `Diagnose MATB.cmd` | Check packages, build, scenario, processes, ports and logs |
| `Stop MATB.cmd` | Stop tracked Console services |

The original shortcuts under `windows-launchers/` remain available. For a
controlled study, use the Console's assigned-session workflow. Direct desktop
runs are a separate workflow. The installed local Console and bundled tasks
work offline; optional online maps, live traffic and model providers need
connectivity. Bluetooth acquisition needs compatible hardware.

Data defaults to `exports/windows-suas/`: desktop captures use `desktop/`,
and the Console database, captures, calculator wheels and logs use `service/`.
Set `MATB_DATA_ROOT` to a dedicated external directory to relocate data.
Installation logs use `exports/windows-install/`. Preserve data when updating.
Avoid Program Files and cloud-synchronized folders for the source and runtime.

The installer uses a local Python environment by default. Explicit
`MATB_PYTHON` or `MATB_VENV` overrides allow installation into that selected
environment; clear them to use the isolated default. Windows/Python 3.12 uses
`release/requirements-windows-py312.lock`; other explicitly selected supported
versions use source requirements. Windows and WSL need separate environments
and builds. The shortcuts need neither WSL nor Git for ZIP installation. ZIP
source provenance correctly remains provisional.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| WinGet missing | Install/update [Microsoft App Installer](https://apps.microsoft.com/detail/9nblggh4nns1) and rerun setup. |
| Institution blocks installation | Ask IT to install prerequisites. Manual downloads: [PowerShell](https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell-on-windows), [Python 3.12](https://www.python.org/downloads/windows/), [Node.js 22](https://nodejs.org/en/download). |
| PowerShell policy blocks scripts | Shortcuts use a process-only policy and do not change machine policy. Institution-enforced policies still apply; ask IT to approve the scripts. |
| Packages/build fail | Rerun `Install MATB.cmd` and read the timestamped installation log. |
| npm `EPERM` on `node_modules/.vite/vitest/.../results.json` | Once the station is idle, close frontend tests, run `Stop MATB.cmd`, then `Install MATB.cmd` and `Start MATB.cmd`. Setup preserves the old test cache outside `node_modules` before reinstalling. See below if using an older launcher. |
| Port 8000 or 3100 occupied | Stop the known service or pass `-BackendPort`/`-FrontendPort` to the existing PowerShell launcher. |
| Research export reports a missing wheel | Rerun setup using the same data root and Python interpreter as the Console. |
| Repository moved | Stop the old Console and rerun setup in its new location. |

This `results.json` is a generated test cache. It is unrelated to participant
results. Windows may prevent its deletion when it was created by another
account (including an automated test account), or when a process holds it open.
Setup preserves it in `webui/frontend/.matb-cache-backup-*`; new tests use a
temporary cache scoped to the account and checkout. Participant data stays in
the configured data root.

For an older launcher, close tests and stop MATB while the station is idle,
then run this in PowerShell from the repository folder before retrying setup:

```powershell
$frontend = (Resolve-Path -LiteralPath '.\webui\frontend').Path
$cache = Join-Path $frontend 'node_modules\.vite'
$backup = Join-Path $frontend ('.matb-cache-backup-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $cache) {
    [System.IO.Directory]::Move($cache, $backup)
}
```

If the move is blocked too, restart Windows and retry before opening MATB or
tests. A continuing access error requires checking permissions on that specific
cache. Do not delete the study data or disable antivirus protection.

The Windows installer CI job checks setup, isolation, versions, startup,
replay, diagnostics and shutdown in paths containing spaces and Unicode.
Physical display/audio timing, controllers and Polar H10 acquisition require
verification on the actual station.
