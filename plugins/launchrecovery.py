# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass(slots=True)
class SequenceState:
    """Represents a launch or recovery sequence."""

    uav: str
    phase: str  # LAUNCH or RECOVERY
    method: str
    status: str  # ACTIVE, COMPLETE, ABORTED, TIMEOUT
    started_at: float
    deadline: float
    reason: Optional[str] = None


class Launchrecovery(AbstractPlugin):
    """Simulates catapult launch and skyhook recovery procedures."""

    def __init__(self, label: str = '', taskplacement: str = 'topright', taskupdatetime: int = 200) -> None:
        super().__init__(label or _('Launch / Recovery'), taskplacement, taskupdatetime)
        self.sequences: Dict[str, SequenceState] = {}
        self._widget: Optional[Simpletext] = None

    def create_widgets(self) -> None:
        super().create_widgets()
        if self.task_container is None:
            return
        self._widget = self.add_widget(
            'status',
            Simpletext,
            container=self.task_container,
            text=_('No active launch/recovery phases.'),
            font_size=F['SMALL'],
            color=C['WHITE'],
            wrap_width=0.95,
            x=0.5,
            y=0.5,
        )

    def compute_next_plugin_state(self) -> bool:
        now = self.scenario_time
        for key, seq in list(self.sequences.items()):
            if seq.status != 'ACTIVE':
                continue
            if now >= seq.deadline:
                updated = replace(seq, status='TIMEOUT')
                self.sequences[key] = updated
                metric = 'launch_timeout' if seq.phase == 'LAUNCH' else 'recovery_fail'
                self.log_performance(metric, f'{seq.uav}:{seq.method}')
        return super().compute_next_plugin_state()

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        return True

    # Scenario commands --------------------------------------------------
    def launch(self, payload: str) -> None:
        """
        payload: uav,method,duration_seconds
        """
        seq = self._create_sequence(payload, 'LAUNCH')
        if seq is None:
            return
        key = self._key(seq.uav, 'launch')
        self.sequences[key] = seq
        self.log_performance('launch_initiate', f'{seq.uav}:{seq.method}:{seq.deadline - seq.started_at:.1f}')
        self._update_widget()

    def recovery(self, payload: str) -> None:
        """
        payload: uav,method,duration_seconds
        """
        seq = self._create_sequence(payload, 'RECOVERY')
        if seq is None:
            return
        key = self._key(seq.uav, 'recovery')
        self.sequences[key] = seq
        self.log_performance('recovery_initiate', f'{seq.uav}:{seq.method}:{seq.deadline - seq.started_at:.1f}')
        self._update_widget()

    def complete(self, payload: str) -> None:
        """payload: uav[,phase]"""
        seq = self._get_sequence(payload, default_phase='launch')
        if seq is None:
            return
        metric = 'launch_complete' if seq.phase == 'LAUNCH' else 'recovery_complete'
        self.sequences[self._key(seq.uav, seq.phase.lower())] = replace(seq, status='COMPLETE')
        self.log_performance(metric, f'{seq.uav}:{seq.method}')
        self._update_widget()

    def abort(self, payload: str) -> None:
        """payload: uav[,reason]"""
        parts = self._split(payload, 1)
        if parts is None:
            return
        uav = parts[0]
        reason = parts[1] if len(parts) > 1 else 'manual'
        seq = self.sequences.get(self._key(uav, 'launch'))
        if seq is None:
            return
        self.sequences[self._key(uav, 'launch')] = replace(seq, status='ABORTED', reason=reason)
        self.log_performance('launch_abort', f'{uav}:{reason}')
        self._update_widget()

    # Helpers ------------------------------------------------------------
    def _create_sequence(self, payload: str, phase: str) -> Optional[SequenceState]:
        parts = self._split(payload, 3)
        if parts is None:
            return None
        try:
            duration = float(parts[2])
        except ValueError:
            duration = 15.0
        duration = max(1.0, duration)
        return SequenceState(
            uav=parts[0],
            phase=phase,
            method=parts[1],
            status='ACTIVE',
            started_at=self.scenario_time,
            deadline=self.scenario_time + duration,
        )

    def _update_widget(self) -> None:
        if self._widget is None:
            return
        active = [seq for seq in self.sequences.values() if seq.status == 'ACTIVE']
        if not active:
            self._widget.set_text(_('No active launch/recovery phases.'))
            return

        now = self.scenario_time
        lines = [
            _('UAV | Phase   | Method    | TGO (s) | Timeline'),
        ]
        for seq in sorted(active, key=lambda s: s.deadline):
            remaining = max(0.0, seq.deadline - now)
            total = max(1.0, seq.deadline - seq.started_at)
            fraction = max(0.0, min(1.0, remaining / total))
            bar = self.format_progress_bar(fraction, length=10)
            lines.append(
                f"{seq.uav:>4} | {seq.phase:<7} | {seq.method:<9} | "
                f"{remaining:6.1f} | {bar}"
            )
        self._widget.set_text('\n'.join(lines))

    def _get_sequence(self, payload: str, default_phase: str) -> Optional[SequenceState]:
        if payload is None:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if not parts:
            return None
        uav = parts[0]
        phase = parts[1].lower() if len(parts) > 1 else default_phase
        return self.sequences.get(self._key(uav, phase))

    @staticmethod
    def _key(uav: str, phase: str) -> str:
        return f'{uav}:{phase}'

    @staticmethod
    def _split(payload: Optional[str], expected: int) -> Optional[list[str]]:
        if payload is None:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < expected:
            return None
        return parts


