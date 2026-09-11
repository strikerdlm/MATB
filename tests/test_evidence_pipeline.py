import hashlib
import io
import json

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pathlib import Path

from matb_integration.evidence.contracts import canonical_bytes, strict_json
from matb_integration.evidence.reference import synthetic_capture
from matb_integration.evidence.reconcile import reconcile, iter_jsonl, parse_capture


def replace_stream(bundle, role, records):
    bundle = dict(bundle)
    bundle[role] = b"".join(canonical_bytes(r) for r in records)
    manifest = strict_json(bundle["capture_manifest"])
    manifest["artifacts"][role].update(sha256=hashlib.sha256(bundle[role]).hexdigest(), size_bytes=len(bundle[role]), records=len(records))
    bundle["capture_manifest"] = canonical_bytes(manifest)
    return bundle


def test_complete_reference_reconciles_every_classic_task_and_schema(tmp_path):
    bundle = synthetic_capture(tmp_path)
    result = reconcile(bundle)
    assert result["issues"] == []
    metrics = {m["metric"]: m for m in result["metrics"]}
    assert metrics["nasatlx_rtlx_mean_0_100"]["value"] == 40
    assert metrics["track_rmse_deviation"]["value"] == pytest.approx(2.8868)
    assert metrics["resman_mean_absolute_deviation"]["value"] == 10
    assert metrics["sysmon_hit_rate"]["value"] == 1
    assert metrics["sysmon_dprime_observed_v2"]["confirmatory_eligible"]
    assert not metrics["comm_d_prime"]["confirmatory_eligible"]
    assert "physical_audio_onset_not_qualified" in metrics["comm_d_prime"]["exclusion_reasons"]
    assert all(m["source_event_ids"] and m["source_observation_ids"] for m in metrics.values())
    assert result == reconcile(bundle)
    for role, schema in (("events", "scientific-event-v3"), ("timing", "timing-observation-v1")):
        validator = Draft202012Validator(json.loads((Path(__file__).parents[1] / f"docs/contracts/{schema}.schema.json").read_text()), format_checker=FormatChecker())
        for record in iter_jsonl(io.BytesIO(bundle[role])):
            validator.validate(record)


def test_tracking_only_has_no_sysmon_requirement_and_practice_is_excluded(tmp_path):
    result = reconcile(synthetic_capture(tmp_path, tasks=("track",), purpose="practice"))
    assert result["issues"] == []
    metrics = {m["metric"]: m for m in result["metrics"]}
    assert metrics["sysmon_hit_rate"]["status"] == "not_applicable"
    assert metrics["track_rmse_deviation"]["status"] == "succeeded"
    assert metrics["track_rmse_deviation"]["exclusion_reasons"] == ["non_study_capture"]


def test_interrupted_capture_remains_inspectable_and_ineligible(tmp_path):
    result = reconcile(synthetic_capture(tmp_path, completion="interrupted"))
    assert result["status"] == "failed"
    assert all(not m["confirmatory_eligible"] for m in result["metrics"])
    assert result["metrics"][0]["source_event_ids"]


def test_missing_timing_and_duplicate_events_are_not_repaired(tmp_path):
    bundle = synthetic_capture(tmp_path)
    timing = list(iter_jsonl(io.BytesIO(bundle["timing"])))
    broken = replace_stream(bundle, "timing", timing[1:])
    assert "missing_or_duplicate_software_receipt" in {i["code"] for i in reconcile(broken)["issues"]}
    events = list(iter_jsonl(io.BytesIO(bundle["events"])))
    broken = replace_stream(bundle, "events", events[:4] + [events[3]] + events[4:])
    assert "duplicate_event" in {i["code"] for i in reconcile(broken)["issues"]}
    assert all(not m["confirmatory_eligible"] for m in reconcile(broken)["metrics"])


def test_integrity_and_truncated_jsonl_rejected(tmp_path):
    bundle = synthetic_capture(tmp_path)
    with pytest.raises(ValueError, match="integrity"):
        parse_capture({**bundle, "events": bundle["events"] + b"\n"})
    with pytest.raises(ValueError, match="incomplete"):
        list(iter_jsonl(io.BytesIO(b'{"a":1}')))
    with pytest.raises(ValueError, match="duplicate JSON"):
        list(iter_jsonl(io.BytesIO(b'{"a":1,"a":2}\n')))


