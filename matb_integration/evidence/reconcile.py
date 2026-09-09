"""Pure, offline reconciliation and derivation. No database or GUI dependencies."""
from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from io import BytesIO
from typing import Any, BinaryIO, Iterator

from matb_integration.contracts import ScientificEventV3, TimingObservationV1
from matb_integration.log_converter import calculate_task_metrics, NASA_TLX_SUBSCALES, NASA_TLX_SUBSCALES_ES, NASA_TLX_SUBSCALE_ALIASES, ISA_TITLE, ISA_TITLE_ES, BEDFORD_TITLE
from matb_integration.metrics_schema import long_metric_definition, METRICS_SCHEMA_VERSION, METRICS_SPEC
from .contracts import (CaptureManifestV1, RuntimePayloadV1, canonical_bytes, strict_json,
                        opportunity_uuid, event_type, DERIVATION_VERSION,
                        MAX_STREAM_BYTES, MAX_JSONL_LINE_BYTES, MAX_STREAM_RECORDS, TASKS)

METRICS = {
    "sysmon_dprime_observed_v2": ("sysmon", "dprime_observed_v2"),
    "sysmon_hit_rate": ("sysmon", "hit_rate"),
    "sysmon_mean_rt_ms": ("sysmon", "mean_rt_ms"),
    "track_rmse_deviation": ("track", "rmse_deviation"),
    "track_percent_time_in_target": ("track", "percent_time_in_target"),
    "resman_mean_absolute_deviation": ("resman", "mean_absolute_deviation"),
    "resman_percent_time_in_tolerance": ("resman", "percent_time_in_tolerance"),
    "comm_d_prime": ("comm", "d_prime"),
    "nasatlx_rtlx_mean_0_100": ("nasatlx", "rtlx_mean_0_100"),
    "bedford": ("bedford", "value"), "isa_mean": ("isa", "mean"),
}
TASK_FOR = {"comm": "communications", "nasatlx": "genericscales", "bedford": "genericscales", "isa": "genericscales"}
TLX_TITLES = set(NASA_TLX_SUBSCALES) | set(NASA_TLX_SUBSCALES_ES) | set(NASA_TLX_SUBSCALE_ALIASES)


def iter_jsonl(stream: BinaryIO) -> Iterator[dict]:
    total = 0
    for index in range(MAX_STREAM_RECORDS + 1):
        line = stream.readline(MAX_JSONL_LINE_BYTES + 1)
        if not line:
            return
        total += len(line)
        if len(line) > MAX_JSONL_LINE_BYTES or total > MAX_STREAM_BYTES or index == MAX_STREAM_RECORDS:
            raise ValueError("evidence stream limit exceeded")
        if not line.endswith(b"\n") or not line.strip():
            raise ValueError(f"incomplete or blank JSONL record at line {index + 1}")
        value = strict_json(line)
        if not isinstance(value, dict):
            raise ValueError("JSONL records must be objects")
        yield value


def parse_capture(artifacts: dict[str, bytes]) -> tuple[CaptureManifestV1, dict, list[ScientificEventV3], list[TimingObservationV1]]:
    manifest = CaptureManifestV1.model_validate(strict_json(artifacts["capture_manifest"]))
    if manifest.completion == "recording":
        raise ValueError("capture must be finalized before ingestion")
    required = {"events", "timing", "scenario_manifest"}
    if not required <= artifacts.keys() or not required <= manifest.artifacts.keys():
        raise ValueError("event, timing and bound scenario manifest artifacts are required")
    for role, content in artifacts.items():
        if role == "capture_manifest":
            continue
        expected = manifest.artifacts.get(role)
        if expected is None or expected.sha256 != hashlib.sha256(content).hexdigest() or expected.size_bytes != len(content):
            raise ValueError(f"artifact integrity mismatch: {role}")
    scenario = strict_json(artifacts["scenario_manifest"])
    if not isinstance(scenario, dict):
        raise ValueError("scenario manifest must be an object")
    if scenario.get("manifest_version") not in {1, 2, 3} and not (
        scenario.get("schema_version") == "1.0" and isinstance(scenario.get("compiler"), dict)
    ):
        raise ValueError("unsupported scenario manifest version")
    events = [ScientificEventV3.from_record(row) for row in iter_jsonl(BytesIO(artifacts["events"]))]
    timing = [TimingObservationV1.from_record(row) for row in iter_jsonl(BytesIO(artifacts["timing"]))]
    for role, records in (("events", events), ("timing", timing)):
        if manifest.artifacts[role].records != len(records):
            raise ValueError(f"artifact record count mismatch: {role}")
    for event in events:
        payload = RuntimePayloadV1.model_validate(event.to_record()["payload"])
        if event.event_type != event_type(payload):
            raise ValueError("event type does not match native payload")
    return manifest, scenario, events, timing


