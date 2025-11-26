# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass
class TaskMetric:
    weight: float = 0.25
    baseline_mean: Optional[float] = None
    cumulative_value: float = 0.0
    sample_count: int = 0

    def add(self, value: float) -> None:
        self.cumulative_value += value
        self.sample_count += 1

    def mean(self) -> float:
        if self.sample_count == 0:
            return 0.0
        return self.cumulative_value / self.sample_count

    def z_score(self) -> float:
        mean_value = self.mean()
        if self.baseline_mean is None:
            return mean_value
        return mean_value - self.baseline_mean


class Compositescore(AbstractPlugin):
    """Aggregates task metrics into a composite multitasking score."""

    def __init__(self, label: str = '', taskplacement: str = 'bottomleft', taskupdatetime: int = 1000) -> None:
        super().__init__(label or _('Composite Score'), taskplacement, taskupdatetime)
        self.parameters.update({'tasks': 'track,sysmon,communications,resman'})
        self.baseline_active = False
        self.metrics: Dict[str, TaskMetric] = {}
        self.composite_score = 0.0
        self._widget: Optional[Simpletext] = None

    def start(self) -> None:
        self._initialise_metrics()
        super().start()

    def create_widgets(self) -> None:
        super().create_widgets()
        self._widget = self.add_widget(
            'score',
            Simpletext,
            container=self.task_container,
            text=_('Composite score pending...'),
            font_size=F['SMALL'],
            y=0.6,
            wrap_width=0.95,
            color=C['WHITE'],
        )

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        return True

    # Scenario commands -------------------------------------------------
    def baseline(self, payload: str) -> None:
        action = payload.strip().lower()
        if action == 'start':
            self.baseline_active = True
            for metric in self.metrics.values():
                metric.cumulative_value = 0.0
                metric.sample_count = 0
            self.log_performance('composite_baseline', 'start')
        elif action == 'stop':
            self.baseline_active = False
            for metric in self.metrics.values():
                metric.baseline_mean = metric.mean()
                metric.cumulative_value = 0.0
                metric.sample_count = 0
            self.log_performance('composite_baseline', 'stop')

    def weights(self, payload: str) -> None:
        for part in payload.split(','):
            if '=' not in part:
                continue
            task, value = part.split('=', 1)
            task = task.strip().lower()
            if task not in self.metrics:
                continue
            try:
                weight = float(value)
            except ValueError:
                continue
            self.metrics[task].weight = max(0.0, weight)
        total = sum(metric.weight for metric in self.metrics.values())
        if total > 0:
            for metric in self.metrics.values():
                metric.weight /= total
        self.log_performance(
            'composite_weights',
            ';'.join(f'{name}:{metric.weight:.2f}' for name, metric in self.metrics.items()),
        )

    def ingest(self, payload: str) -> None:
        parts = [p.strip() for p in payload.split(',') if p.strip()]
        if len(parts) < 2:
            return
        task_key = parts[0].lower()
        if task_key not in self.metrics:
            return
        try:
            value = float(parts[1])
        except ValueError:
            return
        self.metrics[task_key].add(value)
        self._recompute_score()
        self.log_performance('composite_ingest', f'{task_key}:{value}')

    def reset(self, payload: str) -> None:
        self._initialise_metrics()
        self.composite_score = 0.0
        self.log_performance('composite_reset', '1')

    # Helpers -----------------------------------------------------------
    def _initialise_metrics(self) -> None:
        tasks = [task.strip().lower() for task in self.parameters['tasks'].split(',') if task.strip()]
        if not tasks:
            tasks = ['track', 'sysmon', 'communications', 'resman']
        weight = 1.0 / len(tasks)
        self.metrics = {task: TaskMetric(weight=weight) for task in tasks}

    def _recompute_score(self) -> None:
        score = 0.0
        for metric in self.metrics.values():
            score += metric.weight * metric.z_score()
        self.composite_score = score
        self.log_performance('composite_score', round(self.composite_score, 3))

    def _update_widget(self) -> None:
        if self._widget is None:
            return
        lines = [(_('Composite score: {0:.3f}').format(self.composite_score))]
        for task, metric in self.metrics.items():
            baseline = metric.baseline_mean if metric.baseline_mean is not None else _('n/a')
            lines.append(f'{task}: mean={metric.mean():.3f}, weight={metric.weight:.2f}, baseline={baseline}')
        self._widget.set_text('\n'.join(lines))