def test_missing_actor_excludes_sysmon_but_preserves_tracking(tmp_path):
    bundle = synthetic_capture(tmp_path)
    events = list(iter_jsonl(io.BytesIO(bundle["events"])))
    event = next(e for e in events if e["event_type"] == "sysmon.opportunity.closed")
    op = event["payload"]["opportunity"]
    op.pop("response_actor")
    event["payload"]["value"] = canonical_bytes(op).decode().strip()
    result = reconcile(replace_stream(bundle, "events", events))
    metrics = {m["metric"]: m for m in result["metrics"]}
    assert not metrics["sysmon_hit_rate"]["confirmatory_eligible"]
    assert "missing_opportunity_actor" in metrics["sysmon_hit_rate"]["exclusion_reasons"]
    assert metrics["track_rmse_deviation"]["confirmatory_eligible"]


def test_sample_interval_boundaries_and_invalid_values_are_excluded(tmp_path):
    bundle = synthetic_capture(tmp_path, tasks=("track",))
    events = list(iter_jsonl(io.BytesIO(bundle["events"])))
    sample = next(e for e in events if e["event_type"] == "track.sample" and e["payload"]["address"] == "cursor_in_target")
    sample["payload"]["value"] = "not-a-state"
    result = reconcile(replace_stream(bundle, "events", events))
    assert "invalid_task_sample" in {i["code"] for i in result["issues"]}
    assert all(not m["confirmatory_eligible"] for m in result["metrics"])
    events = list(iter_jsonl(io.BytesIO(bundle["events"])))
    stopped = next(e for e in events if e["event_type"] == "track.task.stopped")
    stopped["scenario_time_ns"] = 6_000_000_000
    result = reconcile(replace_stream(bundle, "events", events))
    assert "sample_gap_at_interval_end" in {i["code"] for i in result["issues"]}


def test_manifest_binding_and_orphan_observation_cannot_confer_eligibility(tmp_path):
    from uuid import uuid4
    from matb_integration.contracts import TimingObservationV1
    bundle = synthetic_capture(tmp_path)
    manifest = strict_json(bundle["capture_manifest"])
    scenario = strict_json(bundle["scenario_manifest"])
    scenario["participant_id"] = "P02"
    bundle["scenario_manifest"] = canonical_bytes(scenario)
    manifest["artifacts"]["scenario_manifest"].update(sha256=hashlib.sha256(bundle["scenario_manifest"]).hexdigest(), size_bytes=len(bundle["scenario_manifest"]))
    bundle["capture_manifest"] = canonical_bytes(manifest)
    result = reconcile(bundle)
    assert {"manifest_identity_mismatch", "runtime_manifest_binding_mismatch"} <= {i["code"] for i in result["issues"]}
    timing = list(iter_jsonl(io.BytesIO(bundle["timing"])))
    orphan = TimingObservationV1.create(session_id=manifest["session_id"], event_id=uuid4(), observation_index=0,
        kind="software_receipt", clock_id="python.perf_counter", value=1, unit="ns", evidence_source="software", method="software_clock")
    result = reconcile(replace_stream(bundle, "timing", [*timing, orphan.to_record()]))
    assert "orphan_timing_observation" in {i["code"] for i in result["issues"]}


def test_prepared_metadata_precedes_admission_without_false_gaps(tmp_path, monkeypatch):
    from matb_integration.evidence.writer import EvidenceWriter
    original = EvidenceWriter.lifecycle
    def lifecycle(writer, phase, scenario_time, observed_ns, completion=None):
        if phase == 'started':
            original(writer, 'prepared', 0, 1)
            writer.record({'type':'manual','module':'','address':'','value':'preflight metadata','scenario_time':0},
                {'recorded_monotonic_ns':2})
        original(writer,phase,scenario_time,observed_ns,completion)
    monkeypatch.setattr(EvidenceWriter,'lifecycle',lifecycle)
    result = reconcile(synthetic_capture(tmp_path))
    assert result['issues']==[]
    assert next(m for m in result['metrics'] if m['metric']=='sysmon_hit_rate')['value']==1


@pytest.mark.parametrize('record_type,module',[('input','sysmon'),('performance','track'),('unknown_observation','')])
def test_prepared_prefix_rejects_task_or_unknown_observations(tmp_path,monkeypatch,record_type,module):
    from matb_integration.evidence.writer import EvidenceWriter
    original=EvidenceWriter.lifecycle
    def lifecycle(writer,phase,scenario_time,observed_ns,completion=None):
        if phase=='started':
            original(writer,'prepared',0,1)
            writer.record({'type':record_type,'module':module,'address':'unexpected','value':1,'scenario_time':0}, {'recorded_monotonic_ns':2})
        original(writer,phase,scenario_time,observed_ns,completion)
    monkeypatch.setattr(EvidenceWriter,'lifecycle',lifecycle)
    result=reconcile(synthetic_capture(tmp_path))
    assert 'task_observation_before_admission' in {issue['code'] for issue in result['issues']}
