# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F, STATUS_COLORS
from core.event import Event
from core.logger import logger
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass(slots=True)
class AutomationRule:
    """Threshold-based automation policy."""

    source_plugin: str
    metric: str
    operator: str
    threshold: float
    raw_threshold: str
    mode: str
    target_plugin: str
    command: str
    payload_template: str
    window: float
    cooldown: float
    last_fired: float = -1.0
    occurrences: Deque[float] = field(default_factory=deque)

    def should_trigger(self, value: object, scenario_time: float) -> bool:
        """Return True when the incoming metric satisfies the rule."""
        op = self.operator
        if op == 'count':
            self.occurrences.append(scenario_time)
            if self.window > 0.0:
                while self.occurrences and scenario_time - self.occurrences[0] > self.window:
                    self.occurrences.popleft()
            return len(self.occurrences) > self.threshold

        if op in {'gt', 'ge', 'lt', 'le'}:
            numeric_value = AutomationRule._coerce_float(value)
            if numeric_value is None:
                return False
            if op == 'gt':
                return numeric_value > self.threshold
            if op == 'ge':
                return numeric_value >= self.threshold
            if op == 'lt':
                return numeric_value < self.threshold
            if op == 'le':
                return numeric_value <= self.threshold

        comp_value = str(value).strip().lower()
        target = self.raw_threshold.lower()
        if op == 'eq':
            return comp_value == target
        if op == 'ne':
            return comp_value != target
        return False

    @staticmethod
    def _coerce_float(value: object) -> Optional[float]:
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).strip())
        except (ValueError, TypeError):
            return None

