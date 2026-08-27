"""Streaming runtime recorder and immutable scientific bundle sealer."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping

import pyarrow as pa
import pyarrow.csv as arrow_csv
import pyarrow.parquet as pq

from matb_integration.recording.artifacts import write_json_artifact

from .bundle import pack_bundle, write_checksums
from .quality import assess_timing_quality
from .sampling import DeadlineSampler
from .schema import BUNDLE_SCHEMA_VERSION, SAMPLE_FIELDS, TRIAL_FIELDS, FieldSpec, data_dictionary
from .summary import summarize_rows


def _column_names(fields: tuple[FieldSpec, ...]) -> list[str]:
    return [field.name for field in fields]


def _default_value(field: FieldSpec) -> Any:
    if field.nullable:
        return None
    if field.dtype == "bool":
        return False
    if field.dtype == "int64":
        return 0
    if field.dtype == "float64":
        return 0.0
    if field.dtype == "json":
        return "{}"
    return ""


def _csv_value(field: FieldSpec, value: Any) -> Any:
    if value is None:
        return ""
    if field.dtype == "json":
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return value


def _arrow_type(field: FieldSpec) -> pa.DataType:
    return {
        "bool": pa.bool_(),
        "int64": pa.int64(),
        "float64": pa.float64(),
        "json": pa.string(),
        "string": pa.string(),
    }[field.dtype]


class ResearchRecorder:
    def __init__(
        self,
        *,
        session_id: str,
        run_dir: Path,
        sample_hz: float,
        start_monotonic_ns: int,
        start_utc_ns: int,
        manifest: Mapping[str, Any] | None = None,
        score_config: Mapping[str, Any] | None = None,
        flush_interval_sec: float = 1.0,
        fsync_interval_sec: float = 5.0,
    ) -> None:
        self.session_id = session_id
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.sample_hz = float(sample_hz)
        self.start_monotonic_ns = int(start_monotonic_ns)
        self.start_utc_ns = int(start_utc_ns)
        self.sampler = DeadlineSampler(sample_hz=sample_hz, start_monotonic_ns=start_monotonic_ns)
        self._last_observed_ns: int | None = None
        self._intervals_ms: list[float] = []
        self._lateness_ms: list[float] = []
        self._missed_ticks = 0
        self._non_monotonic = 0
        self._sample_count = 0
        self._trial_count = 0
        self._sealed = False
        self.score_config = dict(score_config or {})
        if flush_interval_sec <= 0 or fsync_interval_sec <= 0:
            raise ValueError("flush and fsync intervals must be positive")
        self.flush_interval_ns = int(flush_interval_sec * 1_000_000_000)
        self.fsync_interval_ns = int(fsync_interval_sec * 1_000_000_000)
        self._last_flush_ns = self.start_monotonic_ns
        self._last_fsync_ns = self.start_monotonic_ns

        self._sample_stream = (self.run_dir / "samples.csv").open("w", encoding="utf-8", newline="")
        self._trial_stream = (self.run_dir / "trials.csv").open("w", encoding="utf-8", newline="")
        self._sample_writer = csv.DictWriter(self._sample_stream, fieldnames=_column_names(SAMPLE_FIELDS))
        self._trial_writer = csv.DictWriter(self._trial_stream, fieldnames=_column_names(TRIAL_FIELDS))
        self._sample_writer.writeheader()
        self._trial_writer.writeheader()

        manifest_payload = {
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "session_id": session_id,
            "sample_hz": self.sample_hz,
            "start_monotonic_ns": self.start_monotonic_ns,
            "start_utc_ns": self.start_utc_ns,
            "score_configuration": self.score_config,
            "durability": {
                "flush_interval_sec": flush_interval_sec,
                "fsync_interval_sec": fsync_interval_sec,
                "trials_fsync": "immediate",
            },
            "source": dict(manifest or {}),
        }
        write_json_artifact(self.run_dir / "manifest.json", manifest_payload)
        write_json_artifact(self.run_dir / "data_dictionary.json", data_dictionary())

    def maybe_sample(
        self,
        *,
        monotonic_ns: int,
        scenario_time_s: float,
        scenario_paused: bool,
        event_sequence: int,
        state: Mapping[str, Any],
    ) -> bool:
        if self._sealed:
            raise RuntimeError("research recorder is sealed")
        if self._last_observed_ns is not None and monotonic_ns <= self._last_observed_ns:
            self._non_monotonic += 1
        timing = self.sampler.observe(monotonic_ns)
        if timing is None:
            return False
        row = {field.name: _default_value(field) for field in SAMPLE_FIELDS}
        row.update({
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "session_id": self.session_id,
            "sample_index": timing.sample_index,
            "scheduled_monotonic_ns": timing.scheduled_monotonic_ns,
            "observed_monotonic_ns": timing.observed_monotonic_ns,
            "utc_ns": self.start_utc_ns + (timing.observed_monotonic_ns - self.start_monotonic_ns),
            "scenario_time_s": scenario_time_s,
            "interval_ms": (
                None
                if self._last_observed_ns is None
                else (timing.observed_monotonic_ns - self._last_observed_ns) / 1_000_000
            ),
            "lateness_ms": timing.lateness_ms,
            "missed_ticks": timing.missed_ticks,
            "scenario_paused": scenario_paused,
            "event_sequence": event_sequence,
            "sysmon_pending_ids_json": [],
            "communications_pending_ids_json": [],
            "pump_states_json": {},
        })
        unknown = set(state) - set(row)
        if unknown:
            raise ValueError(f"unknown sample fields: {sorted(unknown)}")
        row.update(state)
        for field in SAMPLE_FIELDS:
            row[field.name] = _csv_value(field, row[field.name])
        self._sample_writer.writerow(row)
        self._sync_sample_stream(timing.observed_monotonic_ns)
        if self._last_observed_ns is not None:
            self._intervals_ms.append((timing.observed_monotonic_ns - self._last_observed_ns) / 1_000_000)
        self._last_observed_ns = timing.observed_monotonic_ns
        self._lateness_ms.append(timing.lateness_ms)
        self._missed_ticks += timing.missed_ticks
        self._sample_count += 1
        return True

    def _sync_sample_stream(self, observed_monotonic_ns: int) -> None:
        should_fsync = observed_monotonic_ns - self._last_fsync_ns >= self.fsync_interval_ns
        should_flush = observed_monotonic_ns - self._last_flush_ns >= self.flush_interval_ns
        if should_flush or should_fsync:
            self._sample_stream.flush()
            self._last_flush_ns = observed_monotonic_ns
        if should_fsync:
            os.fsync(self._sample_stream.fileno())
            self._last_fsync_ns = observed_monotonic_ns

    def record_trial(self, values: Mapping[str, Any]) -> None:
        if self._sealed:
            raise RuntimeError("research recorder is sealed")
        row = {field.name: _default_value(field) for field in TRIAL_FIELDS}
        row.update({"schema_version": BUNDLE_SCHEMA_VERSION, "session_id": self.session_id})
        unknown = set(values) - set(row)
        if unknown:
            raise ValueError(f"unknown trial fields: {sorted(unknown)}")
        row.update(values)
        for field in TRIAL_FIELDS:
            row[field.name] = _csv_value(field, row[field.name])
        self._trial_writer.writerow(row)
        self._trial_stream.flush()
        os.fsync(self._trial_stream.fileno())
        self._trial_count += 1

    def _close_streams(self) -> None:
        for stream in (self._sample_stream, self._trial_stream):
            if not stream.closed:
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()

    def _write_parquet(self) -> None:
        column_types = {field.name: _arrow_type(field) for field in SAMPLE_FIELDS}
        table = arrow_csv.read_csv(
            self.run_dir / "samples.csv",
            convert_options=arrow_csv.ConvertOptions(column_types=column_types, strings_can_be_null=True),
        )
        pq.write_table(table, self.run_dir / "samples.parquet", compression="zstd")

    def _read_rows(self, filename: str) -> list[dict[str, str]]:
        with (self.run_dir / filename).open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    def seal(
        self,
        *,
        events_csv: Path,
        status: str = "complete",
        reason: str | None = None,
    ) -> Path:
        if self._sealed:
            raise RuntimeError("research recorder is sealed")
        if status not in {"complete", "partial"}:
            raise ValueError("status must be complete or partial")
        self._close_streams()
        shutil.copyfile(events_csv, self.run_dir / "events.csv")
        self._write_parquet()
        quality = assess_timing_quality(
            sample_hz=self.sample_hz,
            observed_intervals_ms=self._intervals_ms,
            lateness_ms=self._lateness_ms,
            missed_ticks=self._missed_ticks,
            observed_samples=self._sample_count,
            non_monotonic_timestamps=self._non_monotonic,
        )
        write_json_artifact(self.run_dir / "quality.json", quality)
        summary = summarize_rows(
            samples=self._read_rows("samples.csv"),
            trials=self._read_rows("trials.csv"),
            score_config=self.score_config,
        )
        summary.update({
            "status": status,
            "session_id": self.session_id,
            "sample_count": self._sample_count,
            "trial_count": self._trial_count,
            "timing_quality_status": quality["status"],
        })
        write_json_artifact(self.run_dir / "summary.json", summary)
        if status == "partial":
            write_json_artifact(self.run_dir / "partial-run.json", {
                "reason": reason or "unspecified",
                "status": "partial",
            })
        write_checksums(self.run_dir)
        destination = pack_bundle(self.run_dir)
        self._sealed = True
        return destination


__all__ = ["ResearchRecorder"]
