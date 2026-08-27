"""Immutable, bilingual research bundles for Polar-synchronized MATB sessions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from enum import Enum
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from .hrv import HRV_ANALYSIS_VERSION
from .durability import (
    fsync_directory as _fsync_directory,
    make_private_directory,
    open_private_exclusive,
)


BUNDLE_SCHEMA_VERSION = "matb-classic-bundle-v2"
METRICS_SCHEMA_VERSION = "matb-classic-metrics-v1"
RR_SCHEMA_VERSION = "polar-h10-rr-v2"

_OUTPUT_ORDER = (
    "session.json",
    "session-metrics.csv",
    "rr-intervals.csv",
    "rr-intervals.jsonl",
    "hrv-psd.csv",
    "openmatb-session.csv",
    "openmatb-events.jsonl",
    "clock-anchors.json",
    "report.en.md",
    "report.es.md",
    "manifest.json",
    "checksums.sha256",
)

_ARTIFACT_KINDS = {
    "session.json": "session",
    "session-metrics.csv": "metrics",
    "rr-intervals.csv": "rr_csv",
    "rr-intervals.jsonl": "rr_jsonl",
    "hrv-psd.csv": "hrv_psd",
    "openmatb-session.csv": "openmatb_csv",
    "openmatb-events.jsonl": "openmatb_events",
    "clock-anchors.json": "clock_anchors",
    "report.en.md": "report_en",
    "report.es.md": "report_es",
    "manifest.json": "manifest",
    "checksums.sha256": "checksums",
}

_REACTIVITY_METRICS = (
    ("time_domain", "mean_hr_bpm"),
    ("time_domain", "rmssd_ms"),
    ("time_domain", "ln_rmssd"),
    ("time_domain", "sdnn_ms"),
    ("frequency_domain", "lf_power_ms2"),
    ("frequency_domain", "hf_power_ms2"),
    ("frequency_domain", "lf_hf_ratio"),
)

_RR_COLUMNS = (
    "session_id",
    "phase",
    "segment_id",
    "beat_index",
    "notification_index",
    "rr_index_in_notification",
    "heart_rate_bpm",
    "rr_ticks_1024",
    "rr_ms",
    "corrected_rr_ms",
    "is_artifact",
    "notification_received_monotonic_ns",
    "estimated_beat_monotonic_ns",
    "estimated_beat_utc_ns",
    "timestamp_source",
)


class BundleImmutableError(RuntimeError):
    """Raised when bundle finalization would replace an existing artifact."""


@dataclass(frozen=True, slots=True)
class BundleArtifact:
    kind: str
    relative_path: str
    sha256: str
    size_bytes: int


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("bundle_json_non_finite_float")
        return value
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        converted: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("bundle_json_mapping_keys_must_be_strings")
            converted[key] = _json_safe(item)
        return converted
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    raise TypeError(f"bundle_json_unsupported_type:{type(value).__name__}")


def _json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    safe = _json_safe(value)
    if pretty:
        text = json.dumps(
            safe,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
    else:
        text = json.dumps(
            safe,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    return (text + "\n").encode("utf-8")


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(_json_bytes(row) for row in rows)


def _stringify_nanoseconds(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: (
                str(item)
                if key.endswith("_ns") and isinstance(item, int) and not isinstance(item, bool)
                else _stringify_nanoseconds(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_stringify_nanoseconds(item) for item in value]
    return value


def _csv_bytes(fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=list(fieldnames),
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_cell(row.get(key)) for key in fieldnames})
    return stream.getvalue().encode("utf-8")


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        return _json_bytes(value).decode("utf-8").strip()
    return value


def _metric_value(
    phase: Mapping[str, Any] | None,
    domain: str,
    metric: str,
) -> float | int | None:
    if not isinstance(phase, Mapping):
        return None
    domain_result = phase.get(domain)
    if not isinstance(domain_result, Mapping) or domain_result.get("status") != "ok":
        return None
    metrics = domain_result.get("metrics")
    if not isinstance(metrics, Mapping):
        return None
    value = metrics.get(metric)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def compute_phase_reactivity(
    phase_results: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, float | int | None]]:
    """Return directional, descriptive changes between adjacent session phases.

    Values are later phase minus earlier phase.  Missing or gated HRV values stay
    null; this function does not impute them or make clinical interpretations.
    """

    transitions = {
        "baseline_to_task": ("baseline", "task"),
        "task_to_recovery": ("task", "recovery"),
    }
    result: dict[str, dict[str, float | int | None]] = {}
    for transition, (before_name, after_name) in transitions.items():
        before = phase_results.get(before_name)
        after = phase_results.get(after_name)
        changes: dict[str, float | int | None] = {}
        for domain, metric in _REACTIVITY_METRICS:
            before_value = _metric_value(before, domain, metric)
            after_value = _metric_value(after, domain, metric)
            changes[metric] = (
                None
                if before_value is None or after_value is None
                else after_value - before_value
            )
        result[transition] = changes
    return result


def _flatten_scalars(value: Any, prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    if isinstance(value, Mapping):
        flattened: list[tuple[tuple[str, ...], Any]] = []
        for key in sorted(value):
            if not isinstance(key, str):
                raise TypeError("metric_mapping_keys_must_be_strings")
            flattened.extend(_flatten_scalars(value[key], (*prefix, key)))
        return flattened
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        flattened: list[tuple[tuple[str, ...], Any]] = []
        for index, item in enumerate(value):
            flattened.extend(_flatten_scalars(item, (*prefix, str(index))))
        return flattened
    return [(prefix, value)]


def _metric_rows(
    matb_metrics: Mapping[str, Any],
    phase_results: Mapping[str, Mapping[str, Any]],
    reactivity: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path, value in _flatten_scalars(matb_metrics):
        if not path:
            continue
        rows.append(
            {
                "scope": "matb",
                "phase": "task",
                "domain": path[0],
                "metric": ".".join(path[1:]) if len(path) > 1 else path[0],
                "value": value,
                "status": "ok" if value is not None else "unavailable",
                "reason_code": "",
            }
        )
    for phase_name in ("baseline", "task", "recovery"):
        phase = phase_results.get(phase_name, {})
        quality = phase.get("quality", {}) if isinstance(phase, Mapping) else {}
        for path, value in _flatten_scalars(quality):
            if path:
                rows.append(
                    {
                        "scope": "physiology",
                        "phase": phase_name,
                        "domain": "quality",
                        "metric": ".".join(path),
                        "value": value,
                        "status": "ok",
                        "reason_code": "",
                    }
                )
        for domain in ("time_domain", "frequency_domain"):
            domain_result = phase.get(domain, {}) if isinstance(phase, Mapping) else {}
            if not isinstance(domain_result, Mapping):
                continue
            status = str(domain_result.get("status", "unavailable"))
            reason_codes = domain_result.get("reason_codes")
            reason = (
                ";".join(str(code) for code in reason_codes)
                if isinstance(reason_codes, Sequence)
                and not isinstance(reason_codes, (str, bytes, bytearray))
                else str(domain_result.get("reason_code") or "")
            )
            metrics = domain_result.get("metrics", {})
            metric_added = False
            for path, value in _flatten_scalars(metrics):
                if path:
                    metric_added = True
                    rows.append(
                        {
                            "scope": "physiology",
                            "phase": phase_name,
                            "domain": domain,
                            "metric": ".".join(path),
                            "value": value,
                            "status": status,
                            "reason_code": reason,
                        }
                    )
            if not metric_added and status != "ok":
                rows.append(
                    {
                        "scope": "physiology",
                        "phase": phase_name,
                        "domain": domain,
                        "metric": "_status",
                        "value": None,
                        "status": status,
                        "reason_code": reason,
                    }
                )
    for transition, metrics in reactivity.items():
        for metric in sorted(metrics):
            value = metrics[metric]
            rows.append(
                {
                    "scope": "physiology",
                    "phase": transition,
                    "domain": "reactivity",
                    "metric": metric,
                    "value": value,
                    "status": "ok" if value is not None else "unavailable",
                    "reason_code": "",
                }
            )
    return rows


def _psd_rows(phase_results: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for phase_name in ("baseline", "task", "recovery"):
        phase = phase_results.get(phase_name, {})
        frequency = phase.get("frequency_domain", {}) if isinstance(phase, Mapping) else {}
        if not isinstance(frequency, Mapping):
            continue
        psd = frequency.get("psd", [])
        if not isinstance(psd, Sequence) or isinstance(psd, (str, bytes, bytearray)):
            continue
        for point in psd:
            if isinstance(point, Mapping):
                rows.append(
                    {
                        "phase": phase_name,
                        "frequency_hz": point.get("frequency_hz"),
                        "power_ms2_per_hz": point.get("power_ms2_per_hz"),
                    }
                )
    return rows


def _escape_markdown(value: Any) -> str:
    if value is None:
        return "—"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _report(
    *,
    language: str,
    session: Mapping[str, Any],
    matb_metrics: Mapping[str, Any],
    phase_results: Mapping[str, Mapping[str, Any]],
    reactivity: Mapping[str, Mapping[str, Any]],
) -> bytes:
    spanish = language == "es"
    labels = {
        "title": "Informe de sesión MATB + Polar H10" if spanish else "MATB + Polar H10 Session Report",
        "warning": (
            "Solo para uso en investigación. Este informe contiene métricas descriptivas y no constituye diagnóstico ni consejo médico."
            if spanish
            else "Research use only. This report contains descriptive metrics and is not a diagnosis or medical advice."
        ),
        "session": "Sesión" if spanish else "Session",
        "task": "Resultados MATB" if spanish else "MATB results",
        "physiology": "Fisiología y VFC" if spanish else "Physiology and HRV",
        "complete_hrv": (
            "Métricas completas de VFC" if spanish else "Complete HRV metrics"
        ),
        "reactivity": "Cambios descriptivos" if spanish else "Descriptive changes",
        "field": "Campo" if spanish else "Field",
        "value": "Valor" if spanish else "Value",
        "phase": "Fase" if spanish else "Phase",
        "domain": "Dominio" if spanish else "Domain",
        "metric": "Métrica" if spanish else "Metric",
        "status": "Estado" if spanish else "Status",
        "reasons": "Razones" if spanish else "Reasons",
        "quality": "Calidad" if spanish else "Quality",
        "direction": (
            "Los cambios son posteriores menos anteriores; no implican una interpretación clínica."
            if spanish
            else "Changes are later phase minus earlier phase; they do not imply clinical interpretation."
        ),
    }
    lines = [
        f"# {labels['title']}",
        "",
        f"> **{labels['warning']}**",
        "",
        f"## {labels['session']}",
        "",
        f"| {labels['field']} | {labels['value']} |",
        "|---|---|",
    ]
    for path, value in _flatten_scalars(session):
        if path:
            lines.append(
                f"| {_escape_markdown('.'.join(path))} | {_escape_markdown(value)} |"
            )
    lines.extend(
        [
            "",
            f"## {labels['task']}",
            "",
            f"| {labels['field']} | {labels['value']} |",
            "|---|---|",
        ]
    )
    for path, value in _flatten_scalars(matb_metrics):
        if path:
            lines.append(f"| {_escape_markdown('.'.join(path))} | {_escape_markdown(value)} |")
    lines.extend(
        [
            "",
            f"## {labels['physiology']}",
            "",
            f"| {labels['phase']} | {labels['quality']} | RMSSD (ms) | SDNN (ms) | Mean HR (bpm) | LF/HF | Gating reasons |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for phase_name in ("baseline", "task", "recovery"):
        phase = phase_results.get(phase_name, {})
        quality = phase.get("quality", {}) if isinstance(phase, Mapping) else {}
        label = quality.get("label") if isinstance(quality, Mapping) else None
        gating_reasons: list[str] = []
        for domain in ("time_domain", "frequency_domain"):
            result = phase.get(domain, {}) if isinstance(phase, Mapping) else {}
            if not isinstance(result, Mapping) or result.get("status") == "ok":
                continue
            codes = result.get("reason_codes")
            if isinstance(codes, Sequence) and not isinstance(
                codes, (str, bytes, bytearray)
            ):
                gating_reasons.extend(str(code) for code in codes)
            elif result.get("reason_code"):
                gating_reasons.append(str(result["reason_code"]))
        values = [
            phase_name,
            label,
            _metric_value(phase, "time_domain", "rmssd_ms"),
            _metric_value(phase, "time_domain", "sdnn_ms"),
            _metric_value(phase, "time_domain", "mean_hr_bpm"),
            _metric_value(phase, "frequency_domain", "lf_hf_ratio"),
            "; ".join(gating_reasons) if gating_reasons else None,
        ]
        lines.append("| " + " | ".join(_escape_markdown(value) for value in values) + " |")
    lines.extend(
        [
            "",
            f"## {labels['complete_hrv']}",
            "",
            f"| {labels['phase']} | {labels['domain']} | {labels['metric']} | {labels['value']} | {labels['status']} | {labels['reasons']} |",
            "|---|---|---|---:|---|---|",
        ]
    )
    excluded_phase_fields = {
        "quality",
        "valid_mask",
        "corrected_rr_ms",
        "time_domain",
        "frequency_domain",
    }
    for phase_name in ("baseline", "task", "recovery"):
        phase = phase_results.get(phase_name, {})
        if not isinstance(phase, Mapping):
            continue
        summary = {
            key: value
            for key, value in phase.items()
            if key not in excluded_phase_fields
        }
        for path, value in _flatten_scalars(summary):
            if path:
                lines.append(
                    "| "
                    + " | ".join(
                        _escape_markdown(item)
                        for item in (
                            phase_name,
                            "phase_summary",
                            ".".join(path),
                            value,
                            "ok",
                            None,
                        )
                    )
                    + " |"
                )
        quality = phase.get("quality", {})
        if isinstance(quality, Mapping):
            quality_reasons = quality.get("reason_codes", [])
            reason_text = (
                ";".join(str(code) for code in quality_reasons)
                if isinstance(quality_reasons, Sequence)
                and not isinstance(quality_reasons, (str, bytes, bytearray))
                else None
            )
            for path, value in _flatten_scalars(quality):
                if path and path[0] != "reason_codes":
                    lines.append(
                        "| "
                        + " | ".join(
                            _escape_markdown(item)
                            for item in (
                                phase_name,
                                "quality",
                                ".".join(path),
                                value,
                                "ok",
                                reason_text,
                            )
                        )
                        + " |"
                    )
        for domain in ("time_domain", "frequency_domain"):
            result = phase.get(domain, {})
            if not isinstance(result, Mapping):
                continue
            status = str(result.get("status", "unavailable"))
            codes = result.get("reason_codes")
            reason = (
                ";".join(str(code) for code in codes)
                if isinstance(codes, Sequence)
                and not isinstance(codes, (str, bytes, bytearray))
                else str(result.get("reason_code") or "")
            )
            metrics = result.get("metrics")
            metric_rows = list(_flatten_scalars(metrics))
            if not any(path for path, _value in metric_rows):
                metric_rows = [(('_status',), None)]
            for path, value in metric_rows:
                if path:
                    lines.append(
                        "| "
                        + " | ".join(
                            _escape_markdown(item)
                            for item in (
                                phase_name,
                                domain,
                                ".".join(path),
                                value,
                                status,
                                reason or None,
                            )
                        )
                        + " |"
                    )
    lines.extend(
        [
            "",
            f"## {labels['reactivity']}",
            "",
            labels["direction"],
            "",
            f"| {labels['phase']} | {labels['field']} | {labels['value']} |",
            "|---|---|---:|",
        ]
    )
    for transition, metrics in reactivity.items():
        for metric, value in metrics.items():
            lines.append(
                f"| {_escape_markdown(transition)} | {_escape_markdown(metric)} | {_escape_markdown(value)} |"
            )
    lines.extend(
        [
            "",
            f"HRV analysis: `{HRV_ANALYSIS_VERSION}`. Bundle schema: `{BUNDLE_SCHEMA_VERSION}`.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def _write_exclusive(path: Path, payload: bytes) -> None:
    try:
        with open_private_exclusive(path, binary=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise BundleImmutableError(f"artifact_immutable:{path.name}") from exc


def _inventory(run_dir: Path) -> tuple[BundleArtifact, ...]:
    inventory: list[BundleArtifact] = []
    for relative in _OUTPUT_ORDER:
        path = run_dir / relative
        data = path.read_bytes()
        inventory.append(
            BundleArtifact(
                kind=_ARTIFACT_KINDS[relative],
                relative_path=relative,
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=len(data),
            )
        )
    return tuple(inventory)


def discard_incomplete_bundle(run_dir: Path) -> bool:
    """Remove only an uncommitted bundle so journal recovery can republish it."""

    destination = Path(run_dir)
    if (destination / "checksums.sha256").is_file():
        return False
    changed = False
    for relative in _OUTPUT_ORDER:
        target = destination / relative
        if target.exists() or target.is_symlink():
            target.unlink(missing_ok=True)
            changed = True
    if destination.is_dir():
        for staging in destination.glob(".bundle-staging-*"):
            if staging.is_symlink():
                staging.unlink(missing_ok=True)
            elif staging.is_dir():
                shutil.rmtree(staging)
            else:
                staging.unlink(missing_ok=True)
            changed = True
    if changed:
        _fsync_directory(destination)
    return changed


def load_complete_bundle(
    run_dir: Path,
) -> tuple[tuple[BundleArtifact, ...], dict[str, Any]] | None:
    """Verify the checksums commit marker and load a published session document."""

    destination = Path(run_dir)
    marker = destination / "checksums.sha256"
    if not marker.is_file():
        return None
    if any(not (destination / relative).is_file() for relative in _OUTPUT_ORDER):
        raise BundleImmutableError("bundle_commit_incomplete")
    expected_hashes: dict[str, str] = {}
    try:
        for line in marker.read_text(encoding="utf-8").splitlines():
            digest, relative = line.split("  ", 1)
            if relative in expected_hashes or relative not in _OUTPUT_ORDER:
                raise ValueError
            expected_hashes[relative] = digest
        required = set(_OUTPUT_ORDER) - {"checksums.sha256"}
        if set(expected_hashes) != required:
            raise ValueError
        for relative, expected in expected_hashes.items():
            actual = hashlib.sha256((destination / relative).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError
        document = json.loads((destination / "session.json").read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise BundleImmutableError("bundle_commit_invalid") from exc
    return _inventory(destination), document


def build_session_bundle(
    run_dir: Path,
    *,
    session: Mapping[str, Any],
    matb_metrics: Mapping[str, Any],
    phase_results: Mapping[str, Mapping[str, Any]],
    rr_records: Sequence[Mapping[str, Any]],
    clock_anchors: Sequence[Mapping[str, Any]],
    openmatb_csv: Path,
    synchronized_events: Path | None = None,
) -> tuple[BundleArtifact, ...]:
    """Finalize one deterministic, write-once classic-session artifact bundle."""

    destination = Path(run_dir)
    source_csv = Path(openmatb_csv)
    source_events = Path(synchronized_events) if synchronized_events is not None else None
    if not source_csv.is_file():
        raise FileNotFoundError(source_csv)
    if source_events is not None and not source_events.is_file():
        raise FileNotFoundError(source_events)
    destination_existed = destination.exists()
    make_private_directory(destination)
    if not destination_existed:
        _fsync_directory(destination.parent)
    for relative in _OUTPUT_ORDER:
        if (destination / relative).exists():
            raise BundleImmutableError(f"artifact_immutable:{relative}")

    reactivity = compute_phase_reactivity(phase_results)
    metric_rows = _metric_rows(matb_metrics, phase_results, reactivity)
    rr_fields = (*_RR_COLUMNS, *sorted(set().union(*(row.keys() for row in rr_records)) - set(_RR_COLUMNS)))
    psd_rows = _psd_rows(phase_results)
    session_document = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "session": session,
        "matb_metrics": matb_metrics,
        "phase_results": phase_results,
        "reactivity": reactivity,
        "contracts": {
            "metrics": METRICS_SCHEMA_VERSION,
            "rr": RR_SCHEMA_VERSION,
            "hrv_analysis": HRV_ANALYSIS_VERSION,
            "nanoseconds": "decimal_string_v1",
        },
    }
    payloads: dict[str, bytes] = {
        "session.json": _json_bytes(session_document, pretty=True),
        "session-metrics.csv": _csv_bytes(
            ("scope", "phase", "domain", "metric", "value", "status", "reason_code"),
            metric_rows,
        ),
        "rr-intervals.csv": _csv_bytes(rr_fields, rr_records),
        "rr-intervals.jsonl": _jsonl_bytes(
            [_stringify_nanoseconds(row) for row in rr_records]
        ),
        "hrv-psd.csv": _csv_bytes(
            ("phase", "frequency_hz", "power_ms2_per_hz"),
            psd_rows,
        ),
        "openmatb-session.csv": source_csv.read_bytes(),
        "openmatb-events.jsonl": source_events.read_bytes() if source_events else b"",
        "clock-anchors.json": _json_bytes(
            {
                "schema_version": "host-clock-anchors-v1",
                "nanosecond_encoding": "decimal_string",
                "anchors": _stringify_nanoseconds(clock_anchors),
            },
            pretty=True,
        ),
        "report.en.md": _report(
            language="en",
            session=session,
            matb_metrics=matb_metrics,
            phase_results=phase_results,
            reactivity=reactivity,
        ),
        "report.es.md": _report(
            language="es",
            session=session,
            matb_metrics=matb_metrics,
            phase_results=phase_results,
            reactivity=reactivity,
        ),
    }
    manifest_entries = [
        {
            "kind": _ARTIFACT_KINDS[relative],
            "relative_path": relative,
            "sha256": hashlib.sha256(payloads[relative]).hexdigest(),
            "size_bytes": len(payloads[relative]),
        }
        for relative in _OUTPUT_ORDER
        if relative not in {"manifest.json", "checksums.sha256"}
    ]
    payloads["manifest.json"] = _json_bytes(
        {
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "session_id": session.get("session_id"),
            "provenance": session.get("provenance", {}),
            "contracts": {
                "metrics": METRICS_SCHEMA_VERSION,
                "rr": RR_SCHEMA_VERSION,
                "hrv_analysis": HRV_ANALYSIS_VERSION,
                "nanoseconds": "decimal_string_v1",
            },
            "artifacts": manifest_entries,
        },
        pretty=True,
    )
    checksum_names = sorted(relative for relative in payloads)
    payloads["checksums.sha256"] = (
        "".join(
            f"{hashlib.sha256(payloads[relative]).hexdigest()}  {relative}\n"
            for relative in checksum_names
        )
    ).encode("utf-8")

    staging = Path(tempfile.mkdtemp(prefix=".bundle-staging-", dir=destination))
    _fsync_directory(destination)
    published: list[Path] = []
    try:
        for relative in _OUTPUT_ORDER:
            _write_exclusive(staging / relative, payloads[relative])
        _fsync_directory(staging)
        for relative in _OUTPUT_ORDER:
            target = destination / relative
            os.replace(staging / relative, target)
            published.append(target)
        # checksums.sha256 is last in _OUTPUT_ORDER and is the commit marker.
        _fsync_directory(destination)
    except BaseException:
        # All targets were proven absent above, so every published path belongs
        # to this failed transaction and is safe to roll back.
        for target in reversed(published):
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            _fsync_directory(destination)
        except OSError:
            # Preserve the original publication error. The absence of the
            # checksum commit marker still makes this bundle incomplete.
            pass
        shutil.rmtree(staging, ignore_errors=True)
        raise
    else:
        shutil.rmtree(staging, ignore_errors=True)
    return _inventory(destination)


__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "BundleArtifact",
    "BundleImmutableError",
    "build_session_bundle",
    "compute_phase_reactivity",
    "discard_incomplete_bundle",
    "load_complete_bundle",
]
