"""Swarm integration invariants, including old scenario and replay compatibility."""
from copy import deepcopy
from pathlib import Path
import pytest
from matb_integration.suas.domain.commands import CommandEnvelope, Hold, SwarmTask, SwarmWaypoint, SwarmMembership
from matb_integration.suas.domain.geometry import PointMM, distance_mm
from matb_integration.suas.domain.serialization import canonical_data
from matb_integration.suas.engine.runtime import SimulationEngine
from matb_integration.suas.engine.swarm import engine_version
from matb_integration.suas.recording.replay import deserialize_command
from matb_integration.suas.scenarios.loader import load_scenario

ROOT=Path(__file__).resolve().parents[2]
def make(block="HIGH"):
    return SimulationEngine(load_scenario(ROOT/"scenarios/suas/swarm_supervision.yaml").definition,block)
def issue(e,c,name="command"):
    return e.step([CommandEnvelope(name,e.snapshot()["state_version"],c)])

@pytest.mark.parametrize("block,count",[("PRACTICE",2),("LOW",4),("MEDIUM",6),("HIGH",8)])
def test_partition_search_and_checkpoint(block,count):
    e=make(block)
    assert len(e.snapshot()["aircraft"])==count
    result=issue(e,SwarmTask("ALPHA","SEARCH","sector_alpha"))
    assert result.command_results[0].code=="accepted"
    routes=[a["route"] for a in e.snapshot()["aircraft"].values()]
    assert len({str(r) for r in routes})==count
    for _ in range(51): e.step()
    checkpoint=e.checkpoint_snapshot(); restored=make(block);restored.restore(checkpoint)
    assert restored.state_hash==e.state_hash
    for _ in range(20): assert restored.step()==e.step()
    assert len(e.snapshot()["swarms"]["ALPHA"]["trails"] )==count

@pytest.mark.parametrize("formation",["line","wedge"])
def test_formation_assembly_is_continuous_and_synchronized(formation):
    e=make("LOW")
    previous={a:PointMM(**v["position"]) for a,v in e.snapshot()["aircraft"].items()}
    result=issue(e,SwarmWaypoint("ALPHA",PointMM(2000000,4000000),formation))
    assert result.command_results[0].code=="accepted"
    for _ in range(180):
        s=e.snapshot()
        for a,v in s["aircraft"].items():
            point=PointMM(**v["position"])
            assert distance_mm(previous[a],point)<=2001
            previous[a]=point
        e.step()
    group=e.snapshot()["swarms"]["ALPHA"]
    assert group["phase"]=="TRANSIT"
    assert group["formation_error_mm"]<=2


def test_rejected_group_command_does_not_partially_apply():
    e=make(); e._state.aircraft["UAS-08"].energy_units=1
    before={a:canonical_data(v.route) for a,v in e._state.aircraft.items()}
    result=issue(e,SwarmTask("ALPHA","SEARCH","sector_alpha"))
    assert result.command_results[0].code=="UAS-08:critical_reserve"
    assert {a:canonical_data(v.route) for a,v in e._state.aircraft.items()}==before
    assert e.snapshot()["swarms"]["ALPHA"]["command_count"]==0


def test_detach_and_duplicate_and_stale_commands():
    e=make()
    assert issue(e,Hold("UAS-01")).command_results[0].code=="detach_member_before_individual_command"
    result=issue(e,SwarmMembership("ALPHA","UAS-01","DETACH"),"detach")
    assert result.command_results[0].code=="accepted"
    assert issue(e,SwarmMembership("ALPHA","UAS-01","DETACH"),"detach").command_results[0].status=="duplicate"
    assert issue(e,Hold("UAS-01"),"hold").command_results[0].code=="accepted"
    result=e.step([CommandEnvelope("stale",0,SwarmTask("ALPHA","HOLD",""))])
    assert result.command_results[0].code=="stale_state_version"


def test_fault_detaches_without_silent_reallocation():
    from matb_integration.suas.domain.enums import LinkState
    e=make(); issue(e,SwarmTask("ALPHA","SEARCH","sector_alpha"))
    routes={a:canonical_data(v.route) for a,v in e._state.aircraft.items()}
    e._state.aircraft["UAS-03"].link=LinkState.LOST
    result=e.step(); g=result.snapshot["swarms"]["ALPHA"]
    assert "UAS-03" not in g["members"] and g["fault_at_ms"] is not None
    for a in g["members"]: assert canonical_data(e._state.aircraft[a].route)==routes[a]
    assert any(event.kind=="SWARM_CHANGED" and event.payload["action"]=="MEMBER_UNAVAILABLE" for event in result.events)


