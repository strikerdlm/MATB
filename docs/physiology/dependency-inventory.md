# Polar H10 optional dependency inventory

This is the source-controlled Release A inventory. A release SBOM generated from
the locked delivery environment remains mandatory.

| Package/source | Pinned/qualified version | Role | License evidence |
| --- | --- | --- | --- |
| Bleak | `3.0.2` | Windows BLE scan/GATT/notifications | package metadata: MIT |
| polar-python | `1.1.1` | public PMD settings and packet parsing | package metadata: MIT |
| PyArrow | `>=18,<25` (qualified locally with 24.0.0) | Zstandard Parquet writing | package metadata: Apache-2.0 |
| strikerdlm/HRV | commit `ef086092…e6a` | HRV equations/detector provenance | `LICENSES/HRV-MIT.txt` |
| Polar BLE SDK | repository reference used by scoped advertisement parser | H10 feature/protocol reference | `LICENSES/Polar_SDK_License.txt` |

`polar-python` is isolated behind `PolarTransport`. Release A acceptance requires
the exact scanned device, one shared connection, simultaneous HRS/ECG/ACC,
correct Windows shutdown, and byte-exact fixtures. If hardware qualification
finds a failure, only the necessary MIT parser/transport modules may be vendored
with source hashes and notices; the interface and stored schemas must not change.