class Automationhooks(AbstractPlugin):
    """Emits manual/auto switches for other plugins based on threshold triggers."""

    _OPERATORS = {'gt', 'ge', 'lt', 'le', 'eq', 'ne', 'count'}
    # Maximum number of rules to display in the widget (prevent overflow)
    _MAX_DISPLAY_RULES = 8
    # Duration in seconds to highlight recently fired rules
    _FIRE_HIGHLIGHT_DURATION = 3.0

    def __init__(
        self,
        label: str = '',
        taskplacement: str = 'bottomright',
        taskupdatetime: int = 500,
    ) -> None:
        super().__init__(label or _('Automation Hooks'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'targetplugin': validation.is_string,
            'showvisualfeedback': validation.is_boolean,
        }

        self.parameters.update({
            'targetplugin': 'missiondirector',
            'showvisualfeedback': True,  # Enable visual feedback by default
        })

        self.rules: List[AutomationRule] = []
        self.active = False
        self._rules_by_key: Dict[Tuple[str, str], List[AutomationRule]] = {}
        self._listener_keys: set[Tuple[str, str]] = set()
        self._status_widget: Optional[Simpletext] = None
        self._rules_widget: Optional[Simpletext] = None

    def create_widgets(self) -> None:
        """Create visual feedback widgets for automation hooks."""
        super().create_widgets()

        if not self.parameters.get('showvisualfeedback', True):
            return

        # Status header showing active/inactive state
        self._status_widget = self.add_widget(
            'status',
            Simpletext,
            container=self.task_container,
            text=_('Automation: INACTIVE'),
            font_size=F['SMALL'],
            y=0.9,
            color=C['GREY'],
            bold=True,
        )

        # Rules list showing enabled rules and recently fired ones
        self._rules_widget = self.add_widget(
            'rules',
            Simpletext,
            container=self.task_container,
            text=_('No rules defined.'),
            font_size=F['SMALL'],
            y=0.65,
            wrap_width=0.95,
            color=C['WHITE'],
        )

    def refresh_widgets(self) -> bool:
        """Update visual feedback widgets."""
        if not super().refresh_widgets():
            return False
        self._update_visual_feedback()
        return True

    def _update_visual_feedback(self) -> None:
        """Update visual feedback widgets with current rule states."""
        if not self.parameters.get('showvisualfeedback', True):
            return

        # Update status widget
        if self._status_widget is not None:
            if self.active:
                self._status_widget.set_text(_('Automation: ACTIVE'))
                self._status_widget.set_color(STATUS_COLORS.get('NORMAL', C['GREEN']))
            else:
                self._status_widget.set_text(_('Automation: INACTIVE'))
                self._status_widget.set_color(C['GREY'])

        # Update rules widget
        if self._rules_widget is not None:
            self._update_rules_display()

    def _update_rules_display(self) -> None:
        """Update the rules list display."""
        if self._rules_widget is None:
            return

        if not self.rules:
            self._rules_widget.set_text(_('No rules defined.'))
            return

        lines: List[str] = []
        now = self.scenario_time
        displayed = 0

        for rule in self.rules:
            if displayed >= self._MAX_DISPLAY_RULES:
                remaining = len(self.rules) - displayed
                lines.append(f'  +{remaining} {_("more rules")}...')
                break

            # Determine if rule was recently fired
            recently_fired = (
                rule.last_fired >= 0
                and (now - rule.last_fired) < self._FIRE_HIGHLIGHT_DURATION
            )

            # Build rule summary line
            indicator = '★' if recently_fired else '•'
            op_symbol = self._operator_symbol(rule.operator)
            summary = (
                f'{indicator} {rule.source_plugin}.{rule.metric} '
                f'{op_symbol}{rule.raw_threshold} → {rule.mode}'
            )
            lines.append(summary)
            displayed += 1

        self._rules_widget.set_text('\n'.join(lines))

    @staticmethod
    def _operator_symbol(op: str) -> str:
        """Convert operator string to display symbol."""
        symbols = {
            'gt': '>',
            'ge': '≥',
            'lt': '<',
            'le': '≤',
            'eq': '=',
            'ne': '≠',
            'count': '#',
        }
        return symbols.get(op, op)

    def start(self) -> None:
        super().start()
        self.rules.clear()
        self._rules_by_key.clear()
        self._listener_keys.clear()

    def stop(self) -> None:
        self._deregister_all_listeners()
        super().stop()

    # Scenario commands --------------------------------------------------
    def rule(self, payload: str) -> None:
        """
        Register a new automation rule.

        Format variants:
        - plugin,metric,threshold,mode
        - plugin,metric,operator,threshold,mode[,key=value ...]

        Supported operator tokens: gt, ge, lt, le, eq, ne, count
        Optional key/value pairs:
            target=<plugin> (default: parameter targetplugin)
            command=<method> (default: automation)
            payload=<template> (default: {mode})
            window=<seconds> (count operator only, default 0)
            cooldown=<seconds> (default 2)
        """
        parts = self._split(payload, 4)
        if not parts:
            return

        operator = 'count'
        threshold_idx = 2
        if len(parts) >= 5 and parts[2].lower() in self._OPERATORS:
            operator = parts[2].lower()
            threshold_idx = 3
        try:
            threshold_value = float(parts[threshold_idx])
        except ValueError:
            return

        mode_idx = threshold_idx + 1
        if mode_idx >= len(parts):
            return
        mode = parts[mode_idx].upper()

        extras = parts[mode_idx + 1:]
        extra_kwargs = self._parse_extra_args(extras)

        target_plugin = extra_kwargs.get('target', self.parameters['targetplugin']).lower()
        command = extra_kwargs.get('command', 'automation')
        payload_template = extra_kwargs.get('payload', '{mode}')
        window = self._safe_float(extra_kwargs.get('window'), default=0.0)
        cooldown = max(0.0, self._safe_float(extra_kwargs.get('cooldown'), default=2.0))

        rule = AutomationRule(
            source_plugin=parts[0].lower(),
            metric=parts[1].lower(),
            operator=operator,
            threshold=threshold_value,
            raw_threshold=parts[threshold_idx],
            mode=mode,
            target_plugin=target_plugin,
            command=command,
            payload_template=payload_template,
            window=window,
            cooldown=cooldown,
        )
        self.rules.append(rule)
        self._rules_by_key.setdefault((rule.source_plugin, rule.metric), []).append(rule)
        self._ensure_listener(rule.source_plugin, rule.metric)
        self.log_performance('automation_rule', payload)

    def enable(self, payload: str) -> None:
        self.active = True
        self.log_performance('automation_enable', payload or '1')

    def disable(self, payload: str) -> None:
        self.active = False
        self.log_performance('automation_disable', payload or '1')

    def clear(self, payload: str) -> None:
        """Remove all rules and detach listeners."""
        self.rules.clear()
        self._rules_by_key.clear()
        self._deregister_all_listeners()
        self.log_performance('automation_clear', payload or 'all')

    # Internal -----------------------------------------------------------
    def _parse_extra_args(self, extras: List[str]) -> Dict[str, str]:
        config: Dict[str, str] = {}
        last_key: Optional[str] = None
        for token in extras:
            if '=' not in token:
                if last_key is not None and token:
                    config[last_key] = f"{config[last_key]},{token}"
                continue
            key, value = token.split('=', 1)
            last_key = key.strip().lower()
            config[last_key] = value.strip()
        return config

    @staticmethod
    def _safe_float(value: Optional[str], default: float) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _ensure_listener(self, module: str, metric: str) -> None:
        key = (module, metric)
        if key in self._listener_keys:
            return
        logger.register_metric_listener(module, metric, self._on_metric)
        self._listener_keys.add(key)

    def _deregister_all_listeners(self) -> None:
        for module, metric in list(self._listener_keys):
            logger.unregister_metric_listener(module, metric, self._on_metric)
        self._listener_keys.clear()

    def _on_metric(self, module: str, metric: str, value: object, scenario_time: float) -> None:
        if not self.active:
            return
        key = (module.lower(), metric.lower())
        for rule in self._rules_by_key.get(key, []):
            if not rule.should_trigger(value, scenario_time):
                continue
            if rule.cooldown > 0.0 and scenario_time - rule.last_fired < rule.cooldown:
                continue
            if self._execute_action(rule, value):
                rule.last_fired = scenario_time
                self.log_performance(
                    'automation_action',
                    f'{rule.source_plugin}:{rule.metric}:{rule.mode}:{value}',
                )

    def _execute_action(self, rule: AutomationRule, value: object) -> bool:
        if self.scheduler is None:
            return False
        payload = self._render_payload(rule, value)
        event = Event(0, int(self.scenario_time), rule.target_plugin, [rule.command, payload])
        try:
            self.scheduler.execute_one_event(event)
        except Exception:
            return False
        return True

    def _render_payload(self, rule: AutomationRule, value: object) -> str:
        context = {
            'mode': rule.mode,
            'value': value,
            'metric': rule.metric,
            'plugin': rule.source_plugin,
            'threshold': rule.raw_threshold,
            'time': f'{self.scenario_time:.3f}',
        }
        template = rule.payload_template or '{mode}'
        try:
            return template.format(**context)
        except Exception:
            return template

    def _split(self, payload: str, min_parts: int) -> Optional[List[str]]:
        if not payload:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < min_parts:
            return None
        return parts


