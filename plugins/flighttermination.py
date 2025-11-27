# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass(slots=True)
class TerminationPrompt:
    """Represents an active flight termination decision."""

    ident: str
    description: str
    urgency: str
    status: str
    started_at: float
    deadline: float
    decision: Optional[str] = None
    confidence: Optional[float] = None
    decided_at: Optional[float] = None


class Flighttermination(AbstractPlugin):
    """Handles BVLOS flight termination decision drills."""

    def __init__(self, label: str = '', taskplacement: str = 'topmid', taskupdatetime: int = 200) -> None:
        super().__init__(label or _('Flight Termination'), taskplacement, taskupdatetime)
        self.parameters.update({
            'defaultduration': 20.0,
        })
        self.prompts: Dict[str, TerminationPrompt] = {}
        self._widget: Optional[Simpletext] = None

    def create_widgets(self) -> None:
        super().create_widgets()
        if self.task_container is None:
            return
        self._widget = self.add_widget(
            'status',
            Simpletext,
            container=self.task_container,
            text=_('No termination prompts.'),
            font_size=F['SMALL'],
            wrap_width=0.95,
            color=C['WHITE'],
            x=0.5,
            y=0.5,
        )

    def compute_next_plugin_state(self) -> bool:
        now = self.scenario_time
        for ident, prompt in list(self.prompts.items()):
            if prompt.status != 'ACTIVE':
                continue
            if now >= prompt.deadline:
                updated = replace(prompt, status='TIMEOUT', decided_at=now)
                self.prompts[ident] = updated
                self.log_performance('termination_timeout', ident)
        return super().compute_next_plugin_state()

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        return True

    # Scenario commands --------------------------------------------------
    def prompt(self, payload: str) -> None:
        """
        payload: id,description,urgency[,duration_seconds]
        """
        parts = self._split(payload, 3)
        if parts is None:
            return
        duration = self._parse_duration(parts[3] if len(parts) > 3 else None)
        ident = parts[0]
        prompt = TerminationPrompt(
            ident=ident,
            description=parts[1],
            urgency=parts[2],
            status='ACTIVE',
            started_at=self.scenario_time,
            deadline=self.scenario_time + duration,
        )
        self.prompts[ident] = prompt
        self._update_widget()
        self.log_performance('termination_prompt', f'{ident}:{prompt.urgency}:{duration:.1f}')

    def decide(self, payload: str) -> None:
        """
        payload: id,decision,confidence(0-1)
        """
        parts = self._split(payload, 3)
        if parts is None:
            return
        prompt = self.prompts.get(parts[0])
        if prompt is None or prompt.status not in {'ACTIVE', 'TIMEOUT'}:
            return
        decision = parts[1].strip().upper()
        confidence = self._clamp_confidence(parts[2])
        updated = replace(
            prompt,
            status='DECIDED',
            decision=decision,
            confidence=confidence,
            decided_at=self.scenario_time,
        )
        self.prompts[parts[0]] = updated
        self._update_widget()
        self.log_performance('termination_decision', f'{parts[0]}:{decision}:{confidence:.2f}')

    def clear(self, payload: str) -> None:
        """payload: id"""
        ident = (payload or '').strip()
        if not ident:
            self.prompts.clear()
            self._update_widget()
            return
        if ident in self.prompts:
            del self.prompts[ident]
            self._update_widget()

    # Helpers ------------------------------------------------------------
    def _update_widget(self) -> None:
        if self._widget is None:
            return
        if not self.prompts:
            self._widget.set_text(_('No termination prompts.'))
            return
        lines = []
        for prompt in self.prompts.values():
            base = f'{prompt.ident}:{prompt.urgency}:{prompt.status}'
            if prompt.decision:
                base += f':{prompt.decision}'
            lines.append(base)
        self._widget.set_text('\n'.join(lines))

    def _split(self, payload: str, expected: int) -> Optional[list[str]]:
        if payload is None:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < expected:
            return None
        return parts

    def _parse_duration(self, value: Optional[str]) -> float:
        if value is None:
            return float(self.parameters['defaultduration'])
        try:
            duration = float(value)
        except ValueError:
            duration = float(self.parameters['defaultduration'])
        return max(1.0, duration)

    @staticmethod
    def _clamp_confidence(value: str) -> float:
        try:
            numeric = float(value)
        except ValueError:
            numeric = 0.5
        return max(0.0, min(1.0, numeric))


