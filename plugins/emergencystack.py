# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass
class ChecklistItem:
    label: str
    done: bool = False


@dataclass
class EmergencyEvent:
    ident: str
    title: str
    checklist: List[ChecklistItem]
    triggered_at: float
    resolved_at: Optional[float] = None

    def status(self) -> str:
        if self.resolved_at is not None:
            return _('RESOLVED')
        if all(item.done for item in self.checklist):
            return _('COMPLETE')
        return _('ACTIVE')


class Emergencystack(AbstractPlugin):
    """Displays cascading failures and checklists for emergency management."""

    def __init__(self, label: str = '', taskplacement: str = 'topmid', taskupdatetime: int = 400) -> None:
        super().__init__(label or _('Emergency Stack'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'autoack': validation.is_boolean,
        }

        self.parameters.update({
            'autoack': False,
        })

        self.parameters['taskfeedback']['overdue'].update({
            'active': True,
            'color': C['RED'],
            'delayms': 0,
            'blinkdurationms': 500,
        })

        self.events: List[EmergencyEvent] = []
        self._widget: Optional[Simpletext] = None

    # Lifecycle ----------------------------------------------------------
    def start(self) -> None:
        self.events = []
        super().start()

    def create_widgets(self) -> None:
        super().create_widgets()
        self._widget = self.add_widget(
            'stack',
            Simpletext,
            container=self.task_container,
            text=_('No emergencies.'),
            font_size=F['SMALL'],
            y=0.5,
            wrap_width=0.95,
            color=C['WHITE'],
        )

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        self._update_overdue()
        return True

    # Scenario commands --------------------------------------------------
    def trigger(self, payload: str) -> None:
        """
        payload: id,title,step1|step2|step3
        """
        parts = self._split(payload, 2)
        if not parts:
            return
        checklist = parts[2].split('|') if len(parts) > 2 else []
        event = EmergencyEvent(
            ident=parts[0],
            title=parts[1],
            checklist=[ChecklistItem(label=step) for step in checklist if step.strip()],
            triggered_at=self.scenario_time,
        )
        self.events.append(event)
        self.log_performance('emergency_trigger', event.ident)

    def stepdone(self, payload: str) -> None:
        """
        payload: id,index (0-based)
        """
        parts = self._split(payload, 2)
        if not parts:
            return
        event = self._find_event(parts[0])
        if event is None:
            return
        try:
            index = int(parts[1])
        except ValueError:
            return
        if 0 <= index < len(event.checklist):
            event.checklist[index].done = True
            self.log_performance('emergency_step', f'{event.ident}:{index}')

    def resolve(self, payload: str) -> None:
        event = self._find_event(payload)
        if event is None:
            return
        event.resolved_at = self.scenario_time
        self.log_performance('emergency_resolve', event.ident)

    def clear(self, payload: str) -> None:
        self.events = []
        self.log_performance('emergency_clear', 'all')

    # Helpers ------------------------------------------------------------
    def _split(self, payload: str, min_parts: int) -> Optional[List[str]]:
        if not payload:
            return None
        parts = [part.strip() for part in payload.split(',')]
        if len(parts) < min_parts:
            return None
        return parts

    def _find_event(self, ident: str) -> Optional[EmergencyEvent]:
        ident = ident.strip().lower()
        for event in self.events:
            if event.ident.lower() == ident:
                return event
        return None

    def _update_widget(self) -> None:
        if self._widget is None:
            return
        if not self.events:
            self._widget.set_text(_('No emergencies.'))
            return
        lines: List[str] = []
        for event in self.events:
            lines.append(f"{event.ident} | {event.title} | {event.status()}")
            for idx, item in enumerate(event.checklist):
                state = _('✓') if item.done else _('•')
                lines.append(f"   {state} Step {idx+1}: {item.label}")
        self._widget.set_text('\n'.join(lines))

    def _update_overdue(self) -> None:
        overdue_active = any(event.status() == _('ACTIVE') for event in self.events)
        overdue = self.parameters['taskfeedback']['overdue']
        overdue['active'] = True
        overdue['_is_visible'] = overdue_active
        if overdue_active and self.parameters['autoack']:
            for event in self.events:
                if event.status() == _('ACTIVE'):
                    # Auto mark first step as reminder
                    if event.checklist:
                        event.checklist[0].done = True


