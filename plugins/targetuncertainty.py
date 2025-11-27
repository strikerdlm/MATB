# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass(slots=True)
class TargetRecord:
    """Represents a pending target identification task."""

    ident: str
    clarity: str
    spawned_at: float
    deadline: float
    status: str  # ACTIVE | IDENTIFIED | TIMEOUT
    label: Optional[str] = None
    confidence: Optional[float] = None
    decided_at: Optional[float] = None


class Targetuncertainty(AbstractPlugin):
    """Simulates uncertain targets requiring confidence reports."""

    def __init__(self, label: str = '', taskplacement: str = 'topright', taskupdatetime: int = 200) -> None:
        super().__init__(label or _('Target Uncertainty'), taskplacement, taskupdatetime)
        self.targets: Dict[str, TargetRecord] = {}
        self._widget: Optional[Simpletext] = None

    def create_widgets(self) -> None:
        super().create_widgets()
        if self.task_container is None:
            return
        self._widget = self.add_widget(
            'status',
            Simpletext,
            container=self.task_container,
            text=_('No active targets.'),
            font_size=F['SMALL'],
            color=C['WHITE'],
            wrap_width=0.95,
            x=0.5,
            y=0.5,
        )

    def compute_next_plugin_state(self) -> bool:
        now = self.scenario_time
        for ident, record in list(self.targets.items()):
            if record.status != 'ACTIVE':
                continue
            if now >= record.deadline:
                updated = replace(record, status='TIMEOUT', decided_at=now)
                self.targets[ident] = updated
                self.log_performance('target_timeout', ident)
        return super().compute_next_plugin_state()

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        return True

    # Scenario commands --------------------------------------------------
    def spawn(self, payload: str) -> None:
        """
        payload: id,clarity,deadline_seconds
        clarity: LOW|MEDIUM|HIGH
        """
        parts = self._split(payload, 3)
        if parts is None:
            return
        ident = parts[0]
        clarity = parts[1].upper()
        try:
            duration = float(parts[2])
        except ValueError:
            duration = 10.0
        record = TargetRecord(
            ident=ident,
            clarity=clarity,
            spawned_at=self.scenario_time,
            deadline=self.scenario_time + max(1.0, duration),
            status='ACTIVE',
        )
        self.targets[ident] = record
        self.log_performance('target_spawn', f'{ident}:{clarity}:{duration}')
        self._update_widget()

    def identify(self, payload: str) -> None:
        """
        payload: id,label,confidence(0-1)
        """
        parts = self._split(payload, 3)
        if parts is None:
            return
        ident = parts[0]
        label = parts[1]
        try:
            confidence = float(parts[2])
        except ValueError:
            confidence = 0.0
        record = self.targets.get(ident)
        if record is None:
            return
        updated = replace(
            record,
            status='IDENTIFIED',
            label=label,
            confidence=self._clamp(confidence),
            decided_at=self.scenario_time,
        )
        self.targets[ident] = updated
        latency = self.scenario_time - record.spawned_at
        self.log_performance('target_identified', f'{ident}:{label}')
        self.log_performance('target_confidence', f'{ident}:{updated.confidence:.2f}')
        self.log_performance('target_identification_time', f'{ident}:{latency:.2f}')
        self._update_widget()

    def clear(self, payload: str) -> None:
        """payload: id or * for all"""
        if (payload or '').strip() == '*':
            self.targets.clear()
            self._update_widget()
            return
        ident = (payload or '').strip()
        if ident in self.targets:
            del self.targets[ident]
            self._update_widget()

    # Helpers ------------------------------------------------------------
    def _update_widget(self) -> None:
        if self._widget is None:
            return
        if not self.targets:
            self._widget.set_text(_('No active targets.'))
            return
        lines = []
        for record in self.targets.values():
            remaining = max(0.0, record.deadline - self.scenario_time)
            lines.append(
                f'{record.ident}:{record.clarity}:{record.status} '
                f'({remaining:.1f}s)'
            )
        self._widget.set_text('\n'.join(lines))

    @staticmethod
    def _split(payload: Optional[str], expected: int) -> Optional[list[str]]:
        if payload is None:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < expected:
            return None
        return parts

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))


