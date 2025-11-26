"""Performance summary aggregation utilities.

This module implements mission-level KPI summaries described in
``Docs/Manual.md`` and ties them to the military assessment literature
(e.g., ``research/Multi Attribute Task Battery for Military Aircrew Assessment A Comprehensive Research Report.md``).
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

Number = float | int


@dataclass(slots=True)
class NumericStats:
    """Aggregates numeric samples without retaining the full history."""

    count: int = 0
    sum_value: float = 0.0
    min_value: float = math.inf
    max_value: float = -math.inf
    last_value: float = 0.0

    def add(self, value: float) -> None:
        """Record a numeric observation."""
        self.count += 1
        self.sum_value += value
        if value < self.min_value:
            self.min_value = value
        if value > self.max_value:
            self.max_value = value
        self.last_value = value

    def as_dict(self) -> Dict[str, float]:
        """Expose aggregate statistics."""
        if self.count == 0:
            raise ValueError('NumericStats has no data')
        mean_value = self.sum_value / self.count
        return {
            'mean': mean_value,
            'last': self.last_value,
            'min': self.min_value,
            'max': self.max_value,
            'count': self.count,
        }


@dataclass(slots=True)
class CategoryStats:
    """Counts categorical samples with a bounded dictionary."""

    max_entries: int
    counts: Dict[str, int] = field(default_factory=dict)
    overflow: int = 0

    def add(self, value: str) -> None:
        """Record a categorical observation with truncation safeguards."""
        key = value if len(value) <= 64 else f"{value[:61]}..."
        if key in self.counts:
            self.counts[key] += 1
            return
        if len(self.counts) < self.max_entries:
            self.counts[key] = 1
        else:
            self.overflow += 1

    @property
    def total(self) -> int:
        return sum(self.counts.values()) + self.overflow

    def as_list(self) -> List[Dict[str, Any]]:
        """Expose sorted counts for reporting."""
        ordered = sorted(self.counts.items(), key=lambda item: (-item[1], item[0]))
        report = [{'value': key, 'count': count} for key, count in ordered]
        if self.overflow:
            report.append({'value': '__other__', 'count': self.overflow})
        return report


@dataclass(slots=True)
class MetricSummary:
    """Tracks numeric and categorical snapshots for a single metric."""

    max_categories: int
    numeric: NumericStats = field(default_factory=NumericStats)
    categorical: CategoryStats = field(init=False)

    def __post_init__(self) -> None:
        self.categorical = CategoryStats(max_entries=self.max_categories)

    def add(self, value: Any) -> None:
        """Record a new value, routing to numeric or categorical buckets."""
        if isinstance(value, bool):
            self.categorical.add(str(value))
            return
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            as_float = float(value)
            if math.isfinite(as_float):
                self.numeric.add(as_float)
                return
        self.categorical.add(str(value))

    def total_count(self) -> int:
        return self.numeric.count + self.categorical.total

    def has_data(self) -> bool:
        return self.total_count() > 0

    def as_report(self) -> Dict[str, Any]:
        report: Dict[str, Any] = {'count': self.total_count()}
        if self.numeric.count > 0:
            report['numeric'] = self.numeric.as_dict()
        if self.categorical.total > 0:
            report['categorical'] = {
                'total': self.categorical.total,
                'values': self.categorical.as_list(),
            }
        return report


class PerformanceAggregator:
    """Collects per-metric summaries and emits mission-level KPIs."""

    def __init__(self, max_categories: int = 8) -> None:
        self._max_categories = max(1, max_categories)
        self._modules: Dict[str, Dict[str, MetricSummary]] = {}
        self._scenario_started_at: Optional[float] = None
        self._metadata: Dict[str, Any] = {}
        self._scenario_duration: float = 0.0

    def reset(self, metadata: Optional[Mapping[str, Any]] = None) -> None:
        """Clear collected statistics and set the metadata context."""
        self._modules.clear()
        self._scenario_started_at = time.monotonic()
        self._scenario_duration = 0.0
        self._metadata = dict(metadata) if metadata else {}

    def update_scenario_time(self, scenario_time: float) -> None:
        """Track the furthest scenario timestamp observed."""
        self._scenario_duration = max(self._scenario_duration, scenario_time)

    def record(self, module: str, metric: str, value: Any) -> None:
        """Record a metric emitted by ``log_performance``."""
        if not module or not metric:
            return
        module_key = module.lower()
        metric_key = metric.lower()
        module_store = self._modules.setdefault(module_key, {})
        summary = module_store.setdefault(metric_key, MetricSummary(self._max_categories))
        summary.add(value)

    def build_summary(self) -> Dict[str, Any]:
        """Assemble the JSON-serialisable payload."""
        modules_report: Dict[str, Any] = {}
        for module_name, metrics in self._modules.items():
            metric_reports = {
                metric: summary.as_report()
                for metric, summary in metrics.items()
                if summary.has_data()
            }
            derived = self._build_domain_metrics(module_name, metrics)
            module_payload: Dict[str, Any] = {'metrics': metric_reports}
            if derived:
                module_payload['derived'] = derived
            modules_report[module_name] = module_payload

        started_at = None
        if self._scenario_started_at is not None:
            started_at = datetime.fromtimestamp(
                self._scenario_started_at,
                tz=timezone.utc,
            ).isoformat()

        summary = {
            'generated_at': datetime.now(tz=timezone.utc).isoformat(),
            'scenario_seconds': round(self._scenario_duration, 3),
            'started_at': started_at,
            'metadata': self._metadata,
            'modules': modules_report,
        }
        return summary

    def export(self, path: Path) -> Path:
        """Write the JSON summary to ``path``."""
        summary = self.build_summary()
        if not summary['modules']:
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', encoding='utf-8') as handle:
            json.dump(summary, handle, indent=2, sort_keys=True)
        return path

    # ------------------------------------------------------------------
    def _build_domain_metrics(
        self,
        module_name: str,
        metrics: Mapping[str, MetricSummary],
    ) -> Dict[str, Any]:
        builders = {
            'missiondirector': self._missiondirector_kpis,
            'senseandavoid': self._senseandavoid_kpis,
            'payloadmanager': self._payloadmanager_kpis,
            'datalink': self._datalink_kpis,
            'threatboard': self._threatboard_kpis,
            'energymanager': self._energymanager_kpis,
        }
        builder = builders.get(module_name)
        return builder(metrics) if builder else {}

    def _missiondirector_kpis(self, metrics: Mapping[str, MetricSummary]) -> Dict[str, Any]:
        assigns = self._count(metrics.get('mission_assign'))
        completes = self._count(metrics.get('mission_complete'))
        alerts = self._count(metrics.get('mission_alert'))
        return self._ratio_payload(assigns, completes, alerts)

    def _senseandavoid_kpis(self, metrics: Mapping[str, MetricSummary]) -> Dict[str, Any]:
        spawns = self._count(metrics.get('saa_spawn'))
        resolves = self._count(metrics.get('saa_resolve'))
        overdue = self._count(metrics.get('saa_overdue'))
        return self._ratio_payload(spawns, resolves, overdue, 'resolution_rate')

    def _payloadmanager_kpis(self, metrics: Mapping[str, MetricSummary]) -> Dict[str, Any]:
        activates = self._count(metrics.get('payload_activate'))
        overbandwidth = self._count(metrics.get('payload_overbandwidth'))
        depleted = self._count(metrics.get('payload_depleted'))
        return self._ratio_payload(activates, overbandwidth, depleted, 'overbandwidth_rate')

    def _datalink_kpis(self, metrics: Mapping[str, MetricSummary]) -> Dict[str, Any]:
        received = self._count(metrics.get('datalink_receive'))
        acknowledgements = self._count(metrics.get('datalink_ack'))
        misses = self._count(metrics.get('datalink_miss'))
        drops = self._count(metrics.get('datalink_drop'))
        kpis = self._ratio_payload(received, acknowledgements, misses, 'ack_rate')
        if received:
            kpis['drop_rate'] = round(drops / received, 3)
        return kpis

    def _threatboard_kpis(self, metrics: Mapping[str, MetricSummary]) -> Dict[str, Any]:
        spawns = self._count(metrics.get('threat_spawn'))
        resolves = self._count(metrics.get('threat_resolve'))
        overdue = self._count(metrics.get('threat_overdue'))
        engages = self._count(metrics.get('threat_engage'))
        payload = self._ratio_payload(spawns, resolves, overdue, 'resolution_rate')
        if spawns:
            payload['engagement_rate'] = round(engages / spawns, 3)
        return payload

    def _energymanager_kpis(self, metrics: Mapping[str, MetricSummary]) -> Dict[str, Any]:
        events = self._count(metrics.get('energy_event_start'))
        overg = self._count(metrics.get('energy_overg'))
        alerts = self._count(metrics.get('energy_alert'))
        if not events:
            return {}
        return {
            'event_count': events,
            'overg_rate': round(overg / events, 3),
            'alert_rate': round(alerts / events, 3),
        }

    @staticmethod
    def _count(summary: Optional[MetricSummary]) -> int:
        return summary.total_count() if summary and summary.has_data() else 0

    @staticmethod
    def _ratio_payload(
        baseline: int,
        positive: int,
        negatives: int,
        label: str = 'completion_rate',
    ) -> Dict[str, Any]:
        if not baseline:
            return {}
        payload = {
            'baseline': baseline,
            label: round(positive / baseline, 3),
            'violations': negatives,
        }
        return payload
