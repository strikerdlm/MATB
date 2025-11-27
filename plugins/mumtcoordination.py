# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass(slots=True)
class CoordinationRequest:
    """Represents a MUM-T coordination exchange."""

    ident: str
    action: str
    requester: str
    target: str
    due_at: float
    status: str
    requested_at: float
    acknowledged_at: Optional[float] = None
    decided_at: Optional[float] = None
    outcome: Optional[str] = None


class Mumtcoordination(AbstractPlugin):
    """Tracks manned-unmanned coordination requests and acknowledgements."""

    def __init__(self, label: str = '', taskplacement: str = 'topleft', taskupdatetime: int = 250) -> None:
        super().__init__(label or _('MUM-T Coordination'), taskplacement, taskupdatetime)
        self.parameters.update({
            'defaultdeadline': 20.0,
        })
        self.roles: Dict[str, str] = {
            'pilot': _('Pilot'),
            'operator': _('UAS Operator'),
        }
        self.requests: Dict[str, CoordinationRequest] = {}
        self._widget: Optional[Simpletext] = None

    def create_widgets(self) -> None:
        super().create_widgets()
        if self.task_container is None:
            return
        self._widget = self.add_widget(
            'status',
            Simpletext,
            container=self.task_container,
            text=_('No coordination requests.'),
            font_size=F['SMALL'],
            wrap_width=0.95,
            color=C['WHITE'],
            x=0.5,
            y=0.5,
        )

    def compute_next_plugin_state(self) -> bool:
        now = self.scenario_time
        for ident, request in list(self.requests.items()):
            if request.status in {'DECIDED', 'TIMEOUT'}:
                continue
            if now >= request.due_at:
                updated = replace(request, status='TIMEOUT', decided_at=now, outcome='TIMEOUT')
                self.requests[ident] = updated
                self.log_performance('mumt_coordination_timeout', ident)
        return super().compute_next_plugin_state()

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        return True

    # Scenario commands --------------------------------------------------
    def role(self, payload: str) -> None:
        """
        payload: role,label
        """
        parts = self._split(payload, 2)
        if parts is None:
            return
        self.roles[parts[0].strip().lower()] = parts[1]
        self._update_widget()

    def request(self, payload: str) -> None:
        """
        payload: id,action,deadline_seconds,requester,target
        """
        parts = self._split(payload, 5)
        if parts is None:
            return
        try:
            deadline = float(parts[2])
        except ValueError:
            deadline = float(self.parameters['defaultdeadline'])
        deadline = max(5.0, deadline)
        ident = parts[0]
        request = CoordinationRequest(
            ident=ident,
            action=parts[1],
            requester=self.roles.get(parts[3].lower(), parts[3]),
            target=self.roles.get(parts[4].lower(), parts[4]),
            due_at=self.scenario_time + deadline,
            status='PENDING',
            requested_at=self.scenario_time,
        )
        self.requests[ident] = request
        self._update_widget()
        self.log_performance('mumt_coordination_request', f'{ident}:{request.action}:{deadline:.1f}')

    def ack(self, payload: str) -> None:
        """
        payload: id[,role]
        """
        parts = self._split(payload, 1)
        if parts is None:
            return
        ident = parts[0]
        request = self.requests.get(ident)
        if request is None:
            return
        updated = replace(request, status='ACKNOWLEDGED', acknowledged_at=self.scenario_time)
        self.requests[ident] = updated
        actor = self.roles.get(parts[1].lower(), parts[1]) if len(parts) > 1 else request.target
        self._update_widget()
        self.log_performance('mumt_coordination_ack', f'{ident}:{actor}')

    def decision(self, payload: str) -> None:
        """
        payload: id,outcome
        """
        parts = self._split(payload, 2)
        if parts is None:
            return
        ident = parts[0]
        request = self.requests.get(ident)
        if request is None:
            return
        outcome = parts[1].upper()
        updated = replace(request, status='DECIDED', decided_at=self.scenario_time, outcome=outcome)
        self.requests[ident] = updated
        self._update_widget()
        self.log_performance('mumt_decision_made', f'{ident}:{outcome}')

    # Helpers ------------------------------------------------------------
    def _update_widget(self) -> None:
        if self._widget is None:
            return
        if not self.requests:
            self._widget.set_text(_('No coordination requests.'))
            return
        lines = []
        for request in self.requests.values():
            remaining = max(0, int(request.due_at - self.scenario_time))
            status = request.status
            if request.outcome and request.status == 'DECIDED':
                status = f'{status}:{request.outcome}'
            lines.append(f'{request.ident}:{request.action}:{status}:{remaining}s')
        self._widget.set_text('\n'.join(lines))

    def _split(self, payload: Optional[str], expected: int) -> Optional[list[str]]:
        if payload is None:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < expected:
            return None
        return parts


