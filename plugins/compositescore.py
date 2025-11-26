# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

"""Composite Score plugin for multitasking efficiency measurement.

This plugin implements a standardised composite scoring methodology based on
USAARL MATB research. It aggregates performance across all active subtasks
and normalises scores to enable cross-subject comparison.

Scenario commands:
    compositescore;start
    compositescore;weights;track=0.25,sysmon=0.25,communications=0.25,resman=0.25
    compositescore;baseline;start|stop
    compositescore;stop

Performance metrics emitted:
    composite_score, composite_efficiency, composite_baseline, task_weights
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass
class TaskMetrics:
    """Accumulated metrics for a single task."""

    task_name: str
    weight: float = 0.25
    raw_scores: List[float] = field(default_factory=list)
    baseline_mean: Optional[float] = None
    baseline_std: Optional[float] = None

    def add_score(self, score: float) -> None:
        self.raw_scores.append(score)

    def current_mean(self) -> float:
        if not self.raw_scores:
            return 0.0
        return sum(self.raw_scores) / len(self.raw_scores)

    def z_score(self, value: float) -> float:
        """Compute z-score relative to baseline."""
        if self.baseline_mean is None or self.baseline_std is None or self.baseline_std == 0:
            return 0.0
        return (value - self.baseline_mean) / self.baseline_std

    def set_baseline(self, mean: float, std: float) -> None:
        self.baseline_mean = mean
        self.baseline_std = std


@dataclass
class CompositeResult:
    """Snapshot of composite scoring at a point in time."""

    timestamp: float
    weighted_score: float
    efficiency_index: float
    task_contributions: Dict[str, float] = field(default_factory=dict)


class Compositescore(AbstractPlugin):
    """Aggregates performance metrics into a composite multitasking score."""

    def __init__(
        self,
        label: str = '',
        taskplacement: str = 'bottomright',
        taskupdatetime: int = 2000,
    ) -> None:
        super().__init__(label or _('Composite Score'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'normalisationmethod': validation.is_string,
            'windowseconds': validation.is_positive_integer,
            'emitinterval': validation.is_positive_integer,
        }

        self.parameters.update({
            'normalisationmethod': 'zscore',  # zscore, minmax, raw
            'windowseconds': 30,
            'emitinterval': 10,
        })

        self._default_weights: Dict[str, float] = {
            'track': 0.25,
            'sysmon': 0.25,
            'communications': 0.25,
            'resman': 0.25,
        }

        self.task_metrics: Dict[str, TaskMetrics] = {}
        self.results_history: List[CompositeResult] = []
        self._baseline_active: bool = False
        self._baseline_scores: Dict[str, List[float]] = {}
        self._last_emit_time: float = 0.0
        self._widget: Optional[Simpletext] = None
        self._score_widget: Optional[Simpletext] = None

    def start(self) -> None:
        self._initialise_metrics()
        super().start()

    def create_widgets(self) -> None:
        super().create_widgets()
        self._widget = self.add_widget(
            'header',
            Simpletext,
            container=self.task_container,
            text=_('Composite Performance'),
            font_size=F['SMALL'],
            y=0.9,
            color=C['WHITE'],
            bold=True,
        )
        self._score_widget = self.add_widget(
            'scores',
            Simpletext,
            container=self.task_container,
            text=_('Collecting data…'),
            font_size=F['SMALL'],
            y=0.6,
            wrap_width=0.9,
            color=C['WHITE'],
        )

    def compute_next_plugin_state(self) -> bool:
        self._collect_scores()
        self._maybe_emit_composite()
        return super().compute_next_plugin_state()

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_display()
        return True

    # Scenario commands -------------------------------------------------
    def weights(self, payload: str) -> None:
        """Set task weights: track=0.3,sysmon=0.2,..."""
        parts = [p.strip() for p in payload.split(',')]
        for part in parts:
            if '=' not in part:
                continue
            key, value = part.split('=', 1)
            key = key.strip().lower()
            try:
                weight = float(value.strip())
            except ValueError:
                continue
            if key in self.task_metrics:
                self.task_metrics[key].weight = max(0.0, min(1.0, weight))
        self._normalise_weights()
        self.log_performance('task_weights', self._weights_string())

    def baseline(self, payload: str) -> None:
        """Start or stop baseline collection."""
        action = payload.strip().lower()
        if action == 'start':
            self._baseline_active = True
            self._baseline_scores = {name: [] for name in self.task_metrics}
            self.log_performance('composite_baseline', 'start')
        elif action == 'stop':
            self._finalise_baseline()
            self._baseline_active = False
            self.log_performance('composite_baseline', 'stop')

    def inject(self, payload: str) -> None:
        """Manually inject a score: task_name,score_value."""
        parts = [p.strip() for p in payload.split(',')]
        if len(parts) < 2:
            return
        task_name = parts[0].lower()
        try:
            score = float(parts[1])
        except ValueError:
            return
        if task_name in self.task_metrics:
            self.task_metrics[task_name].add_score(score)
            if self._baseline_active:
                self._baseline_scores.setdefault(task_name, []).append(score)

    # Internal methods --------------------------------------------------
    def _initialise_metrics(self) -> None:
        self.task_metrics = {
            name: TaskMetrics(task_name=name, weight=weight)
            for name, weight in self._default_weights.items()
        }
        self.results_history = []
        self._baseline_scores = {}
        self._baseline_active = False

    def _normalise_weights(self) -> None:
        total = sum(m.weight for m in self.task_metrics.values())
        if total <= 0:
            return
        for metrics in self.task_metrics.values():
            metrics.weight = metrics.weight / total

    def _weights_string(self) -> str:
        parts = [f'{name}={m.weight:.2f}' for name, m in self.task_metrics.items()]
        return ','.join(parts)

    def _collect_scores(self) -> None:
        """Gather latest scores from scheduler's plugin instances."""
        if self.scheduler is None:
            return

        for plugin in self.scheduler.plugins.values():
            alias = plugin.alias.lower()
            if alias not in self.task_metrics:
                continue
            if not hasattr(plugin, 'performance'):
                continue
            # Aggregate latest performance values
            perf = plugin.performance
            score = self._extract_score(alias, perf)
            if score is not None:
                self.task_metrics[alias].add_score(score)
                if self._baseline_active:
                    self._baseline_scores.setdefault(alias, []).append(score)

    def _extract_score(self, task_name: str, perf: Dict[str, List[float]]) -> Optional[float]:
        """Extract a representative score from a plugin's performance dict."""
        # Task-specific extraction logic
        if task_name == 'track':
            # RMSE is lower-is-better; invert for composite
            if 'RMSE' in perf and perf['RMSE']:
                rmse = perf['RMSE'][-1]
                return max(0.0, 100.0 - rmse)
        elif task_name == 'sysmon':
            # Count correct responses
            correct = sum(1 for v in perf.get('correct', []) if v)
            total = len(perf.get('correct', [])) or 1
            return (correct / total) * 100.0
        elif task_name == 'communications':
            # Accuracy percentage
            if 'accuracy' in perf and perf['accuracy']:
                return perf['accuracy'][-1] * 100.0
        elif task_name == 'resman':
            # Deviation from target (lower is better)
            if 'deviation' in perf and perf['deviation']:
                dev = perf['deviation'][-1]
                return max(0.0, 100.0 - abs(dev))
        return None

    def _finalise_baseline(self) -> None:
        """Compute baseline statistics from collected scores."""
        for name, scores in self._baseline_scores.items():
            if not scores or name not in self.task_metrics:
                continue
            mean = sum(scores) / len(scores)
            variance = sum((s - mean) ** 2 for s in scores) / len(scores) if len(scores) > 1 else 1.0
            std = math.sqrt(variance) if variance > 0 else 1.0
            self.task_metrics[name].set_baseline(mean, std)

    def _maybe_emit_composite(self) -> None:
        interval = float(self.parameters['emitinterval'])
        if self.scenario_time - self._last_emit_time < interval:
            return
        self._last_emit_time = self.scenario_time

        result = self._compute_composite()
        if result is not None:
            self.results_history.append(result)
            self.log_performance('composite_score', round(result.weighted_score, 2))
            self.log_performance('composite_efficiency', round(result.efficiency_index, 2))

    def _compute_composite(self) -> Optional[CompositeResult]:
        contributions: Dict[str, float] = {}
        weighted_sum = 0.0
        method = self.parameters['normalisationmethod']

        for name, metrics in self.task_metrics.items():
            if not metrics.raw_scores:
                continue
            current = metrics.current_mean()
            if method == 'zscore' and metrics.baseline_mean is not None:
                normalised = metrics.z_score(current)
            elif method == 'minmax':
                # Simple 0-100 normalisation
                normalised = max(0.0, min(100.0, current)) / 100.0
            else:
                normalised = current

            contribution = normalised * metrics.weight
            contributions[name] = contribution
            weighted_sum += contribution

        if not contributions:
            return None

        # Efficiency index: ratio of actual to theoretical maximum
        max_possible = sum(m.weight * 100.0 for m in self.task_metrics.values())
        efficiency = (weighted_sum / max_possible) * 100.0 if max_possible > 0 else 0.0

        return CompositeResult(
            timestamp=self.scenario_time,
            weighted_score=weighted_sum,
            efficiency_index=efficiency,
            task_contributions=contributions,
        )

    def _update_display(self) -> None:
        if self._score_widget is None:
            return

        if not self.results_history:
            self._score_widget.set_text(_('Collecting data…'))
            return

        latest = self.results_history[-1]
        lines: List[str] = []
        lines.append(_('Composite Score: {:.1f}').format(latest.weighted_score))
        lines.append(_('Efficiency Index: {:.1f}%').format(latest.efficiency_index))
        lines.append('')
        for name, contrib in latest.task_contributions.items():
            lines.append(f'  {name}: {contrib:.2f}')

        self._score_widget.set_text('\n'.join(lines))

    def get_response_timers(self) -> Optional[List[int]]:
        """No overdue feedback for composite scoring."""
        return None