def test_bad_checkpoint_rejected_atomically():
    from matb_integration.suas.domain.serialization import canonical_sha256
    e=make(); before=e.state_hash; c=deepcopy(e.checkpoint_snapshot())
    c["world"]["swarms"]["ALPHA"]["members"]=["unknown"]
    c.pop("authoritative_state_sha256");c["authoritative_state_sha256"]=canonical_sha256(c)
    with pytest.raises(ValueError): e.restore(c)
    assert e.state_hash==before


def test_legacy_state_has_no_extension_fields():
    scenario=load_scenario(ROOT/"scenarios/suas/reference_area_search.yaml")
    e=SimulationEngine(scenario.definition,"LOW")
    assert engine_version(scenario.definition)=="1.0.0"
    assert "swarm" not in scenario.normalized_document
    assert "swarms" not in e.checkpoint_snapshot()["world"]
    assert "swarms" not in e.snapshot()

@pytest.mark.parametrize("command",[SwarmTask("ALPHA","HOLD",""),SwarmWaypoint("ALPHA",PointMM(1,2),"line"),SwarmMembership("ALPHA","UAS-01","JOIN")])
def test_replay_command_roundtrip(command):
    envelope={"command_id":"test","expected_state_version":0,"kind":type(command).__name__,"payload":canonical_data(command)}
    assert deserialize_command(envelope).command==command


def test_descriptive_swarm_metrics_use_frames_and_preserve_missing_values():
    from matb_integration.suas.metrics.debrief import swarm_metric_summary
    def frame(time, covered, fault=None):
        return {"block_id": "HIGH", "snapshot": {"simulation_time_ms": time, "state_version": time,
            "swarms": {"ALPHA": {"command_count": 2, "last_response_ms": None,
                "formation_error_mm": 100, "fault_at_ms": fault}},
            "coverage": {"sectors": {"alpha": {"covered_cells": list(range(covered))}}}}}
    assert swarm_metric_summary([]) is None
    result = swarm_metric_summary([frame(0,0),frame(100,0,100),frame(300,1,100)])
    group = result["blocks"][0]["groups"]["ALPHA"]
    assert group["group_command_count"] == 2
    assert group["last_fault_response_ms"] is None
    assert group["sampled_mean_formation_error_mm"] == 100
    assert group["first_new_coverage_after_observed_fault_ms"] == 200
    assert swarm_metric_summary([frame(100,0,100)])["blocks"][0]["groups"]["ALPHA"]["first_new_coverage_after_observed_fault_ms"] is None


def test_return_hold_resume_recovers_members():
    from matb_integration.suas.domain.enums import AircraftMode
    e=make("LOW")
    issue(e, SwarmWaypoint("ALPHA", PointMM(2000000,4000000), "line"), "transit")
    for _ in range(20): e.step()
    assert issue(e,SwarmTask("ALPHA","RETURN",""),"return").command_results[0].code == "accepted"
    assert issue(e,SwarmTask("ALPHA","HOLD",""),"hold").snapshot["swarms"]["ALPHA"]["activity"] == "HOLD"
    assert issue(e,SwarmTask("ALPHA","RESUME",""),"resume").command_results[0].code == "accepted"
    for a in e._state.aircraft.values(): assert a.mode in (AircraftMode.RETURN_TO_BASE,AircraftMode.RECOVERED)
    for _ in range(100): e.step()
    assert all(a.mode == AircraftMode.RECOVERED for a in e._state.aircraft.values())


def test_join_requires_explicit_new_task():
    e=make("LOW")
    issue(e,SwarmWaypoint("ALPHA",PointMM(2000000,4000000),"line"),"transit")
    issue(e,SwarmTask("ALPHA","HOLD",""),"hold")
    issue(e,SwarmMembership("ALPHA","UAS-01","DETACH"),"detach")
    assert issue(e,SwarmMembership("ALPHA","UAS-01","JOIN"),"join").command_results[0].code == "accepted"
    assert issue(e,SwarmTask("ALPHA","RESUME",""),"resume").command_results[0].code == "assign_group_task_before_resume"
