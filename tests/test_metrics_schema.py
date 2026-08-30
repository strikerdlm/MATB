from __future__ import annotations

import pytest

from matb_integration.metrics_schema import (
    LONG_METRIC_IDS,
    METRICS_SCHEMA_VERSION,
    METRICS_SPEC,
    metric_definition,
    long_metric_definition,
)


def test_metrics_registry_is_v2_and_contains_corrected_and_legacy_metrics():
    assert METRICS_SCHEMA_VERSION == "2.0"
    assert "nasatlx.rtlx_mean_0_100" in METRICS_SPEC["metrics"]
    assert metric_definition("sysmon.dprime_observed_v2")["confirmatory_eligible"] is True
    assert metric_definition("sysmon.dprime_estimated_v1")["confirmatory_eligible"] is False


def test_every_definition_has_a_complete_scientific_contract():
    required = {
        "metric_version", "unit", "equation", "required_inputs",
        "missing_policy", "directionality", "measurement_basis",
        "confirmatory_eligible", "references",
    }
    for metric_id, definition in METRICS_SPEC["metrics"].items():
        assert required <= set(definition), metric_id
        assert definition["references"], metric_id


def test_every_long_metric_resolves_to_the_normative_registry():
    assert len(LONG_METRIC_IDS) == 15
    for key, metric_id in LONG_METRIC_IDS.items():
        definition = long_metric_definition(key)
        assert definition["metric_id"] == metric_id


def test_unknown_metric_definition_fails_closed():
    with pytest.raises(KeyError, match="unknown scientific metric"):
        metric_definition("unknown.metric")
