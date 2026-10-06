# Windows launcher restart and native presentation

The root CMD files and the numbered Windows shortcuts use the same runtime
discovery and process-only execution policy. `Start MATB.cmd` now replaces an
existing instance instead of silently reusing it. Preparation stops the prior
instance before changing packages or the production build. The startup mutex
prevents concurrent preparation in the same installation.

Restart targets the selected TCP listeners (8000/3100 by default), validated
tracked processes, their captured descendants, and native OpenMATB windows
whose command line belongs to this installation. This intentionally displaces
any application occupying the selected ports, including one launched manually.
It does not terminate Python/Node globally. PID creation times and executable
paths are rechecked before termination; the launcher's ancestors and protected
processes are excluded. Invalid/missing state does not block port recovery.
An old supervisor cannot remove a replacement instance's state file.

Stop/restart retains recordings and databases. A native acquisition interrupted
by restart is recovered by the backend as interrupted, never completed. An
explicit `MATB_DB_PATH` wins; otherwise an implicit default launch reuses the
historical manual-start database if present. Explicit data roots remain
isolated. No databases are merged or deleted by these launchers.

Frontend checks resolve Next, React, MapLibre and TypeScript as well as checking
the package-lock stamp. Setup preserves the old Vitest cache before a locked
install. The backend remains one worker without reload. Console CMD launches
detach after readiness; the normal browser opens only after both services are
healthy. `MATB_NO_PAUSE=1` supports automated CMD verification.

## Native Windows presentation

The fullscreen request continues to use a borderless window inside the selected
monitor's work area. Pyglet 2.1.14 disables WGL vsync for composed windows and
skips its `DwmFlush` call on Windows 8 and later. OpenMATB now synchronizes the
completed frame with the compositor before swapping buffers on those systems,
following Pyglet's presentation order for older Windows versions.
Hidden preparation windows, exclusive windows, disabled vsync, and other
platforms retain their previous presentation path. A failed compositor call
falls back once to driver vsync instead of interrupting acquisition.

This is a targeted mitigation for the reported fullscreen flicker, based on the
installed Pyglet implementation and the [Microsoft DwmFlush contract](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/nf-dwmapi-dwmflush).
The [Pyglet Windows implementation](https://github.com/pyglet/pyglet/blob/v2.1.14/pyglet/window/win32/__init__.py)
documents the WGL/composition behavior. No driver, registry, display refresh
rate, task clock, or scoring setting is changed.

## Verification on Windows, 6 October 2026

- Launcher portability, locked Vitest cache recovery and PowerShell syntax tests.
- Real process-tree tests: parent/child closure, corrupt state, repeated stop,
  stale PID rejection, retained CSV sentinel and an unaffected unrelated port.
- Full relocation test using paths with spaces/Unicode and real CMD entry points:
  PRACTICE/LOW/MEDIUM/HIGH technical runs, checksum/replay verification, result
  lookup, cold start, healthy restart, restart without valid state, runtime API
  port discovery, diagnostic READY and stop with both ports released.
- `Install MATB.cmd` and `Start MATB.cmd` executed in the primary installation;
  the selected database remained the historical manual-start database.
- 123 native window, scheduler, preflight, keyboard, replay and control-bridge
  regressions passed, together with scoped Ruff and bilingual documentation checks.
- Native synthetic runs activated all four tasks, returned status, accepted abort
  and exited with code 0 and empty stderr. The observed station uses Intel Iris Xe,
  double buffering and a borderless 1920 x 1019 client on a 1920 x 1080 display.
  The no-joystick warning was retained and acknowledged only within the synthetic
  display diagnostic; no study preflight requirement was bypassed.

These are software/desktop checks, not participant acquisitions or hardware
timing qualification. Frame timing logs do not establish the absence of every
physical display flicker; the operator's visual confirmation remains relevant.
