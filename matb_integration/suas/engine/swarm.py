"""Versioned, integer-only supervisory coordination. No physical flocking claims."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import fields

from matb_integration.suas.domain.commands import Hold, ResumeMission, ReturnToBase, SwarmMembership, SwarmTask, SwarmWaypoint
from matb_integration.suas.domain.enums import AircraftMode, EventKind, LinkState
from matb_integration.suas.domain.events import DomainEvent
from matb_integration.suas.domain.geometry import PointMM, PolygonMM, distance_mm
from matb_integration.suas.domain.models import Route
from matb_integration.suas.engine.routes import lawnmower_route

SWARM_ENGINE_VERSION = "2.0.0-swarm.1"

def engine_version(scenario):
    return SWARM_ENGINE_VERSION if scenario.swarm else "1.0.0"

def initialize_groups(scenario, aircraft):
    if not scenario.swarm:
        return None
    return {gid: {"members": sorted(set(ids) & set(aircraft)), "formation": "line",
                  "task": "HOLD", "phase": "IDLE", "target_id": "", "slots": {}, "command_count": 0,
                  "fault_at_ms": None, "last_response_ms": None, "trails": {}}
            for gid, ids in sorted(scenario.swarm["groups"].items())
            if set(ids) & set(aircraft)}

def emit(state, group_id, action, **payload):
    state.event_sequence += 1
    return DomainEvent(event_id=f"{state.block_id}:{state.event_sequence:08d}",
        sequence=state.event_sequence, simulation_time_ms=state.simulation_time_ms,
        kind=EventKind.SWARM_CHANGED, entity_ids=(group_id,), payload={"action": action, **payload})

def member_group(state, aircraft_id):
    return next((gid for gid, group in (state.swarms or {}).items() if aircraft_id in group["members"]), None)

def offsets(count, spacing, formation):
    # World-aligned slots remain stable across route changes; no hidden rotating frame.
    if formation == "line":
        return [PointMM((2*i-count+1)*spacing//2, 0) for i in range(count)]
    return [PointMM(0, 0)] + [PointMM((1 if i % 2 else -1)*((i+1)//2)*spacing,
                                     -((i+1)//2)*spacing) for i in range(1, count)]

def apply_group(reducer, state, command):
    from matb_integration.suas.engine.reducer import _Rejected
    if not state.swarms or command.group_id not in state.swarms:
        raise _Rejected("unknown_swarm")
    candidate = deepcopy(state)
    group = candidate.swarms[command.group_id]
    events = []
    if isinstance(command, SwarmMembership):
        aircraft = reducer._aircraft(candidate, command.aircraft_id)
        if command.action == "DETACH":
            if command.aircraft_id not in group["members"]:
                raise _Rejected("not_a_member")
            # Detachment transfers control without altering the existing aircraft route.
            group["members"].remove(command.aircraft_id)
            group["slots"].pop(command.aircraft_id, None)
        elif command.action == "JOIN":
            reducer._validate_aircraft_control(aircraft)
            if member_group(candidate, command.aircraft_id):
                raise _Rejected("already_grouped")
            # Join only while held: the next task explicitly redistributes routes.
            if aircraft.mode != AircraftMode.HOLD or any(candidate.aircraft[a].mode != AircraftMode.HOLD for a in group["members"]):
                raise _Rejected("hold_members_before_join")
            group["members"] = sorted([*group["members"], command.aircraft_id])
            group["slots"] = {}
            group["task"] = "HOLD"
            group["phase"] = "IDLE"
        else:
            raise _Rejected("invalid_membership_action")
    else:
        ids = group["members"]
        if not ids:
            raise _Rejected("empty_swarm")
        if isinstance(command, SwarmWaypoint):
            if command.formation not in ("line", "wedge"):
                raise _Rejected("invalid_formation")
            if not isinstance(command.waypoint, PointMM):
                raise _Rejected("invalid_waypoint")
            slots = offsets(len(ids), reducer._scenario.swarm["spacing_mm"], command.formation)
            center = PointMM(sum(candidate.aircraft[a].position.x_mm for a in ids)//len(ids), sum(candidate.aircraft[a].position.y_mm for a in ids)//len(ids))
            routes = {a: Route((PointMM(center.x_mm+o.x_mm, center.y_mm+o.y_mm), PointMM(command.waypoint.x_mm+o.x_mm, command.waypoint.y_mm+o.y_mm))) for a,o in zip(ids, slots)}
            group.update(formation=command.formation, task="TRANSIT", phase="ASSEMBLE", target_id="",
                         slots={a: {"x_mm": o.x_mm, "y_mm": o.y_mm} for a,o in zip(ids, slots)})
        elif command.action == "SEARCH":
            sector = reducer._scenario.sectors.get(command.target_id)
            if sector is None:
                raise _Rejected("unknown_sector")
            # V1 partitioning supports rectangles only; reject rather than search outside concave polygons.
            x0,y0,x1,y1 = sector.bounds
            if {(p.x_mm,p.y_mm) for p in sector.vertices} != {(x0,y0),(x1,y0),(x1,y1),(x0,y1)}:
                raise _Rejected("swarm_search_requires_rectangle")
            routes = {}
            for i,a in enumerate(ids):
                lo, hi = x0+(x1-x0)*i//len(ids), x0+(x1-x0)*(i+1)//len(ids)
                strip = PolygonMM((PointMM(lo,y0),PointMM(hi,y0),PointMM(hi,y1),PointMM(lo,y1)))
                routes[a] = lawnmower_route(strip, reducer._scenario.aircraft[a].sensor.radius_mm*2)
            group.update(task="SEARCH", phase="IDLE", target_id=command.target_id, slots={})
        elif command.action in ("HOLD", "RESUME", "RETURN") and command.target_id == "":
            routes = None
            if command.action == "RESUME" and group["task"] == "HOLD":
                raise _Rejected("assign_group_task_before_resume")
            kind = {"HOLD": Hold, "RESUME": ResumeMission, "RETURN": ReturnToBase}[command.action]
            for a in ids:
                try:
                    if command.action == "RETURN":
                        reducer._validate_route(candidate.aircraft[a].position, Route((reducer._scenario.aircraft[a].home,)))
                    events.extend(reducer._mutate(candidate, kind(a), grouped=True))
                    if command.action == "RESUME" and group["task"] == "RETURN":
                        events.extend(reducer._set_mode_event(candidate, candidate.aircraft[a], AircraftMode.RETURN_TO_BASE))
                except _Rejected as exc:
                    raise _Rejected(f"{a}:{exc.code}") from exc
            if command.action == "RETURN":
                group["task"] = command.action
                group["phase"] = "IDLE"
        else:
            raise _Rejected("invalid_swarm_task")
        if routes is not None:
            for a, route in routes.items():
                aircraft = candidate.aircraft[a]
                try:
                    reducer._validate_aircraft_control(aircraft)
                    reducer._validate_route(aircraft.position, route)
                    reducer._validate_reserve(candidate, a, aircraft.position, route)
                except _Rejected as exc:
                    raise _Rejected(f"{a}:{exc.code}") from exc
                reducer._set_route(aircraft, route)
                aircraft.assigned_sector_id = group["target_id"] or None
                events.extend(reducer._set_mode_event(candidate, aircraft, AircraftMode.SEARCH if group["task"] == "SEARCH" else AircraftMode.TRANSIT))
        group["command_count"] += 1
        if group["fault_at_ms"] is not None:
            group["last_response_ms"] = candidate.simulation_time_ms-group["fault_at_ms"]
            group["fault_at_ms"] = None
    events.append(emit(candidate, command.group_id, type(command).__name__, task=group["task"], members=group["members"].copy()))
    for field in fields(state):
        setattr(state, field.name, getattr(candidate, field.name))
    return tuple(events)

def update_groups(state):
    events = []
    for gid, group in (state.swarms or {}).items():
        for a in list(group["members"]):
            aircraft = state.aircraft[a]
            unavailable = aircraft.link == LinkState.LOST or aircraft.mode in (AircraftMode.MISSION_FAILED, AircraftMode.RECOVERED, AircraftMode.LOST_LINK_PROCEDURE)
            if aircraft.mode == AircraftMode.RETURN_TO_BASE and group["task"] != "RETURN":
                unavailable = True
            if unavailable:
                group["members"].remove(a)
                group["slots"].pop(a, None)
                if aircraft.mode != AircraftMode.RECOVERED:
                    group["fault_at_ms"] = state.simulation_time_ms
                events.append(emit(state, gid, "MEMBER_UNAVAILABLE", aircraft_id=a, reason=aircraft.mode.value))
        if group["phase"] == "ASSEMBLE" and group["members"] and all(state.aircraft[a].route_leg >= 1 for a in group["members"]):
            group["phase"] = "TRANSIT"
            events.append(emit(state, gid, "FORMATION_ASSEMBLED"))
        if state.simulation_time_ms % 500 == 0:
            group["trails"] = {a: [*(group["trails"].get(a, [])), {"time_ms": state.simulation_time_ms, "x_mm": state.aircraft[a].position.x_mm, "y_mm": state.aircraft[a].position.y_mm}][-61:] for a in group["members"]}
    if events:
        state.version += 1
    return tuple(events)

def public_groups(state):
    result = deepcopy(state.swarms or {})
    for group in result.values():
        ids = group["members"]
        group["status"] = "EMPTY" if not ids else "DEGRADED" if group["fault_at_ms"] is not None or any(state.aircraft[a].link != LinkState.NOMINAL for a in ids) else "NOMINAL"
        group["activity"] = "HOLD" if ids and all(state.aircraft[a].mode == AircraftMode.HOLD for a in ids) else group["task"]
        group["formation_error_mm"] = None
        if len(ids)>1 and all(a in group["slots"] for a in ids):
            anchors = [PointMM(state.aircraft[a].position.x_mm-group["slots"][a]["x_mm"], state.aircraft[a].position.y_mm-group["slots"][a]["y_mm"]) for a in ids]
            center = PointMM(sum(p.x_mm for p in anchors)//len(ids), sum(p.y_mm for p in anchors)//len(ids))
            group["formation_error_mm"] = sum(distance_mm(p,center) for p in anchors)//len(ids)
    return result

def restore_groups(raw, scenario, aircraft):
    expected = initialize_groups(scenario, aircraft)
    if expected is None:
        if raw is not None: raise ValueError("legacy world cannot contain swarm state")
        return None
    if not isinstance(raw, dict) or set(raw) != set(expected): raise ValueError("invalid swarm groups")
    seen = set()
    for group in raw.values():
        if not isinstance(group, dict) or set(group) != set(next(iter(expected.values()))): raise ValueError("invalid swarm fields")
        ids = group["members"]
        if not isinstance(ids, list) or any(not isinstance(a,str) or a not in aircraft or a in seen for a in ids) or ids != sorted(set(ids)): raise ValueError("invalid swarm membership")
        seen.update(ids)
        if group["phase"] not in ("IDLE", "ASSEMBLE", "TRANSIT"): raise ValueError("invalid formation phase")
        if group["formation"] not in ("line", "wedge") or group["task"] not in ("HOLD", "SEARCH", "TRANSIT", "RETURN"): raise ValueError("invalid swarm task")
        if not isinstance(group["target_id"], str) or (group["target_id"] and group["target_id"] not in scenario.sectors): raise ValueError("invalid swarm target")
        for name in ("command_count", "fault_at_ms", "last_response_ms"):
            value = group[name]
            if value is None and name != "command_count": continue
            if isinstance(value,bool) or not isinstance(value,int) or value<0: raise ValueError("invalid swarm counter")
        trails = group["trails"]
        if not isinstance(trails,dict) or not set(trails).issubset(aircraft): raise ValueError("invalid swarm trails")
        for trail in trails.values():
            if not isinstance(trail,list) or len(trail)>61: raise ValueError("invalid trail length")
            previous = -1
            for p in trail:
                if not isinstance(p,dict) or set(p)!={"time_ms","x_mm","y_mm"} or any(isinstance(v,bool) or not isinstance(v,int) for v in p.values()) or p["time_ms"]<=previous: raise ValueError("invalid trail sample")
                previous = p["time_ms"]
        slots = group["slots"]
        if not isinstance(slots,dict) or not set(slots).issubset(ids): raise ValueError("invalid swarm slots")
        for point in slots.values():
            if not isinstance(point,dict) or set(point)!={"x_mm","y_mm"} or any(isinstance(v,bool) or not isinstance(v,int) for v in point.values()): raise ValueError("invalid swarm offset")
    return deepcopy(raw)
