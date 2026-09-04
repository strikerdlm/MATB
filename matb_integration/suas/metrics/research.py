"""Deterministic reductions for the native sUAS research instruments.

Questionnaire records are deliberately reduced to analysis-safe aggregates.
Raw answers and private probe truth remain in the server-side questionnaire
artifact and are never copied into a public debrief.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import math

from matb_integration.suas.recording.records import RecordKind, SessionRecord


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _status(count: int) -> str:
    return "observed" if count else "missing"


@dataclass(frozen=True, slots=True)
class ResearchMetrics:
    """Public, descriptive research summaries with explicit missingness."""

    isa: Mapping[str, object]
    sagat: Mapping[str, object]
    nasa_tlx: Mapping[str, object]
    bedford: Mapping[str, object]
    protocol: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "isa": dict(self.isa),
            "sagat": dict(self.sagat),
            "nasa_tlx": dict(self.nasa_tlx),
            "bedford": dict(self.bedford),
            "protocol": dict(self.protocol),
        }


def derive_research_metrics(records: Iterable[SessionRecord]) -> ResearchMetrics:
    """Reduce durable questionnaire records without exposing private answers."""

    isa: list[int] = []
    sagat_rows: list[dict[str, object]] = []
    tlx_values: list[float] = []
    rtlx_values: list[float] = []
    tlx_subscales: dict[str, list[float]] = {}
    bedford: list[int] = []
    probe_started = 0
    deviations = 0

    for record in records:
        if not isinstance(record, SessionRecord):
            raise ValueError("records must contain SessionRecord values")
        payload = record.payload
        if record.kind is RecordKind.PROTOCOL_DEVIATION:
            deviations += 1
            continue
        if record.kind is not RecordKind.QUESTIONNAIRE:
            continue
        instrument = payload.get("instrument") or payload.get("scale_id")
        if payload.get("event") == "probe_started":
            probe_started += 1
            continue
        if instrument == "ISA":
            value = payload.get("rating")
            if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 10:
                isa.append(value)
        elif instrument == "SAGAT":
            level = payload.get("sa_level")
            correct = payload.get("correct")
            if (
                isinstance(level, int) and not isinstance(level, bool) and level in (1, 2, 3)
                and isinstance(correct, bool)
            ):
                sagat_rows.append({
                    "level": level,
                    "correct": correct,
                    "timed_out": payload.get("timed_out") is True,
                    "unscorable": payload.get("unscorable_reason") is not None,
                })
        elif instrument == "NASA_TLX":
            raw = payload.get("raw_tlx")
            if isinstance(raw, (int, float)) and not isinstance(raw, bool) and math.isfinite(float(raw)):
                tlx_values.append(float(raw))
            subscales = payload.get("subscales")
            if isinstance(subscales, Mapping):
                from matb_integration.suas.research.scoring import score_nasa_tlx
                try:
                    complete_score = score_nasa_tlx(subscales)
                except ValueError:
                    pass
                else:
                    rtlx_values.append(complete_score.raw_tlx * 100 / 60)
                for key, value in subscales.items():
                    if (
                        isinstance(key, str)
                        and isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        and math.isfinite(float(value))
                    ):
                        tlx_subscales.setdefault(key, []).append(float(value))
        elif instrument == "BEDFORD":
            value = payload.get("value")
            if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 10:
                bedford.append(value)

    scorable = [row for row in sagat_rows if not row["unscorable"]]
    sagat_by_level: dict[str, dict[str, object]] = {}
    for level in (1, 2, 3):
        rows = [row for row in scorable if row["level"] == level]
        correct = sum(bool(row["correct"]) for row in rows)
        sagat_by_level[str(level)] = {
            "correct": correct,
            "total": len(rows),
            "accuracy": round(correct / len(rows), 3) if rows else None,
            "status": _status(len(rows)),
        }
    sagat_correct = sum(bool(row["correct"]) for row in scorable)
    sagat_total = len(scorable)

    return ResearchMetrics(
        isa={
            "count": len(isa),
            "mean": _mean([float(value) for value in isa]),
            "min": min(isa) if isa else None,
            "max": max(isa) if isa else None,
            "status": _status(len(isa)),
        },
        sagat={
            "correct": sagat_correct,
            "total": sagat_total,
            "accuracy": round(sagat_correct / sagat_total, 3) if sagat_total else None,
            "timed_out": sum(bool(row["timed_out"]) for row in scorable),
            "unscorable": len(sagat_rows) - len(scorable),
            "by_level": sagat_by_level,
            "status": _status(sagat_total),
        },
        nasa_tlx={
            "count": len(tlx_values),
            "raw_tlx": _mean(tlx_values),
            "legacy_sum_0_60": _mean(tlx_values),
            "rtlx_0_100": _mean(rtlx_values),
            "complete_count": len(rtlx_values),
            "metric_version": "unweighted-rtlx-v2",
            "scoring": "unweighted_mean_of_six_dimensions",
            "missing_reason": None if rtlx_values else "six_valid_dimensions_required",
            "subscales": {key: _mean(values) for key, values in sorted(tlx_subscales.items())},
            "status": _status(len(tlx_values)),
        },
        bedford={
            "count": len(bedford),
            "value": _mean([float(value) for value in bedford]),
            "min": min(bedford) if bedford else None,
            "max": max(bedford) if bedford else None,
            "status": _status(len(bedford)),
        },
        protocol={
            "probes_started": probe_started,
            "sagat_answers": len(sagat_rows),
            "deviations": deviations,
            "missing_instruments": [
                name for name, count in (
                    ("ISA", len(isa)),
                    ("SAGAT", sagat_total),
                    ("NASA_TLX", len(tlx_values)),
                    ("BEDFORD", len(bedford)),
                ) if count == 0
            ],
            "status": "valid_with_deviation" if deviations else "observed",
        },
    )


__all__ = ["ResearchMetrics", "derive_research_metrics"]
