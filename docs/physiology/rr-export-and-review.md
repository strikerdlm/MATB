# Polar RR export and descriptive review

Every finalized capture retains its original Parquet/manifest files. Finalization
also attempts to create `rr-export/`; a derived-export failure leaves the raw
capture status unchanged and can be retried through the download endpoint.
Practice and study exports retain their purpose in filenames and metadata.

## Export contract

`matb.polar.rr-text.v1` uses **transmitted HRS RR ticks × 1000/1024**, never
60000/HR and never an ECG-derived substitute. Exact fractional milliseconds
are retained. No physiological artifact correction or interpolation is applied.

- `*_rr_segment-NNN_ms.txt`: one RR in ms per line; no header/time column.
- `*_rr_segment-NNN_ms.csv`: the same RR with one `rr_ms` header line.
- `*_rr_trace.csv`: every input row, beat index, ticks, RR, time, contact,
  continuity, connection epoch, exported flag and segment identifier.
- `rr_export_manifest.json`: original RR checksum, derived checksums, purpose,
  exclusions, segment boundaries and import settings.
- `capture_context.json`: controller-authorized derivative of persisted
  participant/session identity and software markers, with source manifest hash.
  Scan aliases explicitly are not persistent physical sensor identifiers.

Files split at acquisition gaps, reconnects, nonadjacent beat indices and
nonpositive/nonfinite RR. Numeric exclusions stay visible in the trace. Bad
contact flags remain available; raw values are not silently filtered.
Each continuous segment is an independent import. Joining segments would hide
gaps. Kubios custom ASCII import: RR, ms, column 1, no time column, TXT zero
header lines or CSV one header line. Source: [Kubios Scientific user guide](https://www.kubios.com/downloads/HRV-Scientific-Users-Guide.pdf).

Existing captures can be converted without the application database:

```powershell
python -m matb_integration.physiology.rr_export <capture-directory>
```

The source manifest and `rr.parquet` must match their checksum. Partial files
are rejected. The command never changes originals or publishes data.

## Review methods and limits

The local review selects the longest continuous numeric RR segment and its
last approximately 300 seconds (whole beats). It uses MATB's existing
Lipponen/Tarvainen-inspired rejection mask, contact flags and adjacent-pair
rules. This is a descriptive quick view, not automatic selection of the
protocol's basal endpoint. Short windows of ≥60 s are marked exploratory;
review PSD/LF/HF is omitted below 300 s. Poincaré pairs never cross a rejected
beat or acquisition boundary. The tachogram retains visible discontinuities.
The gauge represents accepted RR percentage, not a clinical normal range.
Unavailable phase contrasts and unavailable respiratory estimates are omitted.

Respiration uses stored x/y/z acceleration and sensor timestamps. It splits
discontinuities, uses 60 s windows with 30 s steps, removes >1 Hz movement
above engineering thresholds, filters/antialiases, resamples to 5 Hz, and
extracts a principal component in 0.10–0.70 Hz. Spectral concentration and
periodicity gates control abstention. Three axes preserve chest tilt that can
cancel out in vector magnitude. Algorithm identity:
`polar-acc-respiration-spectral-v1-experimental`.

**No human accuracy claim:** `accuracy_bpm=null`,
`validated_against_reference=false`. Synthetic rate tests establish software
behavior, not measurement accuracy or a confidence interval. Periodic voluntary
movement can resemble breathing even when gates pass. This is not a reproduction
of the published validated algorithms, and their errors cannot be transferred:
[Schipper et al., 2021](https://doi.org/10.1088/1361-6579/abf01f),
[chest-worn accelerometer/gyroscope comparison, 2022](https://pmc.ncbi.nlm.nih.gov/articles/PMC9599933/).

## HRV repository compatibility audit

Compared with `strikerdlm/HRV` commit
`e658af2b57ec07e60971d072ecd50673ba210508`, including its protected
[`hrs_parser.py`](https://github.com/strikerdlm/HRV/blob/e658af2b57ec07e60971d072ecd50673ba210508/app/research_workspace/polar/hrs_parser.py)
and native backend. The repeatable script
`scripts/verify_hrv_polar_compatibility.py --hrv-repo <checkout>` compares
8,208 packets spanning all HRS flag combinations and every uint16 RR value.
HR, original RR ticks, exact milliseconds, contact and energy fields match.
MATB additionally rejects unexpected trailing bytes when no RR flag is set.

Both native paths use a resolved Bleak device, avoid the HRS advertisement
UUID prefilter on Windows, inspect WinRT connectability and verify services
after connection. MATB now prepares the Windows apartment on each scan/connect
thread, matching HRV. MATB additionally acquires PMD ECG and ACC; HRV's protected
native backend is an HRS recorder. Browser Web Bluetooth has a separate access
model and is not asserted equivalent.

HRV's operational text reader accepts headerless TXT and recognized multicolumn
CSV, but **rejects a single-column CSV with a header**. Prefer each continuous
TXT for transfer. It also rejects values outside 200–3000 ms; MATB preserves
positive raw intervals. Export does not silently adopt the importer's exclusions.
MATB/HRV analysis pipelines are not numerically identical: correction,
windowing and eligibility policies must be compared separately. HRV's
[`respiration.py`](https://github.com/strikerdlm/HRV/blob/e658af2b57ec07e60971d072ecd50673ba210508/app/respiration.py)
uses a different RR/HF proxy; it is not this ACC estimator.

Software equivalence does not establish physical acquisition acceptance on
each H10/adapter. Test connect, RR reception, stop, export and reload on the
actual station before collection. [ASTRA field procedure](astra-baseline-polar.md).
