"""Loss-visible, uncorrected Polar RR exports for Kubios text import."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import threading

from .contracts import PolarArtifactManifestV1

EXPORT_VERSION = "matb.polar.rr-text.v1"
PREVIEW_LIMIT = 200
_LOCK = threading.Lock()


class RRExportError(ValueError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _number(value: float) -> str:
    # HRS ticks * 1000 / 1024 are exactly representable with seven decimals.
    return f"{value:.8f}".rstrip("0").rstrip(".")


def export_rr_capture(root: Path, manifest: PolarArtifactManifestV1 | None = None) -> dict:
    """Write derived files beside a finalized capture, leaving raw artifacts intact.

    Both practice and study retain their recorded purpose. The one-column files
    contain transmitted RR, never 60000/HR or ECG-derived/corrected intervals.
    Gaps and invalid numeric intervals split files rather than joining beats.
    """
    import pyarrow.parquet as pq

    root = root.resolve()
    if manifest is None:
        manifest = PolarArtifactManifestV1.model_validate_json((root / "manifest.json").read_text("utf-8"))
    if list(root.glob("*.partial")):
        raise RRExportError("polar_artifacts_not_finalized")
    source = (root / "rr.parquet").resolve()
    entry = next((item for item in manifest.artifacts if item.relative_path == "rr.parquet"), None)
    if source.parent != root or entry is None or not source.is_file() or sha256(source) != entry.sha256:
        raise RRExportError("polar_artifact_checksum_failed")
    if not manifest.capture_id or any(c not in "0123456789abcdef-" for c in manifest.capture_id.lower()):
        raise RRExportError("polar_artifact_path_invalid")
    target = (root / "rr-export").resolve()
    if target.parent != root:
        raise RRExportError("polar_artifact_path_invalid")

    with _LOCK:
        target.mkdir(exist_ok=True)
        index_path = target / "rr_export_manifest.json"
        if index_path.is_file():
            index = json.loads(index_path.read_text("utf-8"))
            if (index.get("schema_id"), index.get("source_sha256"), index.get("capture_id"), index.get("execution_purpose")) != (
                EXPORT_VERSION, entry.sha256, manifest.capture_id, manifest.execution_purpose,
            ):
                raise RRExportError("polar_rr_export_metadata_mismatch")
            for item in index["files"]:
                path = (target / item["filename"]).resolve()
                if path.parent != target or not path.is_file() or sha256(path) != item["sha256"]:
                    raise RRExportError("polar_artifact_checksum_failed")
            return index

        table = pq.ParquetFile(source)
        columns = ["beat_index", "rr_ms", "rr_ticks_1024", "beat_monotonic_ns", "received_utc_ns",
                   "gap_before", "connection_epoch", "contact_supported", "contact_detected"]
        if not set(columns).issubset(table.schema_arrow.names):
            raise RRExportError("polar_rr_schema_invalid")
        prefix = f"{manifest.capture_id}_{manifest.execution_purpose}"
        trace_name = f"{prefix}_rr_trace.csv"
        trace_partial = target / f"{trace_name}.partial"
        files: list[dict] = []
        segments: list[dict] = []
        preview: list[dict] = []
        count = excluded = rows = contact_not_detected = 0
        previous = None
        segment = None
        txt = simple_csv = None

        def file_entry(name, kind, row_count, segment_id=None):
            path = target / name
            files.append(dict(filename=name, kind=kind, row_count=row_count, segment_id=segment_id,
                              sha256=sha256(path), size_bytes=path.stat().st_size))

        def finish_segment():
            nonlocal txt, simple_csv, segment
            if segment is None:
                return
            txt.close()
            simple_csv.close()
            for key, kind in (("txt_filename", "kubios_txt"), ("csv_filename", "rr_csv")):
                name = segment[key]
                os.replace(target / f"{name}.partial", target / name)
                file_entry(name, kind, segment["rr_count"], segment["segment_id"])
            segments.append(segment)
            segment = None
            txt = simple_csv = None

        try:
            with trace_partial.open("w", encoding="utf-8", newline="") as trace:
                writer = csv.writer(trace, lineterminator="\n")
                writer.writerow(["beat_index", "rr_ms", "segment_id", "exported", *columns[2:]])
                for batch in table.iter_batches(batch_size=4096, columns=columns):
                    for row in batch.to_pylist():
                        rows += 1
                        rr = row["rr_ms"]
                        valid = isinstance(rr, (int, float)) and math.isfinite(rr) and rr > 0
                        if valid and rr != row["rr_ticks_1024"] * 1000.0 / 1024.0:
                            raise RRExportError("polar_rr_units_mismatch")
                        boundary = previous is not None and (
                            row["gap_before"] or row["connection_epoch"] != previous["connection_epoch"]
                            or row["beat_index"] != previous["beat_index"] + 1
                        )
                        if boundary or not valid:
                            finish_segment()
                        if valid and segment is None:
                            number = len(segments) + 1
                            stem = f"{prefix}_rr_segment-{number:03d}_ms"
                            segment = dict(segment_id=number, rr_count=0, first_beat_index=row["beat_index"],
                                           last_beat_index=row["beat_index"], txt_filename=stem + ".txt",
                                           csv_filename=stem + ".csv")
                            txt = (target / f"{stem}.txt.partial").open("w", encoding="utf-8", newline="")
                            simple_csv = (target / f"{stem}.csv.partial").open("w", encoding="utf-8", newline="")
                            simple_csv.write("rr_ms\n")
                        if valid:
                            value = _number(rr)
                            txt.write(value + "\n")
                            simple_csv.write(value + "\n")
                            count += 1
                            segment["rr_count"] += 1
                            segment["last_beat_index"] = row["beat_index"]
                            if len(preview) < PREVIEW_LIMIT:
                                preview.append(dict(beat_index=row["beat_index"], rr_ms=rr, segment_id=segment["segment_id"]))
                        else:
                            value = "" if rr is None else str(rr)
                            excluded += 1
                        contact_not_detected += int(row["contact_supported"] is True and row["contact_detected"] is not True)
                        writer.writerow([row["beat_index"], value, segment["segment_id"] if valid else "",
                                         int(valid), *[row[name] for name in columns[2:]]])
                        previous = row
                finish_segment()
            if rows != entry.row_count:
                raise RRExportError("polar_artifact_checksum_failed")
            os.replace(trace_partial, target / trace_name)
            file_entry(trace_name, "trace_csv", rows)
            index = dict(
                schema_id=EXPORT_VERSION, capture_id=manifest.capture_id,
                execution_purpose=manifest.execution_purpose, units="ms", source="rr.parquet",
                source_sha256=entry.sha256, row_count=rows, rr_count=count,
                excluded_nonpositive_or_nonfinite=excluded, contact_not_detected_count=contact_not_detected,
                segment_count=len(segments), segments=segments, preview=preview, files=files,
                incomplete_reasons=list(manifest.incomplete_reasons),
                correction="none; transmitted HRS RR; no interpolation or physiological outlier removal",
                continuity="separate files at gap_before, connection_epoch changes, nonadjacent beats and invalid RR",
                kubios_import=dict(data_type="RR", units="ms", data_column=1, time_column=None,
                                   txt_header_lines=0, csv_header_lines=1, csv_separator=","),
                source_reference="https://www.kubios.com/downloads/HRV-Scientific-Users-Guide.pdf",
            )
            partial_index = target / "rr_export_manifest.json.partial"
            partial_index.write_text(json.dumps(index, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            os.replace(partial_index, index_path)
            return index
        finally:
            for handle in (txt, simple_csv):
                if handle is not None:
                    handle.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert a finalized Polar capture to raw RR milliseconds.")
    parser.add_argument("capture_directory", type=Path)
    args = parser.parse_args()
    result = export_rr_capture(args.capture_directory)
    print(json.dumps({"rr_count": result["rr_count"], "segment_count": result["segment_count"],
                      "directory": str(args.capture_directory.resolve() / "rr-export")}, indent=2))
