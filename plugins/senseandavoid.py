# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass
class Intruder:
    """Represents an individual conflict to resolve."""

    identifier: str
    bearing: str
    range_nm: float
    altitude_ft: float
    time_to_conflict: float
    created_at: float
    status: str = field(default='ACTIVE')
    action: Optional[str] = field(default=None)
    resolved_at: Optional[float] = field(default=None)

    def remaining(self, now: float) -> float:
        return max(0.0, self.time_to_conflict - (now - self.created_at))


class Senseandavoid(AbstractPlugin):
    """Provides intruder tracking and sense-and-avoid prompts."""

    def __init__(self, label: str = '', taskplacement: str = 'bottomright', taskupdatetime: int = 500) -> None:
        super().__init__(label or _('Sense & Avoid'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'horizontalthresholdnm': validation.is_positive_float,
            'verticalthresholdft': validation.is_positive_integer,
        }

        self.parameters.update({
            'horizontalthresholdnm': 1.5,
            'verticalthresholdft': 500,
        })

        self.intruders: Dict[str, Intruder] = {}
        self._widget: Optional[Simpletext] = None

        self.parameters['taskfeedback']['overdue'].update({
            'active': True,
            'color': C['RED'],
            'delayms': 0,
            'blinkdurationms': 400,
        })

    def create_widgets(self) -> None:
        super().create_widgets()
        header = _('ID | Brg | RNG (nm) | ALT (ft) | TTI (s) | Status')
        self.add_widget(
            'header',
            Simpletext,
            container=self.task_container,
            text=header,
            font_size=F['SMALL'],
            y=0.9,
            color=C['WHITE'],
            bold=True,
        )
        self._widget = self.add_widget(
            'intruders',
            Simpletext,
            container=self.task_container,
            text=_('Waiting for intruders…'),
            font_size=F['SMALL'],
            y=0.6,
            wrap_width=0.95,
            color=C['WHITE'],
        )

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget_text()
        self._update_overdue_state()
        return True

    # Scenario commands -------------------------------------------------
    def spawn(self, payload: str) -> None:
        """
        Expect payload: id,bearing,range_nm,altitude_ft,time_to_conflict
        Example: senseandavoid;spawn;INTR1,090,2.1,300,-20
        """
        parts = self._split_payload(payload, min_parts=5)
        if not parts:
            return
        identifier = parts[0].upper()
        try:
            intruder = Intruder(
                identifier=identifier,
                bearing=parts[1],
                range_nm=float(parts[2]),
                altitude_ft=float(parts[3]),
                time_to_conflict=float(parts[4]),
                created_at=self.scenario_time,
            )
        except ValueError:
            return
        self.intruders[identifier] = intruder
        self.log_performance('saa_spawn', f'{identifier}:{intruder.range_nm}:{intruder.altitude_ft}')

    def resolve(self, payload: str) -> None:
        """
        Expect payload: id,action
        """
        parts = self._split_payload(payload, min_parts=2)
        if not parts:
            return
        identifier = parts[0].upper()
        if identifier not in self.intruders:
            return
        action = parts[1]
        intruder = self.intruders[identifier]
        intruder.status = 'RESOLVED'
        intruder.action = action
        intruder.resolved_at = self.scenario_time
        self.log_performance('saa_resolve', f'{identifier}:{action}:{self._resolution_time(intruder):.1f}')

    def clear(self, payload: str) -> None:
        identifier = payload.upper().strip()
        if identifier in self.intruders:
            del self.intruders[identifier]
            self.log_performance('saa_clear', identifier)

    def thresholds(self, payload: str) -> None:
        """
        Expect payload: horizontal_nm,vertical_ft
        """
        parts = self._split_payload(payload, min_parts=2)
        if not parts:
            return
        try:
            self.parameters['horizontalthresholdnm'] = float(parts[0])
            self.parameters['verticalthresholdft'] = int(float(parts[1]))
        except ValueError:
            return
        self.log_performance('saa_thresholds', f"{self.parameters['horizontalthresholdnm']}:{self.parameters['verticalthresholdft']}")

    # Helpers -----------------------------------------------------------
    def _split_payload(self, payload: str, min_parts: int) -> Optional[list]:
        if not payload:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < min_parts:
            return None
        return parts

    def _update_widget_text(self) -> None:
        if self._widget is None:
            return
        if not self.intruders:
            self._widget.set_text(_('No intruders.'))
            return
        lines = []
        now = self.scenario_time
        for intruder in sorted(self.intruders.values(), key=lambda x: x.remaining(now)):
            remaining = intruder.remaining(now)
            status = _('ACTIVE') if intruder.status == 'ACTIVE' else _('RESOLVED')
            if intruder.action:
                status = f"{status}:{intruder.action}"
            line = (
                f"{intruder.identifier} | {intruder.bearing} | "
                f"{intruder.range_nm:.1f} | {intruder.altitude_ft:.0f} | "
                f"{remaining:5.1f} | {status}"
            )
            lines.append(line)
        self._widget.set_text('\n'.join(lines))

    def _update_overdue_state(self) -> None:
        now = self.scenario_time
        overdue_active = any(
            intr.status == 'ACTIVE' and intr.remaining(now) <= 0 for intr in self.intruders.values()
        )
        overdue = self.parameters['taskfeedback']['overdue']
        overdue['active'] = True
        overdue['_is_visible'] = overdue_active
        if overdue_active:
            for intr in self.intruders.values():
                if intr.status == 'ACTIVE' and intr.remaining(now) <= 0:
                    self.log_performance('saa_overdue', intr.identifier)

    def _resolution_time(self, intruder: Intruder) -> float:
        if intruder.resolved_at is None:
            return 0.0
        return max(0.0, intruder.resolved_at - intruder.created_at)

