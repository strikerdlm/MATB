"""Strict server-side scoring for native sUAS research instruments."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping

from .probes import RenderedProbe


NASA_TLX_KEYS = (
    "mental_demand",
    "physical_demand",
    "temporal_demand",
    "performance",
    "effort",
    "frustration",
)


@dataclass(frozen=True, slots=True)
class IsaScore:
    value: int


@dataclass(frozen=True, slots=True)
class NasaTlxScore:
    subscales: Mapping[str, float]
    raw_tlx: float


@dataclass(frozen=True, slots=True)
class BedfordScore:
    value: int


@dataclass(frozen=True, slots=True)
class ProbeAnswer:
    probe_id: str
    sa_level: int
    answer: str | None
    correct_answer: str
    correct: bool
    timed_out: bool
    latency_ms: int
    unscorable_reason: str | None


@dataclass(frozen=True, slots=True)
class SagatRate:
    correct: int
    total: int
    accuracy: float | None


@dataclass(frozen=True, slots=True)
class SagatAggregate:
    overall: SagatRate
    by_level: Mapping[int, SagatRate]


def score_isa(value: object) -> IsaScore:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
        raise ValueError("ISA rating must be an integer from 1 to 10")
    return IsaScore(value)


def score_nasa_tlx(answers: Mapping[str, object]) -> NasaTlxScore:
    if not isinstance(answers, Mapping) or set(answers) != set(NASA_TLX_KEYS):
        raise ValueError("NASA-TLX requires exactly the six canonical subscales")
    values: dict[str, float] = {}
    for key in NASA_TLX_KEYS:
        value = answers[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 <= value <= 10
        ):
            raise ValueError(f"NASA-TLX {key} must be numeric from 0 to 10")
        values[key] = float(value)
    return NasaTlxScore(MappingProxyType(values), float(sum(values.values())))


def score_bedford(value: object) -> BedfordScore:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
        raise ValueError("Bedford rating must be an integer from 1 to 10")
    return BedfordScore(value)


def score_probe_answer(
    rendered: RenderedProbe,
    answer: str | None,
    *,
    latency_ms: int,
    timed_out: bool = False,
) -> ProbeAnswer:
    if not isinstance(rendered, RenderedProbe):
        raise TypeError("rendered must be a RenderedProbe")
    if isinstance(latency_ms, bool) or not isinstance(latency_ms, int) or latency_ms < 0:
        raise ValueError("SAGAT latency_ms must be a nonnegative integer")
    if not isinstance(timed_out, bool):
        raise ValueError("SAGAT timed_out must be boolean")
    if answer is not None and not isinstance(answer, str):
        raise ValueError("SAGAT answer must be text or null")
    normalized = answer.strip() if isinstance(answer, str) else None
    correct = (
        not timed_out
        and rendered.unscorable_reason is None
        and normalized == rendered.correct_answer
    )
    return ProbeAnswer(
        probe_id=rendered.probe_id,
        sa_level=rendered.sa_level,
        answer=normalized,
        correct_answer=rendered.correct_answer,
        correct=correct,
        timed_out=timed_out,
        latency_ms=latency_ms,
        unscorable_reason=rendered.unscorable_reason,
    )


def aggregate_sagat(answers: Iterable[ProbeAnswer]) -> SagatAggregate:
    rows = tuple(answers)
    if any(not isinstance(item, ProbeAnswer) for item in rows):
        raise TypeError("aggregate_sagat requires ProbeAnswer rows")
    overall = _rate(rows)
    by_level = {
        level: _rate(tuple(item for item in rows if item.sa_level == level))
        for level in (1, 2, 3)
    }
    return SagatAggregate(overall, MappingProxyType(by_level))


def _rate(rows: tuple[ProbeAnswer, ...]) -> SagatRate:
    scorable = tuple(item for item in rows if item.unscorable_reason is None)
    correct = sum(item.correct for item in scorable)
    total = len(scorable)
    return SagatRate(correct, total, correct / total if total else None)
