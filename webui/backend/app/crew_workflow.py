"""Callsigned participant entry over the existing immutable assessment ledger.

Configuration is an explicit, named deployment action. Participant requests
only materialize that configuration and never attest to consent or preparation.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlmodel import select

from app import astra_deployment, astra_roster, study_registry as registry
from app.assessment_models import AssessmentAttempt, AssessmentSourceLink
from app.assessment_schemas import AttemptIn
from app.assessment_service import create_attempt
from app.models import ParticipantRoster, Visit
from app.study_registry_models import StudyAssignment, StudyRecoveryInterval

CALLSIGNS = ("CUELLAR", "COLORADO", "ICEMAN", "WHITE", "PIRATA")
INSTRUMENTS = ("openmatb", "suas", "screen", "pvt")
POLICY = "astra-crew-flow-v1"
# Colombia has a fixed UTC-05:00 offset; no dependency on host time or tzdata.
BOGOTA = timezone(timedelta(hours=-5), "America/Bogota")


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def fail(code, message):
    raise HTTPException(409, dict(code=code, message=message))


def _version(db):
    identity = registry.active_version(db)
    if not identity:
        fail("crew_not_configured", "La estación necesita cargar la configuración de la tripulación.")
    version = registry.get_version(db, identity)
    study = json.loads(version.study_json)
    if version.study_id != astra_deployment.STUDY_ID or POLICY not in study["rules"]["preparation"]:
        fail("crew_not_configured", "La estación necesita actualizar el inicio de la tripulación.")
    return version, study


def _person(db, callsign):
    if callsign not in CALLSIGNS:
        raise HTTPException(422, "Seleccione un callsign de la tripulación ASTRA.")
    rows = db.exec(select(ParticipantRoster)).all()
    matches = [row for row in rows if row.callsign.upper() == callsign]
    if len(matches) != 1 or matches[0].archived_at or matches[0].mission != "ASTRA-1":
        fail("crew_not_available", "Este tripulante todavía no está habilitado en la estación.")
    return matches[0]


def _configure_roster(db):
    """Reuse callsigns even when a prior import omitted the mission."""
    rows = db.exec(select(ParticipantRoster)).all()
    for position, callsign in enumerate(CALLSIGNS, 1):
        matches = [row for row in rows if row.callsign.upper() == callsign]
        if len(matches) > 1:
            fail("crew_duplicate", f"Revise los registros duplicados de {callsign}.")
        if matches:
            row = matches[0]
            if row.archived_at or row.mission not in (None, "", "ASTRA-1"):
                fail("crew_roster_conflict", f"Revise la misión o el retiro de {callsign} antes de configurarlo.")
            row.mission = "ASTRA-1"
            row.position = position
            db.add(row)
        else:
            person = astra_roster.add_person(db, callsign=callsign, mission="ASTRA-1")
            row = db.get(ParticipantRoster, person.id)
            row.position = position
            db.add(row)
        existing = {v.visit_ordinal: v for v in db.exec(select(Visit).where(Visit.participant_id == row.participant_id)).all()}
        for definition in astra_roster.VISITS:
            if definition.ordinal not in existing:
                db.add(Visit(participant_id=row.participant_id, visit_ordinal=definition.ordinal,
                             scheduled_day=definition.scheduled_day))
            elif existing[definition.ordinal].scheduled_day != definition.scheduled_day:
                fail("crew_schedule_conflict", f"El calendario previo de {callsign} requiere revisión; se conserva sin cambios.")
    db.flush()


def configuration_payload(db):
    from app.study_bindings import binding_options, browser_binding
    payload = astra_deployment.payload(db, include_polar=False)
    study = payload["study"]
    study["title"] = "ASTRA · sesiones de tripulación"
    study["rules"]["preparation"] = (
        POLICY + ": inicio por callsign solicitado el 2026-10-06. Una sesión completa por "
        "actividad y día calendario de Bogotá; continuidad desde la primera sesión pendiente. "
        "Comprobación automática de estación y preflight nativo real; instrucciones dentro de "
        "cada tarea. Sin formularios administrativos de preparación ni adquisición Polar "
        "obligatoria. No acredita consentimiento, familiarización previa ni competencia."
    )
    study["enabled_instruments"] += ["pvt", "screen", "suas"]
    options = binding_options(db)
    scenario = next((s for s in options.get("suas", []) if s["id"] == "reference_area_search"), None)
    if not scenario:
        fail("crew_scenario_missing", "Instale el escenario de supervisión sUAS en esta estación.")
    for requirement in study["preparation_policy"]:
        requirement["acknowledgement_required"] = False
        requirement["rationale"] = "Inicio solicitado por el participante; instrucciones en la tarea y comprobación automática del entorno."
    # Keep scientific timings and source bindings; only the entry procedure changes.
    for visit in study["visits"]:
        prefix = f"v{visit['ordinal'] - 1}"
        for instrument, order in (("pvt", 20), ("screen", 21), ("suas", 22)):
            key = f"{prefix}_{instrument}"
            if instrument == "suas":
                config = dict(binding_id="suas-protocol-v1", scenario=scenario, presentation=None,
                              input_mapping="suas-default", scoring="suas-current", practice_included=True)
                conditions = {arm: "_".join(next(o for o in study["occasions"]
                              if o["key"] == f"{prefix}_block{i}")["condition_by_arm"][arm]
                              for i in (1, 2, 3)) for arm in study["arms"]}
            else:
                config = browser_binding(instrument)
                conditions = {arm: "baseline" for arm in study["arms"]}
            study["occasions"].append(dict(key=key, visit_ordinal=visit["ordinal"], instrument=instrument,
                phase="daily", order=order, condition_by_arm=conditions, locale="es-419", config=config,
                prerequisite_keys=[f"{prefix}_pvt"] if instrument == "suas" else []))
            study["preparation_policy"].append(dict(occasion_key=key, placement="prescribed_later",
                demonstration_required=False, acknowledgement_required=False, comprehension=[], practice=[],
                rationale="Instrucciones propias del instrumento dentro de la actividad; sin certificación de preparación adicional."))
    study["repeat_policy"]["permitted_causes"] += ["unknown", "participant_stop"]
    study["repeat_policy"]["rationale"] += " El botón Reintentar registra la solicitud; un cierre inesperado conserva la causa desconocida."
    return payload


def _has_live_attempt(db):
    """Old practice adapters can retain 'started' after their runtime terminated.

    Read both records without rewriting either; an unknown/browser owner still
    blocks station changes. Terminal native sources must have no surviving PID.
    """
    from app.openmatb_models import OpenMatbSuiteSession
    from app.native_process_guard import process_alive
    for attempt in db.exec(select(AssessmentAttempt).where(AssessmentAttempt.acquisition_state == "started")):
        link = _source(db, attempt, "openmatb_suite_session")
        native = db.get(OpenMatbSuiteSession, link.source_id) if link else None
        if (native is None or native.lifecycle not in {"COMPLETE", "ABORTED", "FAILED", "INTERRUPTED"}
                or any(process_alive(pid) for pid in (native.active_pid, native.recovery_pid) if pid)):
            return True
    return False


def configure(db, runtime, *, actor, reason):
    """Called once by the researcher/deployment, never by a participant GET/start."""
    registry.named(actor)
    if runtime.active_session() is not None:
        fail("crew_station_busy", "Termine o cierre la prueba abierta antes de actualizar la estación.")
    astra_deployment.ensure_preset(runtime)
    registry.lock_registry(db)
    from app.station_resources import snapshot
    if snapshot(db)["acquisitions"] or _has_live_attempt(db):
        fail("crew_station_busy", "Hay una prueba en curso; consérvela antes de actualizar la estación.")
    active = registry.active_version(db)
    if active and registry.get_version(db, active).study_id != astra_deployment.STUDY_ID:
        fail("crew_workspace_mismatch", "Esta base pertenece a otro estudio; use la estación ASTRA.")
    _configure_roster(db)
    candidate = registry.create_draft(db, configuration_payload(db))
    if active and candidate.sha256 == registry.get_version(db, active).draft_sha256:
        db.delete(candidate)
        db.flush()
        return dict(version_id=active, changed=False)
    rehearsal = registry.rehearse(db, candidate.id)
    version = registry.freeze(db, candidate.id, dict(actor=actor, reason=reason,
        sha256=candidate.sha256, rehearsal_id=rehearsal.id))
    registry.activate(db, version.id, actor=actor, reason=reason)
    crew_ids = {_person(db, callsign).participant_id for callsign in CALLSIGNS}
    pending = [a.id for a in db.exec(select(StudyAssignment)).all()
               if a.participant_id in crew_ids and registry.assignment_is_current(db, a)
               and not registry.assignment_started(db, a)]
    if pending:
        registry.amend(db, version.id, pending, actor=actor, reason=reason)
    db.flush()
    return dict(version_id=version.id, changed=True, updated_assignments=len(pending))


def _assignment(db, visit):
    return next((a for a in db.exec(select(StudyAssignment).where(StudyAssignment.visit_id == visit.id)).all()
                 if registry.assignment_is_current(db, a)), None)


def _attempts(db, assignment, key):
    if not assignment:
        return []
    identity = json.loads(assignment.occasions_json).get(key)
    if not identity:
        return []
    return db.exec(select(AssessmentAttempt).where(AssessmentAttempt.occasion_id == identity,
        AssessmentAttempt.execution_purpose == "study").order_by(AssessmentAttempt.ordinal)).all()


def _finished(rows, target_id=None):
    return next((row for row in reversed(rows) if row.acquisition_state == "finished"
                 and (target_id is None or row.target_attempt_id == target_id)), None)


def _visit_state(db, visit, instrument, template):
    assignment = _assignment(db, visit)
    study = json.loads(registry.get_version(db, assignment.version_id).study_json) if assignment else template
    tasks = [o for o in study["occasions"] if o["visit_ordinal"] == visit.visit_ordinal and o["instrument"] == instrument]
    keys = {o["key"] for o in tasks}
    tasks += [o for o in study["occasions"] if o["instrument"] == "questionnaire" and o["target_key"] in keys]
    tasks.sort(key=lambda o: o["order"])
    completed = {}
    for spec in tasks:
        target = completed.get(spec.get("target_key"))
        completed[spec["key"]] = (None if spec["instrument"] == "questionnaire" and not target
            else _finished(_attempts(db, assignment, spec["key"]), target.id if target else None))
    completions = [completed[o["key"]] for o in tasks]
    complete = bool(tasks) and all(completions)
    finished_at = max((aware(a.finished_at) for a in completions if a and a.finished_at), default=None) if complete else None
    return dict(visit=visit, assignment=assignment, study=study, tasks=tasks,
                complete=complete, finished_at=finished_at,
                pending=next((o for o, done in zip(tasks, completions) if not done), None),
                completed_blocks=sum(bool(a) for o, a in zip(tasks, completions) if o["instrument"] == instrument))


def _next_spec(db, state):
    spec = state["pending"]
    while spec and spec["prerequisite_keys"]:
        missing = next((key for key in spec["prerequisite_keys"]
                        if not _finished(_attempts(db, state["assignment"], key))), None)
        if missing is None:
            break
        spec = next(o for o in state["study"]["occasions"] if o["key"] == missing)
    return spec


def progress(db, callsign, instrument, *, now=None):
    if instrument not in INSTRUMENTS:
        raise HTTPException(422, "Actividad no disponible para este recorrido.")
    now = aware(now or utcnow())
    person = _person(db, callsign)
    _, template = _version(db)
    visits = db.exec(select(Visit).where(Visit.participant_id == person.participant_id).order_by(Visit.visit_ordinal)).all()
    states = [_visit_state(db, visit, instrument, template) for visit in visits
              if visit.visit_ordinal in {v["ordinal"] for v in template["visits"]}]
    finished_today = any(s["finished_at"] and s["finished_at"].astimezone(BOGOTA).date() == now.astimezone(BOGOTA).date() for s in states)
    pending = next((s for s in states if not s["complete"]), None)
    public = dict(callsign=callsign, participant_id=person.participant_id, instrument=instrument,
        state="complete" if pending is None else "done_today" if finished_today else "ready",
        completed_sessions=sum(s["complete"] for s in states), total_sessions=len(states),
        session_number=pending["visit"].visit_ordinal if pending else None,
        completed_blocks=pending["completed_blocks"] if pending else 0,
        date=now.astimezone(BOGOTA).date().isoformat())
    if pending and not pending["tasks"]:
        public.update(state="needs_review", message="Esta sesión previa no incluye la actividad; se conserva para revisión.")
    elif pending and pending["pending"]:
        spec = _next_spec(db, pending)
        rows = _attempts(db, pending["assignment"], spec["key"])
        if rows and rows[-1].acquisition_state == "interrupted" and not finished_today:
            public["state"] = "interrupted"
    return public, pending


def roster(db, instrument):
    return dict(instrument=instrument, participants=[progress(db, name, instrument)[0] for name in CALLSIGNS])


def _source(db, attempt, table):
    return db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.attempt_id == attempt.id,
        AssessmentSourceLink.source_table == table, AssessmentSourceLink.role == "acquisition")).first()


def _release_idle_reservation(db, assignment, callsign, retry):
    from app import station_resources as station
    from app.openmatb_models import OpenMatbSuiteSession
    current = station.snapshot(db)
    reserved, lanes = current["reservation"], current["acquisitions"]
    if not reserved:
        return
    native_active = db.exec(select(OpenMatbSuiteSession).where(OpenMatbSuiteSession.lifecycle.not_in(
        ("COMPLETE", "ABORTED", "FAILED", "INTERRUPTED")))).first()
    owner = "assignment:" + assignment.id
    # A participant retry can release only this assignment's already interrupted
    # browser attempts. It cannot stop a native process, Polar or another tab's
    # still-started acquisition.
    if retry and reserved["owner"] == owner and reserved.get("uncertain") and lanes:
        interrupted = all(lane["owner"] == owner and lane["instrument"] in {"pvt", "screen"}
            and not lane.get("pid") and lane.get("attempt_id")
            and (attempt := db.get(AssessmentAttempt, lane["attempt_id"])) is not None
            and attempt.acquisition_state == "interrupted" for lane in lanes.values())
        if interrupted and native_active is None:
            station.recover_idle(db, actor=callsign, reason="Reintento solicitado del navegador ya interrumpido; sin adquisición activa.", native_pids=[])
            return
    if reserved["owner"] == owner:
        return
    if (lanes or reserved.get("uncertain") or native_active is not None
            or _has_live_attempt(db)):
        fail("crew_station_busy", "Hay otra prueba abierta en la estación. Termínela antes de cambiar de tripulante.")
    station.close_visit(db, actor=callsign, reason="Cambio solicitado desde el selector; reserva anterior sin adquisición activa.")


def prepare(db, callsign, instrument, *, retry=False, now=None):
    """Serialize next-occasion decisions and reuse attempts on double click/reload."""
    registry.lock_registry(db)
    now = aware(now or utcnow())
    public, state = progress(db, callsign, instrument, now=now)
    if public["state"] in {"done_today", "complete", "needs_review"}:
        return dict(**public, action=public["state"])
    version, _ = _version(db)
    visit, assignment = state["visit"], state["assignment"]
    if not assignment:
        arm = f"ORDER-{(int(public['participant_id'][1:]) - 1) % 6 + 1}"
        assignment = registry.assign(db, version.id, public["participant_id"], visit.id, arm, actor=version.actor)
        state = _visit_state(db, visit, instrument, state["study"])
    spec = _next_spec(db, state)
    if POLICY not in state["study"]["rules"]["preparation"]:
        fail("crew_legacy_session", "Esta sesión ya iniciada conserva su preparación anterior. Solicite continuarla desde la estación.")
    _release_idle_reservation(db, assignment, callsign, retry)
    # Follow declared prerequisites automatically (sUAS -> KSS + PVT), never Polar.
    if spec["instrument"] == "questionnaire":
        target = _finished(_attempts(db, assignment, spec["target_key"]))
        source = _source(db, target, "openmatb_suite_session") if target else None
        if not source:
            fail("crew_ratings_missing", "La sesión necesita recuperar su cuestionario guardado.")
        return dict(**public, action="native_session", session_id=source.source_id, visit_id=visit.id)
    for interval in state["study"]["recovery_intervals"]:
        if interval["before_key"] != spec["key"]:
            continue
        anchor = _finished(_attempts(db, assignment, interval["anchor_key"]))
        if not anchor or not anchor.finished_at:
            fail("crew_rest_anchor_missing", "Complete el cuestionario del bloque anterior.")
        rest = db.get(StudyRecoveryInterval, (assignment.id, interval["key"]))
        if rest is None:
            rest = StudyRecoveryInterval(assignment_id=assignment.id, interval_key=interval["key"],
                anchor_attempt_id=anchor.id, started_at=aware(anchor.finished_at), actor=version.actor,
                reason="Intervalo automático desde el guardado del cuestionario; no acredita reposo observado.")
            db.add(rest)
            db.flush()
        until = aware(rest.started_at) + timedelta(seconds=interval["duration_seconds"])
        if now < until:
            return dict(**public, action="rest", available_at=until.isoformat(), remaining_seconds=(until-now).total_seconds())
        if rest.ended_at is None:
            rest.ended_at = now
            rest.finish_actor = version.actor
            rest.finish_reason = "Duración del intervalo transcurrida; inicio solicitado por el tripulante."
            db.add(rest)
    rows = _attempts(db, assignment, spec["key"])
    if rows and rows[-1].acquisition_state in {"created", "started"}:
        attempt = rows[-1]
    elif rows:
        if not retry:
            return dict(**public, action="retry_required")
        attempt = create_attempt(db, json.loads(assignment.occasions_json)[spec["key"]], AttemptIn(execution_purpose="study"),
            repeat_of=rows[-1].id, reason=f"{callsign}: reintento solicitado desde el inicio simplificado tras interrupción registrada.")
    else:
        attempt = create_attempt(db, json.loads(assignment.occasions_json)[spec["key"]], AttemptIn(execution_purpose="study"))
    if attempt.acquisition_state == "created":
        from app.study_admission import select_prerequisites
        select_prerequisites(db, attempt.id, {key: _finished(_attempts(db, assignment, key)).id for key in spec["prerequisite_keys"]})
    table = {"openmatb": "openmatb_suite_session", "suas": "simulation_session"}.get(spec["instrument"])
    source = _source(db, attempt, table) if table else None
    if attempt.acquisition_state == "started" and not source:
        fail("crew_attempt_active", "Esta prueba ya está abierta. Continúe en la pestaña donde comenzó.")
    return dict(**public, action="launch", activity=spec["instrument"], attempt_id=attempt.id,
        visit_id=visit.id, visit_ordinal=visit.visit_ordinal, locale=spec["locale"], config=spec["config"],
        session_id=source.source_id if source else None)
