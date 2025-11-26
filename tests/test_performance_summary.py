"""Unit tests for the performance summary utilities."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[1] / 'core' / 'performance_summary.py'
    spec = importlib.util.spec_from_file_location('core_performance_summary', module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError('Unable to load performance_summary module')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_performance_module = _load_module()
MetricSummary = _performance_module.MetricSummary
PerformanceAggregator = _performance_module.PerformanceAggregator


def test_metric_summary_tracks_numeric_and_categorical_values() -> None:
    summary = MetricSummary(max_categories=3)
    summary.add(100)
    summary.add(200)
    summary.add('alpha')
    summary.add('beta')
    summary.add('alpha')
    summary.add(True)

    report = summary.as_report()
    assert report['count'] == 6
    numeric = report['numeric']
    assert numeric['count'] == 2
    assert numeric['min'] == 100
    assert numeric['max'] == 200
    assert report['categorical']['total'] == 4
    categorical_values = {entry['value']: entry['count'] for entry in report['categorical']['values']}
    assert categorical_values['alpha'] == 2
    assert categorical_values['beta'] == 1
    assert categorical_values['True'] == 1


def test_performance_aggregator_emits_domain_kpis() -> None:
    agg = PerformanceAggregator()
    agg.reset({'scenario': 'test'})
    agg.update_scenario_time(30.5)

    agg.record('MissionDirector', 'mission_assign', 'uav1:launch')
    agg.record('MissionDirector', 'mission_assign', 'uav2:launch')
    agg.record('MissionDirector', 'mission_complete', 'uav1')
    agg.record('MissionDirector', 'mission_alert', 'uav1:geofence')
    agg.record('SenseAndAvoid', 'saa_spawn', 'intr1')
    agg.record('SenseAndAvoid', 'saa_resolve', 'intr1:turn')
    agg.record('SenseAndAvoid', 'saa_overdue', 'intr2')
    agg.record('Datalink', 'datalink_receive', 'msg1')
    agg.record('Datalink', 'datalink_ack', 'msg1:ATC:1.2')
    agg.record('Datalink', 'datalink_drop', 'msg2')

    summary = agg.build_summary()
    mission = summary['modules']['missiondirector']['derived']
    assert mission['baseline'] == 2
    assert mission['completion_rate'] == 0.5
    saa = summary['modules']['senseandavoid']['derived']
    assert saa['baseline'] == 1
    assert saa['resolution_rate'] == 1.0
    datalink = summary['modules']['datalink']['derived']
    assert datalink['baseline'] == 1
    assert datalink['ack_rate'] == 1.0
    assert datalink['drop_rate'] == 1.0
    assert summary['scenario_seconds'] == 30.5
