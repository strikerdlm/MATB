"""Operator capacity tracking plugin."""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin
from plugins.operatorcapacity_model import CapacityModel, CapacityReport


class Operatorcapacity(AbstractPlugin):
    """Displays validated multi-UAV workload bands against live assignments."""

    def __init__(self, label: str = '', taskplacement: str = 'bottomright', taskupdatetime: int = 1000) -> None:
        super().__init__(label or _('Operator Capacity'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'active_limit': validation.is_positive_integer,
            'supervisory_limit': validation.is_positive_integer,
            'overlap_low_threshold': validation.is_in_unit_interval,
            'overlap_high_threshold': validation.is_in_unit_interval,
            'overlap_window': validation.is_positive_integer,
        }

        self.parameters.update({
            'active_limit': 3,
            'supervisory_limit': 6,
            'overlap_low_threshold': 0.3,
            'overlap_high_threshold': 0.6,
            'overlap_window': 16,
        })
        overdue = self.parameters['taskfeedback']['overdue']
        overdue.update({'active': True, 'delayms': 0, 'blinkdurationms': 600})

        self._model = CapacityModel(
            active_limit=self.parameters['active_limit'],
            supervisory_limit=self.parameters['supervisory_limit'],
            overlap_low_threshold=self.parameters['overlap_low_threshold'],
            overlap_high_threshold=self.parameters['overlap_high_threshold'],
            overlap_window=self.parameters['overlap_window'],
        )
        self._reports: Dict[str, CapacityReport] = {
            'active': CapacityReport('active', 0, self._model.active_limit, False, ()),
            'supervisory': CapacityReport('supervisory', 0, self._model.effective_supervisory_limit(), False, ()),
        }
        self._warning_message = ''
        self._last_overlap_pair: Optional[Tuple[str, str]] = None
        self._last_overlap_value: Optional[float] = None
        self._widgets: Dict[str, Simpletext] = {}

    def create_widgets(self) -> None:
        """Build the textual status blocks."""
        super().create_widgets()
        self._widgets['active'] = self.add_widget(
            'active_status',
            Simpletext,
            container=self.task_container,
            text=self._format_report(_('Active Control'), self._reports['active']),
            font_size=F['SMALL'],
            x=0.02,
            y=0.8,
            anchor_x='left',
            color=C['WHITE'],
            wrap_width=0.96,
        )
        self._widgets['supervisory'] = self.add_widget(
            'supervisory_status',
            Simpletext,
            container=self.task_container,
            text=self._format_report(_('Supervisory Control'), self._reports['supervisory']),
            font_size=F['SMALL'],
            x=0.02,
            y=0.6,
            anchor_x='left',
            color=C['WHITE'],
            wrap_width=0.96,
        )
        self._widgets['overlap'] = self.add_widget(
            'overlap_status',
            Simpletext,
            container=self.task_container,
            text=self._format_overlap_text(),
            font_size=F['SMALL'],
            x=0.02,
            y=0.4,
            anchor_x='left',
            color=C['WHITE'],
            wrap_width=0.96,
        )
        self._widgets['warning'] = self.add_widget(
            'warning_banner',
            Simpletext,
            container=self.task_container,
            text=self._warning_message or _('Within validated workload bands'),
            font_size=F['SMALL'],
            x=0.02,
            y=0.2,
            anchor_x='left',
            color=C['ORANGE'],
            wrap_width=0.96,
        )

    def refresh_widgets(self) -> bool:
        """Update status text each frame."""
        if not super().refresh_widgets():
            return False
        self._widgets['active'].set_text(self._format_report(_('Active Control'), self._reports['active']))
        self._widgets['supervisory'].set_text(
            self._format_report(_('Supervisory Control'), self._reports['supervisory'])
        )
        self._widgets['overlap'].set_text(self._format_overlap_text())
        self._widgets['warning'].set_text(self._warning_message or _('Within validated workload bands'))
        self._update_warning_indicator()
        return True

    def set(self, payload: str) -> None:
        """Scenario command: ``operatorcapacity;set;role,value``."""
        if not payload:
            return
        parts = [part.strip() for part in payload.split(',', 1) if part.strip()]
        if len(parts) != 2:
            return
        role = parts[0].lower()
        if role not in ('active', 'supervisory'):
            return
        assignments = self._parse_assignments(parts[1])
        explicit_count = len(assignments) if assignments else self._safe_positive_int(parts[1])
        self._update_model_limits()
        report = self._model.update_assignments(role, assignments if assignments else None, explicit_count)
        self._reports[role] = report
        metric = 'operator_capacity_active' if role == 'active' else 'operator_capacity_supervisory'
        self.log_performance(metric, report.count)
        if report.exceeded:
            self.log_performance('operator_capacity_breach', role)
        self._warning_message = self._compose_warning(report)
        self._update_warning_indicator()

    def overlap(self, payload: str) -> None:
        """Scenario command: ``operatorcapacity;overlap;uav1,uav2,ratio``."""
        if not payload:
            return
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) != 3:
            return
        ratio = self._safe_ratio(parts[2])
        if ratio is None:
            return
        self._update_model_limits()
        self._last_overlap_pair = (parts[0], parts[1])
        self._last_overlap_value = self._model.record_overlap(ratio)
        self.log_performance('operator_overlap', round(self._last_overlap_value, 4))
        self._refresh_supervisory_report()
        self._warning_message = self._compose_warning(self._reports['supervisory'])
        self._update_warning_indicator()

    def _update_model_limits(self) -> None:
        self._model.update_config(
            active_limit=self._safe_positive_int(self.parameters.get('active_limit'), fallback=3),
            supervisory_limit=self._safe_positive_int(self.parameters.get('supervisory_limit'), fallback=6),
            overlap_low_threshold=self._safe_ratio(self.parameters.get('overlap_low_threshold'), fallback=0.3),
            overlap_high_threshold=self._safe_ratio(self.parameters.get('overlap_high_threshold'), fallback=0.6),
            overlap_window=self._safe_positive_int(self.parameters.get('overlap_window'), fallback=16),
        )

    def _refresh_supervisory_report(self) -> None:
        current = self._reports['supervisory']
        updated_limit = self._model.effective_supervisory_limit()
        exceeded = current.count > updated_limit
        self._reports['supervisory'] = CapacityReport(
            role='supervisory',
            count=current.count,
            limit=updated_limit,
            exceeded=exceeded,
            assignments=current.assignments,
        )
        if exceeded:
            self.log_performance('operator_capacity_breach', 'supervisory')

    def _update_warning_indicator(self) -> None:
        overdue = self.parameters['taskfeedback']['overdue']
        overdue['_is_visible'] = any(report.exceeded for report in self._reports.values())
        overdue['active'] = True

    def _format_report(self, label: str, report: CapacityReport) -> str:
        assignment_str = ', '.join(report.assignments) if report.assignments else _('Unspecified')
        status = _('OVER LIMIT') if report.exceeded else _('Within band')
        return f"{label}: {report.count}/{report.limit} | {assignment_str} | {status}"

    def _format_overlap_text(self) -> str:
        avg = self._model.average_overlap()
        if avg is None:
            return _('Overlap: awaiting data')
        pair_text = ''
        if self._last_overlap_pair:
            pair_text = f"{self._last_overlap_pair[0]}↔{self._last_overlap_pair[1]}"
        return _('Overlap avg {avg:.2f} {pair}').format(avg=avg, pair=pair_text)

    def _compose_warning(self, report: CapacityReport) -> str:
        if not report.exceeded:
            return ''
        delta = report.count - report.limit
        role_label = _('Active') if report.role == 'active' else _('Supervisory')
        return _('{} load exceeds validated limit by {}').format(role_label, delta)

    def _parse_assignments(self, raw: str) -> Tuple[str, ...]:
        tokens = [token.strip() for token in re.split(r'[|/;,\s]+', raw) if token.strip()]
        if not tokens:
            return ()
        if all(token.isdigit() for token in tokens):
            return ()
        return tuple(tokens)

    @staticmethod
    def _safe_positive_int(value: object, fallback: int = 0) -> int:
        try:
            parsed = int(float(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return fallback
        return max(parsed, 0)

    @staticmethod
    def _safe_ratio(value: object, fallback: Optional[float] = None) -> Optional[float]:
        try:
            parsed = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return fallback
        return min(max(parsed, 0.0), 1.0)

