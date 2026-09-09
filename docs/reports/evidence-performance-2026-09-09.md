# Evidence and presentation performance — 2026-09-09

These are executed synthetic software measurements on the existing Windows 11
development workstation, not physical timing qualification or a clean laboratory
experiment. Acquisition remains synchronous. No participant/health data is used.
The [consolidation report](evidence-integration-verification-2026-09-09.md)
separately documents clean dependency environments on Windows and Linux.

## Recorder cost

Paired deterministic workloads alternate recording off/on across three repeats,
with 1,000 samples per run. Both modes produce the same workload checksum.
`perf_counter_ns` measures synchronous recorder calls, synthetic dispatch lateness
and sample spacing. A call includes event/timing validation, serialization,
writing and flushing. Baseline timing encloses a no-record operation.

| Synthetic interval | Recorded call median by repeat (ms) | p99 by repeat (ms) | Maximum by repeat (ms) | Gaps exceeding twice the interval, recorded / baseline |
| --- | --- | --- | --- | --- |
| 2 ms (500 Hz stress) | 0.878 / 0.926 / 0.856 | 1.301 / 1.149 / 1.070 | 8.046 / 6.029 / 7.146 | 4 / 0 |
| 10 ms (100 Hz) | 1.391 / 1.022 / 1.080 | 2.581 / 2.126 / 2.050 | 11.845 / 10.596 / 6.696 | 1 / 0 |

The maximum synthetic dispatch lateness was 6.104 ms at 500 Hz and 19.018 ms at
100 Hz. These are separate runs; they do not establish a monotonic frequency
effect or isolate the recorder as the cause of every scheduler stall. The
workstation was not reserved as a qualified idle rig; other development work
occurred during the measurement campaign. Prespecified protocol limits are
absent, so acceptance is **not assessed**. Physical input latency and physical
stimulus onset remain unavailable. Tail stalls support measuring actual
laboratory workloads before adopting asynchronous buffering or claiming adequacy.

Raw per-sample CSVs and complete percentile summaries are retained in
[the measurement directory](evidence-performance-2026-09-09/).

## Long and near-limit evidence captures

Each row runs the production service in a fresh process and SQLite database.
Before/after comparisons reuse the exact same source bytes and checksums.
Measurements include source parsing, reconciliation, indexing, export, duplicate
re-upload and two concurrent duplicate requests. They exclude HTTP upload
transport. Concurrent first-time large uploads were not characterized.

| Source case / implementation | First import (s) | ZIP export (s) | Identical re-upload (s) | Process lifetime peak RSS (MiB) |
| --- | ---: | ---: | ---: | ---: |
| 30-minute tracking / original path | 78.310 | 5.652 | 12.693 | 688.7 |
| Same source / batched links and fast duplicate path | 58.088 | 6.373 | 0.052 | 641.7 |
| Near-limit / original path | 34.911 | 3.992 | 5.010 | 1269.0 |
| Same source / final incremental BLOB export | 33.048 | 3.641 | 0.263 | 1269.6 |

The 30-minute source contains 34,557,595 event bytes and 15,735,059 timing bytes
(18,000 tracking ticks). The near-limit source contains 263,640,363 event bytes:
98.21% of the 256 MiB per-stream limit. It uses 3,000 ticks plus 85,000 repeated
padding bytes per tick to exercise byte limits, not a physiologically meaningful
recording. Padding compresses strongly; its 3.38 MB ZIP is not representative of
all near-limit files. The final database occupies 551,202,816 bytes (~526 MiB).

The 30-minute duplicate path improved because unchanged immutable bytes are
hashed before parsing. The two concurrent duplicate requests took 0.064/0.068 s
afterward, versus 30.17/30.40 s on the original path. The final near-limit requests
took 0.298/0.262 s. These single-process observations are not statistical claims
about throughput under multi-client laboratory load.

A first disk-backed export experiment used repeated SQLite substring queries;
its near-limit export regressed to 124.506 s. That implementation was rejected.
The final path uses SQLite incremental BLOB reads and measured 3.641 s on the
same bytes. The intermediate report is retained to make the decision auditable.

Full event parsing and derivation remain in memory. Near-limit peak RSS did not
materially decrease, despite bounded source reads during export. Reserve adequate
memory and disk, then qualify the declared capacity; the stream limit is not a
promise that several concurrent maximum-size captures fit a small workstation.

