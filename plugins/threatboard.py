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
class ThreatContact:
    threat_id: str
    sector: str
    range_nm: float
    weapon_hint: str
    created_at: float
    tti_seconds: float
    status: str = 'PENDING'  # PENDING, ENGAGED, RESOLVED
    assigned_weapon: Optional[str] = None
    resolved_at: Optional[float] = None

    def remaining(self, now: float) -> float:
        elapsed = now - self.created_at
        return max(0.0, self.tti_seconds - elapsed)

    def is_overdue(self, now: float) -> bool:
        return self.status != 'RESOLVED' and self.remaining(now) <= 0.0


class Threatboard(AbstractPlugin):
    """Displays radar/weapon threat timelines for high-performance aircraft crews."""

    def __init__(self, label: str = '', taskplacement: str = 'topright', taskupdatetime: int = 300) -> None:
        super().__init__(label or _('Threat Board'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'defaulttti': validation.is_positive_integer,
            'maxthreats': validation.is_positive_integer,
        }

        self.parameters.update({
            'defaulttti': 30,
            'maxthreats': 5,
        })

        self.parameters['taskfeedback']['overdue'].update({
            'active': True,
            'color': C['RED'],
            'delayms': 0,
            'blinkdurationms': 350,
        })

        self.threats: List[ThreatContact] = []
        self._widget: Optional[Simpletext] = None

    # Lifecycle ---------------------------------------------------------
    def start(self) -> None:
        self.threats = []
        super().start()

    def create_widgets(self) -> None:
        super().create_widgets()
        header = _('ID | Sector | Range (nm) | Weapon | TTI (s) | Status')
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
            'threats',
            Simpletext,
            container=self.task_container,
            text=_('No threats.'),
            font_size=F['SMALL'],
            y=0.6,
            wrap_width=0.95,
            color=C['WHITE'],
        )

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        self._update_overdue()
        return True

    # Scenario commands -------------------------------------------------
    def spawn(self, payload: str) -> None:
        """
        payload: id,sector,range_nm,weapon_hint[,tti_seconds]
        """
        parts = self._split(payload, 4)
        if not parts:
            return
        try:
            range_nm = float(parts[2])
        except ValueError:
            return
        try:
            tti = float(parts[4]) if len(parts) > 4 else float(self.parameters['defaulttti'])
        except ValueError:
            tti = float(self.parameters['defaulttti'])

        threat = ThreatContact(
            threat_id=parts[0],
            sector=parts[1],
            range_nm=range_nm,
            weapon_hint=parts[3],
            created_at=self.scenario_time,
            tti_seconds=max(1.0, tti),
        )
        self.threats.append(threat)
        max_size = int(self.parameters['maxthreats'])
        if len(self.threats) > max_size:
            dropped = self.threats.pop(0)
            self.log_performance('threat_drop', dropped.threat_id)
        self.log_performance('threat_spawn', f'{threat.threat_id}:{threat.sector}:{threat.range_nm}')

    def engage(self, payload: str) -> None:
        """
        payload: id,weapon
        """
        parts = self._split(payload, 2)
        if not parts:
            return
        threat = self._find(parts[0])
        if threat is None:
            return
        threat.status = 'ENGAGED'
        threat.assigned_weapon = parts[1]
        self.log_performance('threat_engage', f'{threat.threat_id}:{threat.assigned_weapon}')

    def resolve(self, payload: str) -> None:
        """
        payload: id,result
        """
        parts = self._split(payload, 2)
        if not parts:
            return
        threat = self._find(parts[0])
        if threat is None:
            return
        threat.status = 'RESOLVED'
        threat.resolved_at = self.scenario_time
        result = parts[1]
        self.log_performance('threat_resolve', f'{threat.threat_id}:{result}')

    def reprioritize(self, payload: str) -> None:
        """
        payload: id,new_sector,new_range
        """
        parts = self._split(payload, 3)
        if not parts:
            return
        threat = self._find(parts[0])
        if threat is None:
            return
        try:
            threat.range_nm = float(parts[2])
        except ValueError:
            return
        threat.sector = parts[1]
        self.log_performance('threat_reprioritize', f'{threat.threat_id}:{threat.sector}:{threat.range_nm}')

    def clear(self, payload: str) -> None:
        self.threats = []
        self.log_performance('threat_clear', 'all')

    # Helpers -----------------------------------------------------------
    def _split(self, payload: str, min_parts: int) -> Optional[List[str]]:
        if not payload:
            return None
        parts = [part.strip() for part in payload.split(',')]
        if len(parts) < min_parts:
            return None
        return parts

    def _find(self, threat_id: str) -> Optional[ThreatContact]:
        threat_id = threat_id.strip().lower()
        for threat in self.threats:
            if threat.threat_id.lower() == threat_id:
                return threat
        return None

    def _update_widget(self) -> None:
        if self._widget is None:
            return
        if not self.threats:
            self._widget.set_text(_('No threats.'))
            return
        now = self.scenario_time
        lines: List[str] = []
        for threat in self.threats:
            remaining = threat.remaining(now)
            status = threat.status
            if threat.assigned_weapon:
                status = f"{status}:{threat.assigned_weapon}"
            line = (
                f"{threat.threat_id} | {threat.sector} | "
                f"{threat.range_nm:4.1f} | {threat.weapon_hint} | "
                f"{remaining:5.1f} | {status}"
            )
            lines.append(line)
        self._widget.set_text('\n'.join(lines))

    def _update_overdue(self) -> None:
        now = self.scenario_time
        overdue = self.parameters['taskfeedback']['overdue']
        overdue_active = any(threat.is_overdue(now) for threat in self.threats)
        overdue['active'] = True
        overdue['_is_visible'] = overdue_active
        if overdue_active:
            for threat in self.threats:
                if threat.is_overdue(now):
                    self.log_performance('threat_overdue', threat.threat_id)

