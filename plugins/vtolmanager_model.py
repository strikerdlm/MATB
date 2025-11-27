"""VTOL energy and phase management helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional, Tuple


@dataclass
class VtolState:
    """Per-UAV VTOL state."""

    phase: str = 'idle'
    phase_started_at: float = 0.0
    battery_remaining: float = 0.0
    battery_capacity: float = 0.0
    power_multiplier: float = 1.0
    pending_confirmation: bool = False
    last_update_at: float = 0.0
    warning_level: str = 'normal'
    overdue_transition: bool = False


class VtolModel:
    """Pure helper that tracks VTOL flight phases and battery draw."""

    def __init__(
        self,
        battery_seconds: float,
        phase_power: Mapping[str, float],
        confirm_phases: Iterable[str],
        warning_ratio: float,
        critical_ratio: float,
    ) -> None:
        self._default_capacity = max(60.0, float(battery_seconds))
        self._phase_power = dict(phase_power)
        self._confirm_phases = {phase.lower() for phase in confirm_phases}
        self._warning_ratio = max(0.0, min(1.0, warning_ratio))
        self._critical_ratio = max(0.0, min(self._warning_ratio, critical_ratio))
        self._states: Dict[str, VtolState] = {}

    def ensure(self, uav: str, now: float) -> VtolState:
        if uav not in self._states:
            self._states[uav] = VtolState(
                battery_remaining=self._default_capacity,
                battery_capacity=self._default_capacity,
                last_update_at=now,
            )
        return self._states[uav]

    def set_phase(self, uav: str, phase: str, now: float) -> Dict[str, object]:
        state = self.ensure(uav, now)
        duration = max(0.0, now - state.phase_started_at) if state.phase else 0.0
        state.phase = phase
        state.phase_started_at = now
        state.pending_confirmation = phase in self._confirm_phases
        state.overdue_transition = False
        state.power_multiplier = self._phase_power.get(phase, 1.0)
        state.last_update_at = now
        return {
            'duration': duration,
            'power': state.power_multiplier,
            'pending_confirmation': state.pending_confirmation,
        }

    def confirm(self, uav: str) -> bool:
        state = self._states.get(uav)
        if state is None or not state.pending_confirmation:
            return False
        state.pending_confirmation = False
        state.overdue_transition = False
        return True

    def set_battery(self, uav: str, seconds: float, now: float) -> float:
        state = self.ensure(uav, now)
        state.battery_capacity = max(60.0, seconds)
        state.battery_remaining = state.battery_capacity
        state.warning_level = 'normal'
        state.last_update_at = now
        return state.battery_capacity

    def update_energy(self, uav: str, now: float) -> Tuple[float, Optional[str]]:
        state = self.ensure(uav, now)
        dt = max(0.0, now - state.last_update_at)
        if dt > 0:
            state.battery_remaining = max(
                0.0, state.battery_remaining - dt * max(0.1, state.power_multiplier)
            )
            state.last_update_at = now
        level = self._classify_warning(state)
        changed = None
        if level != state.warning_level:
            state.warning_level = level
            changed = level
        return state.battery_remaining, changed

    def mark_overdue(self, uav: str) -> bool:
        state = self._states.get(uav)
        if state is None or not state.pending_confirmation:
            return False
        if state.overdue_transition:
            return False
        state.overdue_transition = True
        return True

    def pending(self, uav: str) -> bool:
        state = self._states.get(uav)
        return bool(state and state.pending_confirmation)

    def _classify_warning(self, state: VtolState) -> str:
        if state.battery_capacity <= 0:
            return 'empty'
        ratio = state.battery_remaining / state.battery_capacity
        if state.battery_remaining == 0:
            return 'empty'
        if ratio <= self._critical_ratio:
            return 'critical'
        if ratio <= self._warning_ratio:
            return 'warning'
        return 'normal'