Recovery checks include marking pending derivations `interrupted_processing`
and a real child-process exit during indexing. SQLite rolled back the interrupted
transaction and the same capture could be imported again. This does not claim
recovery from storage corruption, power loss or exhausted disks.

## Scene-object CPU measurements

The benchmark compares the consolidated legacy rebuild pattern at
`dcb3df934e86c3d834aa6a0409ec5fd5feb2f7e3` with keyed objects. Each case uses 10
warmup updates and 120 measured updates; contact changes trigger the old aircraft
reconstruction. Final aircraft positions match in both implementations.

| Aircraft / contacts | Original median / p95 (ms) | Keyed median / p95 (ms) | Aircraft objects created, original / keyed |
| --- | --- | --- | --- |
| 12 / 40 | 5.619 / 9.596 | 0.061 / 0.134 | 1560 / 12 |
| 40 / 400 | 27.774 / 34.116 | 0.400 / 0.541 | 5200 / 40 |
| 80 / 1000 | 69.285 / 90.101 | 0.520 / 0.958 | 10400 / 80 |

This measures object lifecycle/transform CPU work in Node with Three.js, not
WebGL rendering, terrain, labels, browser compositing, transport or physical
display onset. It demonstrates removal of unnecessary allocations; it does not
establish a corresponding GPU/frame-rate improvement.

Browser verification exposed another problem: multiple update paths could submit
frames during a refresh, causing screenshot/input timeouts under SwiftShader.
Coalescing invalidations into a single pending submission resolved the three
LOW/MEDIUM/HIGH acceptance cases without increasing their timeouts, reducing
graphics quality or changing the pinned interpolation duration. Those cases cover
camera changes, pause, technical 2D/3D fallback, resource lifecycle and mobile
layout. The renderer reports GPU completion and physical onset as unavailable.

## Evidence and precision

The reference inspector browser scenario executes upload, result selection,
source/timing inspection, checksummed export, offline recalculation, reopening,
event navigation and a narrow layout check. Retained desktop/mobile screenshots
show synthetic data and explicitly label original visual exposure unavailable.
Older `classic-evidence-1.0` exports still verify without assigned analysis
execution metadata. Qualification-link tests preserve metric eligibility and
reject changed context, attachment corruption and hidden revocation state.

Reports were collected during development on the `bbd99de` follow-up checkout;
their source metadata correctly records modified trees. Recorder reports include
writer/benchmark hashes; source artifacts have exact hashes. The scene report
records the baseline commit and compared outputs. The committed report inventory
is checksummed. These reports must not be relabeled as clean release benchmarks.
Final source verification is recorded separately in `verification.json` in the
measurement directory.

Final application source: `34d8910878967ed4b6879b848e6203204ded1e1c`.
The subsequent report commit changes documentation/artifacts only.

| Executed check | Windows | Linux |
| --- | --- | --- |
| Contracts / public-core boundary | 585 passed, 9 skipped | 585 passed, 9 skipped |
| Backend | 281 passed, 1 skipped | 281 passed, 1 skipped |
| Frontend unit suite | 152 passed | 152 passed |
| Final production browser | 8 passed, synthetic observed-traffic fixture | 1 passed, evidence workflow |
| Lint / TypeScript / production build | Passed | Passed |

Windows additionally passed 184 engine/evidence/recovery tests with one skip.
The final Linux revision passed 18 focused presentation/evidence UI tests. Broader
Python/backend checks ran on the same application source at `5962054`; only two
presentation files changed afterward. The frontend unit suite and final focused
checks cover those updates; final build/browser checks use the revision above.
Windows broad suites used the precommit working tree; Linux used a fresh Git
checkout and npm installation in the disposable Debian environment. Detailed
source contexts, JUnit results, compiler/browser logs and the caught intermediate
TypeScript failure are retained in `verification.json` and
`software-verification.zip`. The initial native-capture checks remain documented
with the separate consolidation verification.

Hosted Actions remains blocked by the account billing/spending restriction,
independent of application assertions. No scientific release gate was weakened.
Full synchronized Replay Studio, hardware/physical onset qualification, human
calibration, preregistered visual-condition studies and cross-condition adaptive
model validation remain separate work requiring real measurements or protocols.

Implementation and rerun commands:
[evidence review and qualification](../implementation/evidence-review-qualification-performance.md).
