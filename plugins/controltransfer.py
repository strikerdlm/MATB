# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass(slots=True)
class TransferRecord:
    """Represents a custody transfer request."""

    ident: str
    uav_id: str
    origin: str
    target: str
    reason: str
    status: str
    initiated_at: float
    acknowledged_at: Optional[float]
    completed_at: Optional[float]
    deadline: float
    failure_reason: Optional[str] = None


class Controltransfer(AbstractPlugin):
    """Tracks BVLOS control transfers between operators."""

    def __init__(self, label: str = '', taskplacement: str = 'topright', taskupdatetime: int = 250) -> None:
        super().__init__(label or _('Control Transfer Monitor'), taskplacement, taskupdatetime)
        self.parameters.update({
            'defaulttimeout': 30.0,
        })
        self.transfers: Dict[str, TransferRecord] = {}
        self._widget: Optional[Simpletext] = None

    def create_widgets(self) -> None:
        super().create_widgets()
        if self.task_container is None:
            return
        self._widget = self.add_widget(
            'status',
            Simpletext,
            container=self.task_container,
            text=_('No active transfers.'),
            font_size=F['SMALL'],
            color=C['WHITE'],
            wrap_width=0.95,
            x=0.5,
            y=0.5,
        )

    def compute_next_plugin_state(self) -> bool:
        now = self.scenario_time
        for ident, record in list(self.transfers.items()):
            if record.status in {'COMPLETED', 'FAILED'}:
                continue
            if now >= record.deadline:
                self._mark_failure(ident, 'timeout')
        return super().compute_next_plugin_state()

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        return True

    # Scenario commands --------------------------------------------------
    def initiate(self, payload: str) -> None:
        """
        payload: transfer_id,uav_id,origin,target,reason[,timeout_seconds]
        """
        parts = self._split(payload, 5)
        if parts is None:
            return
        timeout = self._parse_timeout(parts[5] if len(parts) > 5 else None)
        ident = parts[0]
        record = TransferRecord(
            ident=ident,
            uav_id=parts[1],
            origin=parts[2],
            target=parts[3],
            reason=parts[4],
            status='PENDING',
            initiated_at=self.scenario_time,
            acknowledged_at=None,
            completed_at=None,
            deadline=self.scenario_time + timeout,
        )
        self.transfers[ident] = record
        self._update_widget()
        self.log_performance('control_transfer_initiate', f'{ident}:{record.uav_id}:{record.origin}->{record.target}:{timeout:.1f}')

    def acknowledge(self, payload: str) -> None:
        """
        payload: transfer_id[,actor]
        """
        parts = self._split(payload, 1)
        if parts is None:
            return
        ident = parts[0]
        record = self.transfers.get(ident)
        if record is None or record.status != 'PENDING':
            return
        updated = replace(record, status='ACKNOWLEDGED', acknowledged_at=self.scenario_time)
        self.transfers[ident] = updated
        actor = parts[1] if len(parts) > 1 else updated.target
        self._update_widget()
        self.log_performance('control_transfer_acknowledge', f'{ident}:{actor}')

    def complete(self, payload: str) -> None:
        """payload: transfer_id"""
        ident = (payload or '').strip()
        record = self.transfers.get(ident)
        if record is None or record.status == 'COMPLETED':
            return
        updated = replace(record, status='COMPLETED', completed_at=self.scenario_time)
        self.transfers[ident] = updated
        self._update_widget()
        self.log_performance('control_transfer_complete', ident)

    def fail(self, payload: str) -> None:
        """
        payload: transfer_id[,reason]
        """
        parts = self._split(payload, 1)
        if parts is None:
            return
        reason = parts[1] if len(parts) > 1 else 'manual'
        self._mark_failure(parts[0], reason)

    # Helpers ------------------------------------------------------------
    def _mark_failure(self, ident: str, reason: str) -> None:
        record = self.transfers.get(ident)
        if record is None or record.status == 'FAILED':
            return
        updated = replace(record, status='FAILED', failure_reason=reason, completed_at=self.scenario_time)
        self.transfers[ident] = updated
        self._update_widget()
        self.log_performance('control_transfer_fail', f'{ident}:{reason}')

    def _update_widget(self) -> None:
        if self._widget is None:
            return
        if not self.transfers:
            self._widget.set_text(_('No active transfers.'))
            return
        lines = []
        for record in self.transfers.values():
            status = record.status
            if status == 'FAILED' and record.failure_reason:
                status = f'{status}:{record.failure_reason}'
            lines.append(f'{record.ident}:{record.uav_id}:{status}')
        self._widget.set_text('\n'.join(lines))

    def _split(self, payload: str, expected: int) -> Optional[list[str]]:
        if payload is None:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < expected:
            return None
        return parts

    def _parse_timeout(self, value: Optional[str]) -> float:
        if value is None:
            return float(self.parameters['defaulttimeout'])
        try:
            seconds = float(value)
        except ValueError:
            seconds = float(self.parameters['defaulttimeout'])
        return max(1.0, seconds)


