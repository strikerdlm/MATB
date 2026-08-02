"""Deterministic research-protocol state machine for native sUAS sessions.

The controller owns protocol truth (block order, instrument gates, private
probe answers, and validity).  It deliberately does not mutate an aircraft
world or expose a rendered probe's correct answer to a caller using the public
payload.  The FastAPI runtime is responsible for durable records and pausing
the engine around the phases returned here.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Literal

from matb_integration.suas.domain.enums import Locale, WorkloadProfile
from matb_integration.suas.domain.models import BlockDefinition, ScenarioDefinition, WorldState
from matb_integration.suas.engine.prng import PCG32, derive_stream_seed
from matb_integration.suas.recording.records import RecordKind, SessionRecord
from matb_integration.suas.recording.replay import effective_records
from matb_integration.suas.scenarios.profiles import block_order_for_participant

from .probes import ProbeTemplate, RenderedProbe, load_suas_probe_bank, render_probe
from .scoring import (
    BedfordScore,
    IsaScore,
    NasaTlxScore,
    ProbeAnswer,
    score_bedford,
    score_isa,
    score_nasa_tlx,
    score_probe_answer,
)


TICK_MS = 100


class ProtocolPhase(StrEnum):
    READY_FOR_BLOCK = "READY_FOR_BLOCK"
    BLOCK_RUNNING = "BLOCK_RUNNING"
    ISA_ACTIVE = "ISA_ACTIVE"
    SAGAT_ACTIVE = "SAGAT_ACTIVE"
    POST_BLOCK_ACTIVE = "POST_BLOCK_ACTIVE"
    COMPLETE = "COMPLETE"
    ABORTED = "ABORTED"


class ProtocolError(ValueError):
    """Stable, non-HTTP protocol failure with a machine-readable code."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        detail = message or code.replace("_", " ")
        super().__init__(detail if detail.startswith(f"{code}:") else f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class ActiveProbe:
    """Public gate data plus private server-side rendering provenance."""

    kind: Literal["ISA", "SAGAT", "POST_BLOCK"]
    probe_id: str | None
    public_payload: Mapping[str, object]
    timeout_ms: int
    private_probe: RenderedProbe | None = None
    started_monotonic_s: float = 0.0


def _ceil_tick(value: int) -> int:
    return ((value + TICK_MS - 1) // TICK_MS) * TICK_MS


def _floor_tick(value: int) -> int:
    return (value // TICK_MS) * TICK_MS


class ProtocolController:
    """Pure protocol authority for one participant's native session."""

    def __init__(
        self,
        scenario: ScenarioDefinition,
        *,
        participant_id: str,
        locale: Locale | str,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        if not isinstance(scenario, ScenarioDefinition):
            raise TypeError("scenario must be a ScenarioDefinition")
        if not isinstance(participant_id, str) or not participant_id:
            raise ValueError("participant_id must be non-empty")
        try:
            resolved_locale = Locale(locale)
        except ValueError as error:
            raise ValueError("locale is invalid") from error
        participant_order = block_order_for_participant(participant_id)
        self.scenario = scenario
        self.participant_id = participant_id
        self.locale = resolved_locale
        self.block_order: tuple[WorkloadProfile, ...] = (
            WorkloadProfile.PRACTICE,
            *participant_order,
        )
        missing = [profile.value for profile in self.block_order if profile.value not in scenario.blocks]
        if missing:
            raise ProtocolError("block_order_violation", f"scenario is missing block {missing[0]}")
        self.phase = ProtocolPhase.READY_FOR_BLOCK
        self.block_index = 0
        self.current_block_id: str | None = None
        self.active_probe: ActiveProbe | None = None
        self.private_probe: RenderedProbe | None = None
        self.sagat_due_ms: int | None = None
        self.validity = "valid"
        self.protocol_deviations: list[dict[str, object]] = []
        self.isa_scores: dict[str, IsaScore] = {}
        self.sagat_answers: list[ProbeAnswer] = []
        self.post_block_scores: dict[str, IsaScore | NasaTlxScore | BedfordScore] = {}
        self.completed_scales: set[str] = set()
        self._isa_cursor = 0
        self._sagat_cursor = 0
        self._sagat_due_consumed = False
        self._freeze_state: WorldState | None = None
        self._freeze_time_ms: int | None = None
        self._clock = monotonic_clock or (lambda: 0.0)
        seed, stream = derive_stream_seed(scenario.seed, "protocol", participant_id)
        self._rng = PCG32(seed=seed, stream=stream)
        self._probe_bank: dict[str, ProbeTemplate] | None = None

    @property
    def next_block_id(self) -> str | None:
        if self.block_index >= len(self.block_order):
            return None
        return self.block_order[self.block_index].value

    @property
    def current_block(self) -> BlockDefinition | None:
        return self.scenario.blocks.get(self.current_block_id or "")

    @property
    def probe_active(self) -> bool:
        return self.phase in {ProtocolPhase.ISA_ACTIVE, ProtocolPhase.SAGAT_ACTIVE}

    @property
    def conceal_operational_state(self) -> bool:
        return self.phase is ProtocolPhase.SAGAT_ACTIVE

    @property
    def current_block_index(self) -> int:
        return self.block_index

    @property
    def sagat_due_time_ms(self) -> int | None:
        return self.sagat_due_ms

    def start_block(self, block_id: WorkloadProfile | str) -> BlockDefinition:
        requested = WorkloadProfile(block_id)
        expected = self.next_block_id
        if expected != requested.value:
            raise ProtocolError(
                "block_order_violation",
                f"expected block {expected or 'COMPLETE'}, received {requested.value}",
            )
        if self.phase is not ProtocolPhase.READY_FOR_BLOCK:
            raise ProtocolError("invalid_protocol_phase", f"cannot start a block from {self.phase.value}")
        block = self.scenario.blocks[requested.value]
        self.current_block_id = requested.value
        self.phase = ProtocolPhase.BLOCK_RUNNING
        self.active_probe = None
        self.private_probe = None
        self._isa_cursor = 0
        self._sagat_cursor = 0
        self._sagat_due_consumed = False
        self._freeze_state = None
        self._freeze_time_ms = None
        self.completed_scales.clear()
        self.post_block_scores.clear()
        self.sagat_due_ms = self._choose_sagat_due(block)
        return block

    def on_tick(self, state: WorldState, *, simulation_time_ms: int | None = None) -> ActiveProbe | None:
        """Advance protocol gates using authoritative simulation time only."""

        if not isinstance(state, WorldState):
            raise TypeError("state must be a WorldState")
        if self.phase in {ProtocolPhase.ISA_ACTIVE, ProtocolPhase.SAGAT_ACTIVE, ProtocolPhase.POST_BLOCK_ACTIVE}:
            return self.active_probe
        if self.phase is not ProtocolPhase.BLOCK_RUNNING:
            return None
        block = self.current_block
        if block is None or state.block_id != block.block_id:
            raise ProtocolError("block_state_mismatch")
        now = state.simulation_time_ms if simulation_time_ms is None else simulation_time_ms
        if isinstance(now, bool) or not isinstance(now, int) or now < 0:
            raise ValueError("simulation_time_ms must be a nonnegative integer")

        if (
            not self._sagat_due_consumed
            and self.sagat_due_ms is not None
            and now >= self.sagat_due_ms
        ):
            # A direct restore/test may hand us a time past an ISA trigger.
            # The live tick loop normally consumes that trigger first; when a
            # caller jumps over it, mark it observed rather than presenting a
            # stale ISA gate after the freeze has completed.
            while self._isa_cursor < len(block.isa_times_ms) and block.isa_times_ms[self._isa_cursor] <= now:
                self._isa_cursor += 1
            self._sagat_due_consumed = True
            self._freeze_state = copy.deepcopy(state)
            self._freeze_time_ms = now
            return self._activate_next_sagat()

        if self._isa_cursor < len(block.isa_times_ms) and now >= block.isa_times_ms[self._isa_cursor]:
            due_ms = block.isa_times_ms[self._isa_cursor]
            self._isa_cursor += 1
            probe_id = f"isa:{block.block_id}:{due_ms}"
            self.phase = ProtocolPhase.ISA_ACTIVE
            self.active_probe = ActiveProbe(
                kind="ISA",
                probe_id=probe_id,
                timeout_ms=60_000,
                public_payload={
                    "kind": "ISA",
                    "probe_id": probe_id,
                    "scale_id": "ISA",
                    "options": list(range(1, 11)),
                    "timeout_ms": 60_000,
                },
                started_monotonic_s=self._clock(),
            )
            return self.active_probe

        if now >= block.duration_ms:
            self.phase = ProtocolPhase.POST_BLOCK_ACTIVE
            self.active_probe = ActiveProbe(
                kind="POST_BLOCK",
                probe_id=None,
                timeout_ms=0,
                public_payload={
                    "kind": "POST_BLOCK",
                    "scales": list(block.post_block_questionnaires),
                },
                started_monotonic_s=self._clock(),
            )
            return self.active_probe
        return None

    def submit_isa(self, probe_id: str, rating: int) -> IsaScore:
        self._require_active("ISA", probe_id)
        score = score_isa(rating)
        self.isa_scores[probe_id] = score
        self.active_probe = None
        self.phase = ProtocolPhase.BLOCK_RUNNING
        return score

    def submit_sagat(
        self,
        probe_id: str,
        answer: str | None,
        *,
        latency_ms: int | None = None,
        timed_out: bool = False,
    ) -> ProbeAnswer:
        self._require_active("SAGAT", probe_id)
        private = self.private_probe
        if private is None:
            raise ProtocolError("probe_state_missing")
        if latency_ms is None:
            elapsed = max(0.0, self._clock() - self.active_probe.started_monotonic_s)  # type: ignore[union-attr]
            latency_ms = int(round(elapsed * 1_000))
        result = score_probe_answer(private, answer, latency_ms=latency_ms, timed_out=timed_out)
        self.sagat_answers.append(result)
        if self._sagat_cursor < len(self.current_block.sagat.probe_ids):  # type: ignore[union-attr]
            self._activate_next_sagat()
        else:
            self.active_probe = None
            self.private_probe = None
            self._freeze_state = None
            self._freeze_time_ms = None
            self.phase = ProtocolPhase.BLOCK_RUNNING
        return result

    def submit_post_block(self, scale_id: str, answers: Mapping[str, object]) -> IsaScore | NasaTlxScore | BedfordScore:
        if self.phase is not ProtocolPhase.POST_BLOCK_ACTIVE:
            raise ProtocolError("post_block_active", "post-block scales are not active")
        if scale_id == "NASA_TLX":
            score: IsaScore | NasaTlxScore | BedfordScore = score_nasa_tlx(answers)
        elif scale_id == "BEDFORD":
            if set(answers) == {"value"}:
                score = score_bedford(answers["value"])
            elif set(answers) == {"bedford"}:
                score = score_bedford(answers["bedford"])
            else:
                raise ValueError("Bedford requires exactly one value")
        else:
            raise ValueError("unknown post-block scale")
        self.post_block_scores[scale_id] = score
        self.completed_scales.add(scale_id)
        block = self.current_block
        required = set(block.post_block_questionnaires if block else ("NASA_TLX", "BEDFORD"))
        if required.issubset(self.completed_scales):
            self._complete_current_block()
        return score

    def timeout_active_probe(self) -> ProbeAnswer | None:
        """Close an expired probe deterministically and mark a deviation."""

        active = self.active_probe
        if active is None or active.kind not in {"ISA", "SAGAT"}:
            raise ProtocolError("no_active_probe")
        self.validity = "valid_with_deviation"
        self.protocol_deviations.append({
            "code": "probe_timeout",
            "kind": active.kind,
            "probe_id": active.probe_id,
            "block_id": self.current_block_id,
        })
        if active.kind == "SAGAT":
            if active.probe_id is None:
                raise ProtocolError("probe_state_missing")
            return self.submit_sagat(
                active.probe_id,
                None,
                latency_ms=active.timeout_ms,
                timed_out=True,
            )
        self.active_probe = None
        self.phase = ProtocolPhase.BLOCK_RUNNING
        return None

    def interrupt_probe(self, reason: str = "probe_interrupted") -> None:
        if not self.probe_active:
            raise ProtocolError("no_active_probe")
        self.validity = "valid_with_deviation"
        self.protocol_deviations.append({
            "code": "probe_interrupted", "reason": reason,
            "block_id": self.current_block_id,
            "probe_id": self.active_probe.probe_id if self.active_probe else None,
        })
        self.active_probe = None
        self.private_probe = None
        self._freeze_state = None
        self._freeze_time_ms = None
        self.phase = ProtocolPhase.ABORTED

    def advance_block(self, block_id: WorkloadProfile | str | None = None) -> BlockDefinition:
        if self.phase is ProtocolPhase.COMPLETE:
            raise ProtocolError("protocol_complete")
        if self.phase is not ProtocolPhase.READY_FOR_BLOCK:
            raise ProtocolError("invalid_protocol_phase", "required post-block scales are incomplete")
        expected = self.next_block_id
        if block_id is None:
            block_id = expected
        if block_id is None:
            raise ProtocolError("protocol_complete")
        return self.start_block(block_id)

    def status(self) -> dict[str, object]:
        """Public protocol metadata; no private answer or evaluator input."""

        active = self.active_probe.public_payload if self.active_probe is not None else None
        return {
            "protocol_phase": self.phase.value,
            "block_order": [item.value for item in self.block_order],
            "current_block_index": self.block_index,
            "active_block_id": self.current_block_id,
            "next_block_id": self.next_block_id,
            "active_probe": dict(active) if active is not None else None,
            "validity": self.validity,
        }

    def _choose_sagat_due(self, block: BlockDefinition) -> int:
        guard_ms = min(30_000, max(TICK_MS, block.duration_ms // 10))
        lower = max(block.sagat.window_start_ms, guard_ms)
        upper = min(block.sagat.window_end_ms, block.duration_ms - guard_ms)
        candidates = self._candidate_ticks(lower, upper, block.isa_times_ms, guard_ms)
        if not candidates:
            # Existing reference scenarios place the SAGAT window immediately
            # after an ISA boundary. Preserve the 30 s block-boundary guard,
            # then reject only exact ISA collisions when no fully guarded tick
            # exists; short E2E fixtures still get strict guard validation.
            candidates = self._candidate_ticks(lower, upper, block.isa_times_ms, TICK_MS)
        if not candidates:
            raise ProtocolError("sagat_window_unavailable", f"block {block.block_id} has no eligible SAGAT tick")
        return candidates[self._rng.next_uint32() % len(candidates)]

    @staticmethod
    def _candidate_ticks(lower: int, upper: int, isa_times: Sequence[int], guard_ms: int) -> list[int]:
        if upper < lower:
            return []
        start = _ceil_tick(lower)
        end = _floor_tick(upper)
        return [
            tick for tick in range(start, end + 1, TICK_MS)
            if all(abs(tick - isa) >= guard_ms for isa in isa_times)
        ]

    def _activate_next_sagat(self) -> ActiveProbe:
        block = self.current_block
        state = self._freeze_state
        if block is None or state is None:
            raise ProtocolError("probe_state_missing")
        if self._probe_bank is None:
            self._probe_bank = load_suas_probe_bank(self.locale)
        if self._sagat_cursor >= len(block.sagat.probe_ids):
            raise ProtocolError("probe_sequence_complete")
        probe_id = block.sagat.probe_ids[self._sagat_cursor]
        self._sagat_cursor += 1
        try:
            template = self._probe_bank[probe_id]
        except KeyError as error:
            raise ProtocolError("unknown_probe", probe_id) from error
        rendered = render_probe(template, state, self.scenario, block=block)
        self.private_probe = rendered
        self.phase = ProtocolPhase.SAGAT_ACTIVE
        self.active_probe = ActiveProbe(
            kind="SAGAT",
            probe_id=probe_id,
            timeout_ms=rendered.timeout_ms,
            private_probe=rendered,
            started_monotonic_s=self._clock(),
            public_payload={
                "kind": "SAGAT",
                **rendered.to_public_dict(),
                "conceal_operational_state": True,
            },
        )
        return self.active_probe

    def _require_active(self, kind: str, probe_id: str) -> None:
        if self.active_probe is None or self.active_probe.kind != kind:
            raise ProtocolError("probe_active", f"expected an active {kind} probe")
        if self.active_probe.probe_id != probe_id:
            raise ProtocolError("probe_id_mismatch")

    def _complete_current_block(self) -> None:
        self.active_probe = None
        self.private_probe = None
        self._freeze_state = None
        self._freeze_time_ms = None
        self.block_index += 1
        self.current_block_id = None
        self.sagat_due_ms = None
        self.phase = ProtocolPhase.COMPLETE if self.block_index >= len(self.block_order) else ProtocolPhase.READY_FOR_BLOCK


def restore_protocol_from_records(
    scenario: ScenarioDefinition,
    participant_id: str,
    locale: Locale | str,
    records: Sequence[SessionRecord],
    through_sequence: int,
) -> ProtocolController:
    """Reduce the authoritative record prefix into protocol state.

    The reducer is intentionally conservative. It never infers a gate from
    engine time; a missing or contradictory lifecycle record is a stable
    recovery error instead.
    """

    if isinstance(through_sequence, bool) or not isinstance(through_sequence, int) or through_sequence < 0:
        raise ProtocolError("invalid_record_sequence")
    materialized = tuple(records)
    if any(record.sequence > through_sequence for record in materialized):
        raise ProtocolError("future_protocol_record")
    try:
        effective = tuple(record for record in effective_records(materialized) if record.sequence <= through_sequence)
    except ValueError as error:
        raise ProtocolError("invalid_protocol_records") from error
    controller = ProtocolController(scenario, participant_id=participant_id, locale=locale)
    for record in effective:
        payload = dict(record.payload)
        event = payload.get("event")
        if record.kind is RecordKind.LIFECYCLE and event == "block_started":
            block_id = payload.get("block_id", record.block_id)
            if not isinstance(block_id, str):
                raise ProtocolError("invalid_protocol_records")
            if controller.phase is not ProtocolPhase.READY_FOR_BLOCK:
                raise ProtocolError("contradictory_protocol_records")
            controller.start_block(block_id)
        elif record.kind is RecordKind.LIFECYCLE and event == "block_finished":
            if controller.current_block_id != record.block_id:
                raise ProtocolError("contradictory_protocol_records")
            # A restored finished block advances only when its required scales
            # were also durable; otherwise recovery must remain at the gate.
            if controller.phase is ProtocolPhase.BLOCK_RUNNING:
                controller.phase = ProtocolPhase.POST_BLOCK_ACTIVE
            if controller.phase is ProtocolPhase.POST_BLOCK_ACTIVE:
                controller.completed_scales.update({"NASA_TLX", "BEDFORD"})
                controller._complete_current_block()
        elif record.kind is RecordKind.PROTOCOL_DEVIATION:
            controller.validity = "valid_with_deviation"
        elif record.kind is RecordKind.QUESTIONNAIRE:
            instrument = payload.get("scale_id")
            if instrument in {"NASA_TLX", "BEDFORD"}:
                controller.completed_scales.add(str(instrument))
    if controller.phase is ProtocolPhase.BLOCK_RUNNING and controller.current_block_id is None:
        raise ProtocolError("incomplete_protocol_records")
    return controller


__all__ = [
    "ActiveProbe",
    "ProtocolController",
    "ProtocolError",
    "ProtocolPhase",
    "restore_protocol_from_records",
]
