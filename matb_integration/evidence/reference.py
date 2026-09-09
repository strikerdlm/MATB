"""Deterministic synthetic reference generator for software verification only.

No participant recordings or empirical qualification evidence are included.
"""
from pathlib import Path
from hashlib import sha256
from uuid import UUID, uuid5

from matb_integration.log_converter import NASA_TLX_SUBSCALES, ISA_TITLE, BEDFORD_TITLE
from .contracts import canonical_bytes
from .writer import EvidenceWriter


def synthetic_capture(root: Path, *, tasks: tuple[str, ...] = ("sysmon", "track", "resman", "communications", "genericscales"),
                      purpose: str = "study", completion: str = "completed", identity: str = "reference") -> dict[str, bytes]:
    """A tiny reference with known outcomes; source IDs are fixture constants."""
    root.mkdir(parents=True, exist_ok=True)
    stem = root / "synthetic.csv"
    session_id = str(uuid5(UUID("ae9c19fc-ad8b-4b98-a8c1-0be0456652af"), identity))
    context = {"scenario_sha256": "a" * 64, "profile_id": "synthetic-software-reference",
               "source_commit": "b" * 40, "source_dirty": False, "component_version": "synthetic-test-1",
               "scenario_manifest_status": "verified"}
    manifest = {"manifest_version": 3, "scenario": {"sha256": "a" * 64},
        "generated_by": {"component": "synthetic-software-reference", "source_commit": "b" * 40,
                         "source_dirty": False, "provenance_status": "complete"},
        "participant_id": "P01", "visit_ordinal": 1, "workload_level": "REFERENCE",
        "expected": {"sysmon_target_opportunities": 1, "sysmon_nontarget_opportunities": 1, "comm_events": 2,
                     "isa_probe_times_sec": [6] if "genericscales" in tasks else []},
        "questionnaires": {"include_nasatlx": "genericscales" in tasks, "include_bedford": "genericscales" in tasks},
        "synthetic_reference_only": True}
    scenario_path = root / "synthetic.scenario.manifest.json"
    scenario_path.write_bytes(canonical_bytes(manifest))
    writer = EvidenceWriter(stem, session_id, context, {"participant_id": "P01", "visit_ordinal": 1,
                            "condition": "REFERENCE", "execution_purpose": purpose})
    writer.set_tasks(list(tasks))
    tick = 1_000_000_000
    writer.lifecycle("started", 0, tick)

    def emit(task: str, address: str, value, time: float, kind: str = "performance") -> None:
        nonlocal tick
        tick += 1_000_000
        writer.record({"type": kind, "module": task, "address": address, "value": value, "scenario_time": time},
                      {"recorded_monotonic_ns": tick})

    emit("", "", canonical_bytes({"status": "verified", "scenario_manifest_sha256": sha256(scenario_path.read_bytes()).hexdigest()}).decode().strip(),
         0, "scenario_manifest_evidence")

    for task in tasks:
        emit(task, "automaticsolver", False, 0, "parameter")
        emit(task, "taskupdatetime", 100, 0, "parameter")
    if "resman" in tasks:
        emit("resman", "tank-a-target", 2500, 0, "parameter")
    for task in ("track", "resman"):
        if task in tasks:
            emit(task, "self", "started", 0.9, "task_lifecycle")
            emit(task, "self", "resumed", 0.9, "task_lifecycle")
    for step in range(3):
        at = 1 + step / 10
        if "track" in tasks:
            emit("track", "cursor_in_target", step != 1, at)
            emit("track", "center_deviation", [3., 4., 0.][step], at)
        if "resman" in tasks:
            emit("resman", "a_in_tolerance", step != 1, at)
            emit("resman", "a_deviation", [10., -20., 0.][step], at)
    for task in ("track", "resman"):
        if task in tasks:
            emit(task, "self", "stopped", 1.3, "task_lifecycle")
    if "sysmon" in tasks:
        for i, target in enumerate((True, False)):
            op = {"opportunity_id": f"sysmon-{i}", "target": target,
                  "allocation_actor": "participant", "automation_active": False,
                  "opened_scenario_time_s": 2 + i, "deadline_s": 2.5 + i}
            emit("sysmon", "opportunity", canonical_bytes({**op, "phase": "opened"}).decode().strip(), 2 + i)
            closed = {**op, "phase": "closed", "outcome": "HIT" if target else "CR", "response_actor": "participant",
                      "response_time_ms": 100 if target else None, "scheduled_deadline_s": 2.5 + i}
            emit("sysmon", "opportunity", canonical_bytes(closed).decode().strip(), 2.1 + i)
    if "communications" in tasks:
        for i, destination in enumerate(("own", "other")):
            op = {"schema_version": "1.0", "opportunity_id": f"comm-{i}", "destination": destination, "automation_active": False}
            for j, phase in enumerate(("opened", "presentation_started", "response_window_opened", "closed")):
                detail = {"phase": phase, "software_play_invoked": True, "physical_onset_measured": False}
                if phase == "closed":
                    detail.update(outcome="HIT" if destination == "own" else "CR", response_actor="participant",
                                  response_time_ms=150 if destination == "own" else None)
                emit("communications", "comm_opportunity_v1", canonical_bytes({**op, **detail}).decode().strip(), 4 + i + j / 10)
    if "genericscales" in tasks:
        for title in NASA_TLX_SUBSCALES:
            emit("genericscales", title, 4, 6)
        emit("genericscales", BEDFORD_TITLE, 3, 6)
        emit("genericscales", ISA_TITLE, 5, 6)
    tick += 1_000_000
    writer.lifecycle("completed" if completion == "completed" else "interrupted", 7, tick, completion)
    writer.seal(completion=completion, artifacts={"scenario_manifest": scenario_path})
    return {"capture_manifest": writer.manifest_path.read_bytes(), "scenario_manifest": scenario_path.read_bytes(),
            **{key: path.read_bytes() for key, path in writer.paths.items()}}
