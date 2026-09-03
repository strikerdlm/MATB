# Polar H10 Windows hardware acceptance report

**Status: NOT EXECUTED — physical Polar H10 and approved participant-free bench
session are required. This template is committed as a release gate, not as
evidence that hardware qualification passed.**

Preflight on 2026-09-03: the bounded, address-redacted Bleak scan was attempted,
but Windows returned `BleakBluetoothNotAvailableReason.POWERED_OFF`. No H10
discovery, connection, or sample claim can be made from that attempt. Turn on
the Bluetooth radio and rerun the matrix below.

## Configuration record

| Field | Observed value |
| --- | --- |
| Date/operator | PENDING |
| Windows build | PENDING |
| Bluetooth adapter/driver | PENDING |
| Polar H10 firmware | PENDING |
| Strap/electrode state | PENDING |
| Competing receivers closed | PENDING |
| Python/Bleak/polar-python | 3.12 / 3.0.2 / 1.1.1 |

## Acceptance matrix

| Test | Required evidence | Result |
| --- | --- | --- |
| Listen-only broadcast | HR, contact, RSSI; no address in API/log | PENDING |
| Connected HRS | HR plus raw RR ticks and ms | PENDING |
| Connected ECG | signed µV, 130 Hz, timestamps | PENDING |
| Simultaneous streams | HRS + ECG + ACC without silent substitution | PENDING |
| ACC 25 Hz | ±2G, ±4G, ±8G | PENDING |
| ACC 50 Hz | ±2G, ±4G, ±8G | PENDING |
| ACC 100 Hz | ±2G, ±4G, ±8G | PENDING |
| ACC 200 Hz | ±2G, ±4G, ±8G | PENDING |
| Non-connectable advertisement | explicit pre-GATT rejection | PENDING |
| Disconnect/reconnect | gap and epoch visible; no analytical bridging | PENDING |
| Queue pressure | overflow counter and invalid reason | PASS — simulated |
| 60-minute soak at 50 Hz/±2G | >=99.5% expected samples and zero unreported loss | PENDING |
| Shutdown/restart | `.partial` retained and prior active row failed explicitly | PASS — simulated |
| Address privacy | no raw BLE address in API, SQLite, artifacts, or generic export | PENDING audit |

Expected samples must be calculated from the sensor time span and resolved rate,
not merely from host elapsed time. Packet/timestamp gaps, callback queue loss,
and disconnect epochs must be reconciled before signing the soak row.

## Stage 2 internal recording

Keep all rows PENDING until the license gate is accepted: start one-second HR
recording, occupied-storage conflict, status, stop, list, interrupted fetch,
SHA-256 verification, deletion confirmation, and firmware variation. Internal
recordings remain separate from synchronized workload analysis unless adequate
task clock anchors exist.

## Approval

| Role | Name/signature/date |
| --- | --- |
| Engineering verifier | PENDING |
| Scientific reviewer | PENDING |
| Privacy/licensing reviewer | PENDING |