def native_row(event: ScientificEventV3) -> dict[str, str]:
    payload = event.payload
    value = payload["value"]
    return {"scenario_time": str(event.scenario_time_ns / 1e9),
            "type": str(payload["record_type"]), "module": str(payload["module"]),
            "address": str(payload["address"]), "value": str(value)}


def reconcile(artifacts: dict[str, bytes]) -> dict[str, Any]:
    capture, scenario, events, observations = parse_capture(artifacts)
    issues: list[dict] = []

    def issue(code: str, task: str | None = None, ids: list[str] | None = None, detail: str = "") -> None:
        issues.append({"code": code, "task": task, "event_ids": ids or [], "detail": detail})

    if not events:
        issue("empty_event_stream")
    expected_scenario = (scenario.get("scenario") or {}).get("sha256")
    if expected_scenario is None:
        expected_scenario = (scenario.get("output") or {}).get("scenario_sha256")
    if expected_scenario != capture.scenario_sha256:
        issue("scenario_manifest_mismatch")
    for key, actual in (("participant_id", capture.participant_id), ("visit_ordinal", capture.visit_ordinal)):
        if scenario.get(key) is not None and scenario[key] != actual:
            issue("manifest_identity_mismatch", detail=key)
    condition = (scenario.get("parameters") or {}).get("suite_profile_name", scenario.get("workload_level"))
    if condition is not None and condition != capture.condition:
        issue("manifest_condition_mismatch")
    if capture.scenario_manifest_status != "verified":
        issue("unverified_scenario_manifest")
    if capture.completion != "completed":
        issue("interrupted_or_failed_block", detail=capture.completion)
    if events and (events[0].event_type != "block.started" or events[-1].event_type != "block.completed"):
        issue("incomplete_block_lifecycle")
    by_id: dict[str, ScientificEventV3] = {}
    task_events: dict[str, list[ScientificEventV3]] = defaultdict(list)
    last_time = -1
    for index, event in enumerate(events):
        eid = str(event.event_id)
        payload = event.payload
        task = event.task
        if eid in by_id:
            issue("duplicate_event", task, [eid])
        by_id[eid] = event
        if event.sequence != index:
            issue("event_sequence_gap_or_reorder", ids=[eid])
        if event.scenario_time_ns < last_time:
            issue("scenario_clock_regression", ids=[eid])
        last_time = event.scenario_time_ns
        if (str(event.session_id) != capture.session_id or payload["block_instance_id"] != capture.block_instance_id
                or str(event.correlation_id) != capture.block_instance_id or event.component_id != "matb-runtime"
                or event.scenario_sha256 != capture.scenario_sha256 or event.profile_id != capture.profile_id
                or event.source_commit != capture.source_commit or event.source_dirty != capture.source_dirty
                or event.component_version != capture.component_version):
            issue("event_manifest_mismatch", ids=[eid])
        expected_task = payload["module"] if payload["module"] in TASKS else None
        if task != expected_task or (task and task not in capture.tasks):
            issue("undeclared_or_mismatched_task", ids=[eid])
        native = payload.get("native_opportunity_id")
        expected_id = opportunity_uuid(capture.session_id, task or "", native) if native else None
        if event.opportunity_id != expected_id:
            issue("opportunity_identity_mismatch", task, [eid])
        op = payload.get("opportunity")
        if op:
            phase = op.get("phase")
            if phase not in {"rejected", "invalidated"}:
                if type(op.get("automation_active")) is not bool:
                    issue("missing_opportunity_allocation", task, [eid])
                actor_key = "response_actor" if phase == "closed" else "allocation_actor"
                if (task == "sysmon" or phase == "closed") and op.get(actor_key) not in {"participant", "automation"}:
                    issue("missing_opportunity_actor", task, [eid])
        if event.causation_id is not None and str(event.causation_id) not in by_id:
            issue("unresolved_causation", task, [eid])
        if task:
            task_events[task].append(event)
        if payload["record_type"] in {"event_dispatch_failure", "runtime_phase_failure", "scenario_clock_failure"}:
            issue("runtime_dispatch_failure", ids=[eid])

    timing_by_event: dict[str, list[TimingObservationV1]] = defaultdict(list)
    observation_ids = set()
    for obs in observations:
        eid = str(obs.event_id)
        if str(obs.observation_id) in observation_ids:
            issue("duplicate_timing_observation", by_id[eid].task if eid in by_id else None, [eid])
        observation_ids.add(str(obs.observation_id))
        if eid not in by_id or str(obs.session_id) != capture.session_id:
            issue("orphan_timing_observation", ids=[eid])
        if obs.clock_id not in capture.clocks:
            issue("undeclared_clock", ids=[eid])
        timing_by_event[eid].append(obs)
    previous_receipt = -1
    for event in events:
        eid = str(event.event_id)
        linked = timing_by_event[eid]
        receipts = [o for o in linked if o.kind == "software_receipt" and o.clock_id == "python.perf_counter"]
        if len(receipts) != 1:
            issue("missing_or_duplicate_software_receipt", event.task, [eid])
        elif receipts[0].value < previous_receipt:
            issue("software_clock_regression", ids=[eid])
        else:
            previous_receipt = receipts[0].value
        starts = [o.value for o in linked if o.kind == "dispatch_start" and o.clock_id == "python.perf_counter"]
        ends = [o.value for o in linked if o.kind == "dispatch_end" and o.clock_id == "python.perf_counter"]
        if (bool(starts) != bool(ends) or len(starts) > 1 or len(ends) > 1
                or (starts and ends and ends[0] < starts[0])):
            issue("invalid_dispatch_observations", event.task, [eid])
        indices = [o.observation_index for o in linked]
        if sorted(indices) != list(range(len(indices))):
            issue("timing_index_gap_or_duplicate", event.task, [eid])

    # Only event payloads reach the shared calculators. CSV cannot fill a gap.
    rows = [native_row(e) for e in events]
    manifest_bindings = [r for r in rows if r["type"] == "scenario_manifest_evidence"]
    if len(manifest_bindings) != 1:
        issue("missing_or_duplicate_runtime_manifest_binding")
    else:
        try:
            binding = strict_json(manifest_bindings[0]["value"])
            if (binding.get("status") != capture.scenario_manifest_status
                    or binding.get("scenario_manifest_sha256") != capture.artifacts["scenario_manifest"].sha256):
                issue("runtime_manifest_binding_mismatch")
        except (ValueError, AttributeError):
            issue("invalid_runtime_manifest_binding")
    expected = scenario.get("expected", {})
    for key in ("sysmon_target_opportunities", "sysmon_nontarget_opportunities", "comm_events"):
        value = expected.get(key)
        if value is not None and (type(value) is not int or value < 0):
            issue("invalid_planned_opportunity_count", detail=key)
            expected = {**expected, key: None}
    calculations = calculate_task_metrics(rows,
        expected_sysmon_target_opportunities=expected.get("sysmon_target_opportunities"),
        expected_sysmon_nontarget_opportunities=expected.get("sysmon_nontarget_opportunities"),
        expected_comm_opportunities=expected.get("comm_events"))
    for task, section in (("sysmon", "sysmon"), ("communications", "comm")):
        if task not in capture.tasks:
            continue
        calc = calculations[section]
        for problem in calc.get("observed_opportunity_issues", []):
            issue("opportunity_reconciliation", task, detail=problem)
        if not calc.get("observed_opportunity_reconciled"):
            issue("incomplete_opportunities", task)
        keys = ("sysmon_target_opportunities", "sysmon_nontarget_opportunities") if task == "sysmon" else ("comm_events",)
        if any(expected.get(key) is None for key in keys):
            issue("missing_planned_opportunity_counts", task)

    # Pair native continuous samples, detect gaps, and retain automation exposure.
    # Gap rule v1: >3 declared update intervals, within a continuous task run.
    for task in ("track", "resman"):
        if task not in capture.tasks:
            continue
        samples: dict[tuple[int, str], list[ScientificEventV3]] = defaultdict(list)
        previous: dict[str, tuple[int, int | float]] = {}
        required_channels = {"center_deviation", "cursor_in_target"} if task == "track" else set()
        active_start: int | None = None
        lifecycle_seen = False
        found = False

        def close_interval(at: int) -> None:
            if active_start is None or at <= active_start:
                return
            if not required_channels or not required_channels <= previous.keys():
                issue("missing_interval_samples", task)
            for _address, (last_sample, interval_ms) in previous.items():
                if at - last_sample > 3 * interval_ms * 1e6:
                    issue("sample_gap_at_interval_end", task)

        for event in task_events[task]:
            p = event.payload
            address = p["address"]
            if task == "resman" and p["record_type"] in {"parameter", "event"} and address.startswith("tank-") and address.endswith("-target"):
                tank = address.split("-")[1]
                channels = {f"{tank}_deviation", f"{tank}_in_tolerance"}
                if p["value"] is None:
                    required_channels -= channels
                else:
                    required_channels |= channels
            if p["record_type"] == "task_lifecycle":
                lifecycle_seen = True
                close_interval(event.scenario_time_ns)
                active_start = event.scenario_time_ns if p["value"] == "resumed" else None
                previous.clear()
                continue
            if p["record_type"] != "performance":
                continue
            matched = address in {"center_deviation", "cursor_in_target"} if task == "track" else address.endswith(("_deviation", "_in_tolerance"))
            if not matched:
                continue
            found = True
            if active_start is None:
                issue("sample_outside_active_task", task, [str(event.event_id)])
            tank = "cursor" if task == "track" else address.split("_", 1)[0]
            samples[(event.scenario_time_ns, tank)].append(event)
            scalar = p["value"]
            is_state = address == "cursor_in_target" or address.endswith("_in_tolerance")
            if (is_state and type(scalar) is not bool) or (not is_state and (
                type(scalar) not in {int, float} or not math.isfinite(scalar))):
                issue("invalid_task_sample", task, [str(event.event_id)])
            if p["automation_active"] is None:
                issue("unknown_sample_allocation", task, [str(event.event_id)])
            elif p["automation_active"]:
                issue("automation_exposed_sample", task, [str(event.event_id)])
            interval = p["sample_interval_ms"]
            if interval is None or interval <= 0:
                issue("unknown_sampling_interval", task, [str(event.event_id)])
            elif address in previous and event.scenario_time_ns - previous[address][0] > 3 * previous[address][1] * 1e6:
                issue("sample_gap", task, [str(event.event_id)])
            elif address not in previous and active_start is not None and event.scenario_time_ns - active_start > 3 * interval * 1e6:
                issue("sample_gap_at_interval_start", task, [str(event.event_id)])
            if interval is not None:
                previous[address] = (event.scenario_time_ns, interval)
        if not found:
            issue("missing_task_samples", task)
        if not lifecycle_seen:
            issue("missing_task_lifecycle", task)
        if active_start is not None and events:
            close_interval(events[-1].scenario_time_ns)
        for grouped in samples.values():
            if len(grouped) != 2 or len({e.payload["address"] for e in grouped}) != 2:
                issue("missing_or_duplicate_sample_pair", task, [str(e.event_id) for e in grouped])

    if "legacy_csv" in artifacts:
        import csv
        from io import StringIO
        csv_rows = list(csv.DictReader(StringIO(artifacts["legacy_csv"].decode("utf-8-sig"))))
        projected = [dict(e.payload["compatibility_row"]) if e.payload.get("compatibility_row") is not None else native_row(e)
                     for e in events if e.payload["record_type"] not in {"capture_lifecycle", "task_lifecycle"}]
        # Native values are recorded at full precision. Compatibility CSV rounds
        # numeric values to six decimals; compare at that documented boundary.
        mismatch = len(csv_rows) != len(projected)
        for actual, native in zip(csv_rows, projected):
            for key in ("type", "module", "address", "value", "scenario_time"):
                a, b = actual.get(key, ""), native[key]
                if a == b:
                    continue
                try:
                    same = float(a) == round(float(b), 6)
                except ValueError:
                    same = False
                mismatch |= not same
        if mismatch:
            issue("companion_csv_mismatch")

    metrics = []
    global_issues = [i["code"] for i in issues if i["task"] is None]
    generator = scenario.get("generated_by", scenario)
    generator_complete = generator.get("provenance_status") == "complete"
    complete_source = all(e.provenance_status == "complete" for e in events) and bool(events) and generator_complete
    for key, (section, field) in METRICS.items():
        task = TASK_FOR.get(section, section)
        task_stream = task_events[task]
        if section in {"nasatlx", "bedford", "isa"}:
            titles = TLX_TITLES if section == "nasatlx" else ({BEDFORD_TITLE} if section == "bedford" else {ISA_TITLE, ISA_TITLE_ES})
            sources = [e for e in task_stream if e.payload["record_type"] == "performance" and e.payload["address"] in titles]
            questionnaires = scenario.get("questionnaires", {})
            applicable = bool(sources) or (section in {"nasatlx", "bedford"} and questionnaires.get(f"include_{section}", False)) or (section == "isa" and bool(expected.get("isa_probe_times_sec")))
        else:
            sources = task_stream
            applicable = task in capture.tasks
        relevant = [*global_issues, *(i["code"] for i in issues if i["task"] == task)]
        calc = calculations[section]
        value = calc.get(field)
        if applicable and value is None:
            relevant.append("missing_or_invalid_metric_inputs")
        if section in {"nasatlx", "bedford", "isa"} and applicable and not calc.get("confirmatory_eligible"):
            relevant.append("incomplete_or_invalid_questionnaire")
        if section == "isa" and applicable and expected.get("isa_probe_times_sec") is not None and len(sources) != len(expected["isa_probe_times_sec"]):
            relevant.append("probe_count_mismatch")
        if section == "sysmon" and applicable and not calc.get("human_performance_eligible"):
            relevant.append("incomplete_or_automated_opportunities")
        definition = long_metric_definition(key)
        eligibility_reasons = list(relevant)
        if not complete_source:
            eligibility_reasons.append("provisional_source_provenance")
        if capture.execution_purpose != "study":
            eligibility_reasons.append("non_study_capture")
        if not definition["confirmatory_eligible"]:
            eligibility_reasons.append("metric_definition_not_confirmatory")
        if section == "comm":
            eligibility_reasons.append("physical_audio_onset_not_qualified")
        if not applicable:
            eligibility_reasons = ["task_or_probe_not_administered"]
        source_ids = [str(e.event_id) for e in sources]
        source_timing = [str(o.observation_id) for eid in source_ids for o in timing_by_event[eid]]
        metrics.append({"metric": key, "metric_version": str(definition["metric_version"]),
            "definition": definition, "value": value if applicable and not relevant else None,
            "descriptive_value": value if applicable else None,
            "status": "not_applicable" if not applicable else ("failed" if relevant else "succeeded"),
            "confirmatory_eligible": applicable and not eligibility_reasons,
            "exclusion_reasons": sorted(set(eligibility_reasons)),
            "source_event_ids": source_ids, "source_observation_ids": source_timing,
            "timing_basis": "scenario_time_and_software_observations",
            "physical_timing_qualification": "not_qualified", "human_calibration": "not_qualified"})
    fingerprint_data = {"capture_sha256": hashlib.sha256(artifacts["capture_manifest"]).hexdigest(),
        "source_hashes": {k: hashlib.sha256(v).hexdigest() for k, v in sorted(artifacts.items())},
        "derivation_version": DERIVATION_VERSION, "metrics_spec": METRICS_SPEC,
        "eligibility": [(m["metric"], m["confirmatory_eligible"], m["exclusion_reasons"]) for m in metrics]}
    return {"derivation_version": DERIVATION_VERSION, "metrics_schema_version": METRICS_SCHEMA_VERSION,
        "fingerprint": hashlib.sha256(canonical_bytes(fingerprint_data)).hexdigest(),
        "status": "failed" if issues else "succeeded", "issues": issues, "metrics": metrics,
        "source_hashes": fingerprint_data["source_hashes"],
        "analysis": {"suhir": {"status": "not_applicable", "reason": "protocol_has_not_declared_model_inputs"}},
        "timing": {"software_observations": len(observations), "physical_timing_qualification": "not_qualified",
                   "cross_clock_latency": None},
        "parameters": {"continuous_sample_max_gap_intervals": 3, "missing_sample_interpolation": False}}
