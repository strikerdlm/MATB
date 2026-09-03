# Native Polar H10 acquisition — Release A

## Scope and safety boundary

`matb-physiology` is an optional, experimental Windows 11 component. It owns
one direct-computer Bluetooth connection, raw local physiology artifacts,
resumable operator monitoring, and descriptive HRV outputs. It does not replace
the external `HrvTaskClient`, upload physiology, diagnose a person, classify
workload, establish fitness for duty, or generate operational alerts.

The official Polar SDK runtime targets Android and iOS. The desktop adapter uses
Bleak and `polar-python` PMD parsing behind a MATB-owned interface. The correct
Bluetooth Heart Rate Service decoder is MATB-owned because it must support
8/16-bit heart rate, energy-expended fields, contact flags, and all RR values.

## Installation and activation

Use Python 3.12 on Windows and install the optional dependency set:

```powershell
python -m pip install -r webui/backend/requirements.txt
python -m pip install -r webui/backend/requirements-physiology.txt
```

`MATB_COMPONENTS=auto` loads the component from this source tree. A restricted
deployment can use `MATB_COMPONENTS=matb-openmatb,matb-physiology`. Set
`MATB_PHYSIOLOGY_DIR` to an absolute institution-controlled directory; the
default is ignored `exports/physiology/`.

## Operator flow

1. Wet and fit the H10 strap, close competing Polar/Bluetooth receivers, and
   open **Polar H10** in the Research Console.
2. Use the bounded broadcast listen only as a preflight. Broadcast heart rate
   has no RR series and is never used for HRV.
3. Scan and connect. Windows scanning deliberately has no HRS UUID prefilter;
   the connection verifies HRS and PMD characteristics afterward. A raw
   `is_connectable=False` advertisement fails before GATT.
4. Link a pseudonym and MATB session. OpenMATB capture start is accepted only
   while that session is `READY`.
5. Start the default five-minute seated baseline. Release A requires HRS,
   ECG 130 Hz/14 bit, and the exact selected ACC rate/range. Default ACC is
   50 Hz and ±2G. No requested setting is silently substituted.
6. OpenMATB starts automatically insert PRACTICE/LOW/MEDIUM/HIGH markers. Suite
   completion inserts RECOVERY; retain five minutes before stopping.
7. Stop and inspect gap/incomplete reasons before downloading the controller-
   authorized bundle.

## Storage and time bases

High-rate samples are written by bounded per-stream queues into Zstandard
Parquet files. Live filenames end in `.partial`; successful closure atomically
renames them. Queue overflow, writer errors, unexpected disconnects, sensor
timestamp discontinuities, shutdown, and incomplete finalization remain in the
manifest and invalidate affected analytical windows.

- `rr.parquet`: original 1/1024-second RR ticks, derived milliseconds, HR,
  contact flags, notification/beat indices, host receipt clocks, gap boundaries,
  and connection epoch.
- `ecg.parquet`: µV values, packet/sample indices, original PMD sensor time,
  reconstructed host-monotonic/UTC clocks, receipt clocks, and connection epoch.
- `acc.parquet`: x/y/z mG plus exact rate/range, indices, both time bases, and
  connection epoch.
- `manifest.json`: schemas, counts, settings, clock model, algorithm versions,
  incompleteness reasons, and SHA-256 for every Parquet file.

HRS beat times are explicitly `host_reconstructed_unknown_ble_latency`. MATB
markers are host-monotonic software observations and are not physical stimulus
onset measurements.

## HTTP interface

All endpoints are under `/physiology/polar-h10/v1`. State-changing calls retain
the Console loopback/origin/token defenses. Scan results expose expiring device
tokens and aliases only. Captures return a separate controller lease used for
start, markers, stop, WebSocket monitoring, inventory, and bundle retrieval.

The WebSocket route
`/captures/{id}/stream?after_sequence=N&lease=...` replays retained events after
`N`. Only HR/quality and decimated ECG envelope/ACC magnitude previews reach the
browser; raw high-rate samples remain in the local files.

## Stage 2 gate

Internal H10 recording status/start/stop/list/fetch/remove routes exist as a
stable path surface but return `501 polar_internal_recording_not_qualified`.
They must not be enabled until the Polar license assessment and every physical-
hardware acceptance row are approved. Deletion will additionally require a
previously fetched SHA-256 and explicit confirmation.
