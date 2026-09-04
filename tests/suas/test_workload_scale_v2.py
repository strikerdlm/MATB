"""Independent scale examples: six 0-10 ratings map to their mean x 10."""
import pytest
from matb_integration.suas.metrics.research import derive_research_metrics
from matb_integration.suas.recording.records import RecordKind, SessionRecord


def record(values):
    return SessionRecord("s", "LOW", 1, 0, "2026-09-04T00:00:00Z", 0,
                         RecordKind.QUESTIONNAIRE, {"instrument": "NASA_TLX",
                         "raw_tlx": sum(values.values()), "subscales": values})


def test_complete_unweighted_scale_and_preserved_legacy_sum():
    values = dict(zip(("mental_demand", "physical_demand", "temporal_demand",
                       "performance", "effort", "frustration"), (1, 2, 3, 4, 5, 9)))
    metric = derive_research_metrics([record(values)]).nasa_tlx
    assert metric["raw_tlx"] == 24
    assert metric["rtlx_0_100"] == pytest.approx(40)
    assert metric["metric_version"] == "unweighted-rtlx-v2"


def test_incomplete_questionnaire_has_no_normalized_score():
    metric = derive_research_metrics([record({"mental_demand": 10})]).nasa_tlx
    assert metric["rtlx_0_100"] is None
    assert metric["complete_count"] == 0
