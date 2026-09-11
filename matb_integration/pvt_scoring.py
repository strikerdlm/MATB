"""Portable PVT validation/scoring, moved verbatim from the ingestion router."""
from __future__ import annotations
from statistics import median
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

PVT_VERSION = 2
PVT_DURATION_MS = 600_000
PVT_RESPONSE_TIMEOUT_MS = 30_000


class PvtTrialIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    wait_ms: int = Field(ge=2_000, le=10_000)
    stimulus_at_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    response_at_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    rt_ms: float | None = Field(default=None, ge=0, le=PVT_RESPONSE_TIMEOUT_MS, allow_inf_nan=False)
    outcome: Literal["response", "lapse", "false_start", "timeout"]

    @model_validator(mode="after")
    def validate_timing(self) -> "PvtTrialIn":
        if self.outcome == "false_start":
            if self.response_at_ms is None or (self.rt_ms is not None and self.rt_ms >= 100):
                raise ValueError("false_start requires a response before 100 ms")
            if self.stimulus_at_ms is None:
                if self.rt_ms is not None:
                    raise ValueError("a response before stimulus onset cannot have rt_ms")
            elif self.rt_ms is None or abs(self.response_at_ms - self.stimulus_at_ms - self.rt_ms) > 5:
                raise ValueError("false-start timing does not match stimulus and response")
            return self
        if self.stimulus_at_ms is None:
            raise ValueError("stimulus_at_ms is required after stimulus onset")
        if self.outcome == "timeout":
            if self.response_at_ms is not None or self.rt_ms is not None:
                raise ValueError("timeout must not contain a response")
            return self
        if self.response_at_ms is None or self.rt_ms is None:
            raise ValueError("response timing is required")
        observed = self.response_at_ms - self.stimulus_at_ms
        if abs(observed - self.rt_ms) > 5:
            raise ValueError("rt_ms does not match stimulus and response timestamps")
        if self.outcome == "response" and not 100 <= self.rt_ms < 500:
            raise ValueError("response outcome requires 100 <= rt_ms < 500")
        if self.outcome == "lapse" and self.rt_ms < 500:
            raise ValueError("lapse outcome requires rt_ms >= 500")
        return self


class PvtAssessmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str | None = None
    participant_id: str
    visit_ordinal: int = Field(ge=1)
    kss_score: int = Field(ge=1, le=9)
    administered_at: str = Field(min_length=1)
    duration_ms: int = Field(ge=1)
    fast_mode: bool = False
    trials: list[PvtTrialIn] = Field(min_length=0, max_length=10000)
    overwrite: bool = False
    execution_purpose: Literal["practice", "study"]
    locale: Literal["es-419", "en"] = "es-419"
    timing_version: Literal[1, 2] = 1
    interruption_count: int = Field(default=0, ge=0)
    max_frame_gap_ms: float = Field(default=0, ge=0, allow_inf_nan=False)
    terminal_phase: Literal["waiting", "stimulus", "feedback", "complete"] | None = None
    terminal_stimulus_at_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_protocol_duration(self) -> "PvtAssessmentIn":
        if self.fast_mode and self.execution_purpose == "study":
            raise ValueError("fast_mode requires practice purpose")
        indices = [trial.index for trial in self.trials]
        if indices != list(range(len(indices))):
            raise ValueError("trial indices must be contiguous from zero")
        previous_end = 0.0
        for trial in self.trials:
            start = trial.stimulus_at_ms if trial.stimulus_at_ms is not None else trial.response_at_ms
            end = trial.response_at_ms if trial.response_at_ms is not None else (trial.stimulus_at_ms or 0) + PVT_RESPONSE_TIMEOUT_MS
            if start is None or start < previous_end or end < start or end > self.duration_ms:
                raise ValueError("trial timeline must be ordered and inside the session duration")
            previous_end = end
        if self.timing_version == 2:
            if self.terminal_phase is None:
                raise ValueError("version 2 requires terminal phase evidence")
            if self.terminal_phase == "stimulus":
                if self.terminal_stimulus_at_ms is None or not previous_end <= self.terminal_stimulus_at_ms <= self.duration_ms:
                    raise ValueError("terminal stimulus must follow recorded trials within the session")
            elif self.terminal_stimulus_at_ms is not None:
                raise ValueError("terminal stimulus is only valid for an unfinished stimulus")
        return self

    def validity_reasons(self) -> list[str]:
        reasons = []
        if not self.trials:
            reasons.append("no_completed_trials")
        if self.fast_mode or self.execution_purpose == "practice":
            reasons.append("practice")
        if self.timing_version < 2:
            reasons.append("legacy_timing_evidence_missing")
        if self.duration_ms < PVT_DURATION_MS:
            reasons.append("duration_below_10_minutes")
        if self.interruption_count or self.max_frame_gap_ms > 250:
            reasons.append("interrupted_or_delayed_presentation")
        previous_end = 0.0
        for trial in self.trials:
            start = trial.stimulus_at_ms if trial.stimulus_at_ms is not None else trial.response_at_ms or 0
            if self.timing_version == 2:
                if trial.stimulus_at_ms is not None and abs(start - previous_end - trial.wait_ms) > 250:
                    reasons.append("wait_timing_mismatch")
                if trial.stimulus_at_ms is None and start - previous_end > trial.wait_ms + 250:
                    reasons.append("false_start_after_expected_onset")
            if start - previous_end > 11250:
                reasons.append("unexplained_timeline_gap")
            previous_end = trial.response_at_ms if trial.response_at_ms is not None else (trial.stimulus_at_ms or 0) + PVT_RESPONSE_TIMEOUT_MS
        if self.terminal_phase == "stimulus" and self.terminal_stimulus_at_ms is not None:
            if self.terminal_stimulus_at_ms - previous_end > 10250 or self.duration_ms - self.terminal_stimulus_at_ms > 30250:
                reasons.append("terminal_timing_mismatch")
        terminal_limit = 40500 if self.terminal_phase == "stimulus" else 11250
        if self.duration_ms - previous_end > terminal_limit:
            reasons.append("incomplete_timeline")
        return list(dict.fromkeys(reasons))


def _metrics(trials: list[PvtTrialIn], *, duration_ms: int) -> dict[str, int | float | None]:
    response_times = [
        trial.rt_ms for trial in trials
        if trial.rt_ms is not None and trial.rt_ms >= 100
    ]
    reciprocal_speeds = [1_000 / value for value in response_times if value > 0]
    return {
        "duration_ms": duration_ms,
        "total_trials": len(trials),
        "valid_responses": len(response_times),
        "median_rt_ms": round(float(median(response_times)), 3) if response_times else None,
        "mean_reciprocal_rt_per_s": (
            round(sum(reciprocal_speeds) / len(reciprocal_speeds), 6)
            if reciprocal_speeds else None
        ),
        "lapses": sum(trial.outcome == "lapse" for trial in trials),
        "false_starts": sum(trial.outcome == "false_start" for trial in trials),
        "timeouts": sum(trial.outcome == "timeout" for trial in trials),
    }
