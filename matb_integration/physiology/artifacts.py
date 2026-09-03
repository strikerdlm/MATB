"""Loss-visible Parquet artifact writing for Polar captures."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

from .contracts import PolarArtifactEntryV1, PolarArtifactManifestV1


RR_SCHEMA_ID = "matb.polar.rr.v1"
ECG_SCHEMA_ID = "matb.polar.ecg.v1"
ACC_SCHEMA_ID = "matb.polar.acc.v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ParquetCaptureWriter:
    """Append packet batches to bounded, explicitly partial capture files."""

    def __init__(self, root: Path, capture_id: str) -> None:
        if not capture_id or any(character not in "0123456789abcdef-" for character in capture_id.lower()):
            raise ValueError("capture_id is not path-safe")
        self.base_root = root.expanduser().resolve()
        self.capture_root = (self.base_root / capture_id).resolve()
        if self.capture_root.parent != self.base_root:
            raise ValueError("capture path escapes physiology root")
        self.capture_root.mkdir(parents=True, exist_ok=False)
        self._writers: dict[str, Any] = {}
        self._schemas: dict[str, Any] = {}
        self._rows = {"rr": 0, "ecg": 0, "acc": 0}
        self._closed = False
        self._open()

    def _open(self) -> None:
        import pyarrow as pa
        import pyarrow.parquet as pq

        schemas = {
            "rr": pa.schema([
                ("notification_index", pa.int64()), ("beat_index", pa.int64()),
                ("received_monotonic_ns", pa.int64()), ("received_utc_ns", pa.int64()),
                ("beat_monotonic_ns", pa.int64()), ("rr_ticks_1024", pa.int32()),
                ("rr_ms", pa.float64()), ("heart_rate_bpm", pa.int32()),
                ("contact_supported", pa.bool_()), ("contact_detected", pa.bool_()),
                ("gap_before", pa.bool_()), ("connection_epoch", pa.int32()),
            ]),
            "ecg": pa.schema([
                ("packet_index", pa.int64()), ("sample_index", pa.int64()),
                ("sensor_timestamp_ns", pa.int64()),
                ("reconstructed_monotonic_ns", pa.int64()),
                ("reconstructed_utc_ns", pa.int64()),
                ("received_monotonic_ns", pa.int64()), ("received_utc_ns", pa.int64()),
                ("ecg_uv", pa.int32()), ("connection_epoch", pa.int32()),
            ]),
            "acc": pa.schema([
                ("packet_index", pa.int64()), ("sample_index", pa.int64()),
                ("sensor_timestamp_ns", pa.int64()),
                ("reconstructed_monotonic_ns", pa.int64()),
                ("reconstructed_utc_ns", pa.int64()),
                ("received_monotonic_ns", pa.int64()), ("received_utc_ns", pa.int64()),
                ("x_mg", pa.int32()), ("y_mg", pa.int32()), ("z_mg", pa.int32()),
                ("sample_rate_hz", pa.int32()), ("range_g", pa.int32()),
                ("connection_epoch", pa.int32()),
            ]),
        }
        for stream, schema in schemas.items():
            self._schemas[stream] = schema
            self._writers[stream] = pq.ParquetWriter(
                self.capture_root / f"{stream}.parquet.partial",
                schema,
                compression="zstd",
                use_dictionary=False,
            )

    def write_rows(self, stream: str, rows: Iterable[dict[str, Any]]) -> None:
        if self._closed:
            raise RuntimeError("capture writer is closed")
        if stream not in self._writers:
            raise ValueError(f"unknown physiology stream: {stream}")
        batch = list(rows)
        if not batch:
            return
        import pyarrow as pa

        table = pa.Table.from_pylist(batch, schema=self._schemas[stream])
        self._writers[stream].write_table(table)
        self._rows[stream] += len(batch)

    def abort(self) -> None:
        """Close handles but retain every .partial artifact for recovery."""

        if self._closed:
            return
        for writer in self._writers.values():
            writer.close()
        self._closed = True

    def finalize(self, manifest: PolarArtifactManifestV1) -> PolarArtifactManifestV1:
        if self._closed:
            raise RuntimeError("capture writer is already closed")
        for writer in self._writers.values():
            writer.close()
        self._closed = True
        entries: list[PolarArtifactEntryV1] = []
        schema_ids = {"rr": RR_SCHEMA_ID, "ecg": ECG_SCHEMA_ID, "acc": ACC_SCHEMA_ID}
        for stream in ("rr", "ecg", "acc"):
            partial = self.capture_root / f"{stream}.parquet.partial"
            target = self.capture_root / f"{stream}.parquet"
            os.replace(partial, target)
            entries.append(PolarArtifactEntryV1(
                relative_path=target.name,
                schema_id=schema_ids[stream],
                row_count=self._rows[stream],
                size_bytes=target.stat().st_size,
                sha256=_sha256(target),
            ))
        complete = manifest.model_copy(update={"artifacts": tuple(entries)})
        manifest_path = self.capture_root / "manifest.json"
        partial_manifest_path = self.capture_root / "manifest.json.partial"
        partial_manifest_path.write_text(
            json.dumps(complete.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(partial_manifest_path, manifest_path)
        return complete

    @staticmethod
    def partial_files(root: Path) -> tuple[Path, ...]:
        resolved = root.expanduser().resolve()
        return tuple(sorted(resolved.glob("*/**/*.partial"))) if resolved.exists() else ()
