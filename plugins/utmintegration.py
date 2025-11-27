# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass(slots=True)
class UTMRestriction:
    """Represents a dynamic UTM restriction."""

    ident: str
    description: str
    severity: str
    status: str
    issued_at: float
    expires_at: float
    replan_count: int = 0
    violations: int = 0


class Utmintegration(AbstractPlugin):
    """Simulates dynamic UTM restrictions for BVLOS ops."""

    def __init__(self, label: str = '', taskplacement: str = 'bottomright', taskupdatetime: int = 300) -> None:
        super().__init__(label or _('UTM Integration'), taskplacement, taskupdatetime)
        self.parameters.update({
            'defaultduration': 60.0,
        })
        self.restrictions: Dict[str, UTMRestriction] = {}
        self._widget: Optional[Simpletext] = None

    def create_widgets(self) -> None:
        super().create_widgets()
        if self.task_container is None:
            return
        self._widget = self.add_widget(
            'status',
            Simpletext,
            container=self.task_container,
            text=_('Airspace clear.'),
            font_size=F['SMALL'],
            color=C['WHITE'],
            wrap_width=0.9,
            x=0.5,
            y=0.5,
        )

    def compute_next_plugin_state(self) -> bool:
        now = self.scenario_time
        for ident, restriction in list(self.restrictions.items()):
            if restriction.status != 'ACTIVE':
                continue
            if now >= restriction.expires_at:
                updated = replace(restriction, status='EXPIRED')
                self.restrictions[ident] = updated
                self.log_performance('restriction_expire', ident)
        return super().compute_next_plugin_state()

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        return True

    # Scenario commands --------------------------------------------------
    def restriction(self, payload: str) -> None:
        """
        payload: id,description,severity[,duration_seconds]
        """
        parts = self._split(payload, 3)
        if parts is None:
            return
        duration = self._parse_duration(parts[3] if len(parts) > 3 else None)
        ident = parts[0]
        restriction = UTMRestriction(
            ident=ident,
            description=parts[1],
            severity=parts[2],
            status='ACTIVE',
            issued_at=self.scenario_time,
            expires_at=self.scenario_time + duration,
        )
        self.restrictions[ident] = restriction
        self._update_widget()
        self.log_performance('utm_restriction_received', f'{ident}:{restriction.severity}:{duration:.1f}')

    def replan(self, payload: str) -> None:
        """payload: id"""
        ident = (payload or '').strip()
        restriction = self.restrictions.get(ident)
        if restriction is None:
            return
        updated = replace(restriction, replan_count=restriction.replan_count + 1)
        self.restrictions[ident] = updated
        self.log_performance('route_replan', f'{ident}:{updated.replan_count}')

    def violation(self, payload: str) -> None:
        """
        payload: id[,detail]
        """
        parts = self._split(payload, 1)
        if parts is None:
            return
        ident = parts[0]
        detail = parts[1] if len(parts) > 1 else ''
        restriction = self.restrictions.get(ident)
        if restriction is not None:
            updated = replace(restriction, violations=restriction.violations + 1)
            self.restrictions[ident] = updated
        self.log_performance('restriction_violation', f'{ident}:{detail}')

    def clear(self, payload: str) -> None:
        """payload: id"""
        ident = (payload or '').strip()
        restriction = self.restrictions.get(ident)
        if restriction is None:
            return
        updated = replace(restriction, status='CLEARED')
        self.restrictions[ident] = updated
        self._update_widget()
        self.log_performance('restriction_clear', ident)

    # Helpers ------------------------------------------------------------
    def _update_widget(self) -> None:
        if self._widget is None:
            return
        active = [r for r in self.restrictions.values() if r.status == 'ACTIVE']
        if not active:
            self._widget.set_text(_('Airspace clear.'))
            return
        lines = [f'{r.ident}:{r.severity}:{int(r.expires_at - self.scenario_time)}s' for r in active]
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
        return max(5.0, duration)


