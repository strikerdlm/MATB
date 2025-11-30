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
            'chaffcapacity': 6,
            'flarecapacity': 6,
        })

        self.parameters['taskfeedback']['overdue'].update({
            'active': True,
            'color': C['RED'],
            'delayms': 0,
            'blinkdurationms': 350,
        })

        self.threats: List[ThreatContact] = []
        self._widget: Optional[Simpletext] = None
        self.countermeasure_stock = {
            'chaff': int(self.parameters['chaffcapacity']),
            'flare': int(self.parameters['flarecapacity']),
        }

    # Lifecycle ---------------------------------------------------------
    def start(self) -> None:
        self.threats = []
        self.countermeasure_stock = {
            'chaff': int(self.parameters['chaffcapacity']),
            'flare': int(self.parameters['flarecapacity']),
        }
        super().start()

    def create_widgets(self) -> None:
        """Create a 2D text-only threat strip consistent with fighter displays.

        Columns mirror typical situational displays (ID/sector/range/weapon/TTI/status),
        but remain ASCII-only so that timing and scoring stay identical to legacy
        MATB-style tasks while giving pilots a familiar scan pattern.
        """
        super().create_widgets()
        header = _('ID   | SECTOR | RNG  | WEAPON  | TTI       | STATUS')
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

    def countermeasure(self, payload: str) -> None:
        """
        payload: type,count
        """
        parts = self._split(payload, 2)
        if not parts:
            return
        c_type = parts[0].strip().lower()
        try:
            count = int(float(parts[1]))
        except (TypeError, ValueError):
            return
        count = max(1, count)
        if c_type not in ('chaff', 'flare'):
            return
        remaining_before = self.countermeasure_stock[c_type]
        spent = min(remaining_before, count)
        self.countermeasure_stock[c_type] = max(0, remaining_before - spent)
        target = self._nearest_active_threat()
        target_id = target.threat_id if target else 'none'
        self.log_performance('countermeasure_deploy', f'{c_type}:{spent}:{target_id}')
        if spent == 0:
            self.log_performance('countermeasure_empty', c_type)
        self._update_overdue()

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
        # Sort by time-to-impact so pilots see the most urgent threat first
        for threat in sorted(self.threats, key=lambda t: t.remaining(now)):
            remaining = threat.remaining(now)
            status = threat.status
            if threat.assigned_weapon:
                status = f"{status}:{threat.assigned_weapon}"
            # Fraction of TTI remaining, based on scripted tti_seconds
            denom = max(1.0, float(threat.tti_seconds))
            frac = remaining / denom
            bar = self.format_progress_bar(frac, length=8)
            line = (
                f"{threat.threat_id:<4} | {threat.sector:>3}    | "
                f"{threat.range_nm:4.1f} | {threat.weapon_hint:<7} | "
                f"{remaining:5.1f}s {bar} | {status}"
            )
            lines.append(line)
        lines.append('')
        lines.append(
            _('Chaff {0}/{1} | Flare {2}/{3}').format(
                self.countermeasure_stock['chaff'],
                int(self.parameters['chaffcapacity']),
                self.countermeasure_stock['flare'],
                int(self.parameters['flarecapacity']),
            )
        )
        self._widget.set_text('\n'.join(lines))

    def _update_overdue(self) -> None:
        now = self.scenario_time
        overdue = self.parameters['taskfeedback']['overdue']
        overdue_active = any(threat.is_overdue(now) for threat in self.threats)
        cm_low = self._countermeasure_low()
        overdue['active'] = True
        overdue['_is_visible'] = overdue_active or cm_low
        if overdue_active:
            for threat in self.threats:
                if threat.is_overdue(now):
                    self.log_performance('threat_overdue', threat.threat_id)
        if cm_low:
            self.log_performance(
                'countermeasure_low',
                f"{self.countermeasure_stock['chaff']}:{self.countermeasure_stock['flare']}",
            )

    def _nearest_active_threat(self) -> Optional[ThreatContact]:
        active = [threat for threat in self.threats if threat.status != 'RESOLVED']
        if not active:
            return None
        return min(active, key=lambda threat: threat.remaining(self.scenario_time))

    def _countermeasure_low(self) -> bool:
        chaff_capacity = max(1, int(self.parameters['chaffcapacity']))
        flare_capacity = max(1, int(self.parameters['flarecapacity']))
        ratio_chaff = self.countermeasure_stock['chaff'] / chaff_capacity
        ratio_flare = self.countermeasure_stock['flare'] / flare_capacity
        return ratio_chaff <= 0.2 or ratio_flare <= 0.2

