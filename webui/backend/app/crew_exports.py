"""Regenerable, flat CSV copies of ASTRA evidence; original records are untouched."""
from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlmodel import Session, select

from app.assessment_models import AssessmentAttempt, AssessmentOccasion, AssessmentSourceLink
from app.models import ParticipantRoster, Visit
from app import crew_schedule as schedule

ROOT = Path(__file__).resolve().parents[3]
CALLSIGNS = {"CUELLAR", "COLORADO", "ICEMAN", "WHITE", "PIRATA"}
# Only evidence fields: never export runtime leases, tokens, host paths or credentials.
FIELDS = {
    "pvt_assessment": ("kss_score", "administered_at", "duration_ms", "protocol_valid", "pvt_version", "raw_trials_json", "metrics_json", "timing_evidence_json"),
    "screenresult": ("administered_at", "screen_version", "raw_trials_json", "scores_json"),
    "openmatb_suite_session": ("lifecycle", "preset_id", "preset_version", "locale", "block_order_json", "scores_json"),
    "openmatb_block_attempt": ("block_index", "profile", "task_status", "artifact_status", "evidence_status", "ratings_json"),
    "study_native_rating": ("payload_json", "target_attempt_id", "block_instance_id"),
    "simulation_session": ("scenario_id", "scenario_sha256", "locale", "lifecycle", "validity"),
    "simulation_block": ("block_id", "profile", "order_index", "lifecycle", "validity", "metrics_json"),
}
HEADER = ("callsign", "participant_id", "jornada", "planned_date", "test_date", "started_at",
          "instrument", "attempt_id", "attempt_number", "acquisition_state", "source_type", "source_id", "field", "value")
PRIVATE_FIELDS = {"controller_lease", "controller_lease_hash", "participant_token", "participant_token_hash",
                  "authorization", "api_key", "access_token", "refresh_token", "password", "artifact_root"}


def export_root():
    configured = os.getenv("MATB_CREW_EXPORT_ROOT")
    root = Path(configured) if configured else ROOT / "exports"
    if not root.is_absolute():
        root = ROOT / root
    return root.resolve()


def _directory(root, callsign, day, code):
    if callsign not in CALLSIGNS:
        raise ValueError("Unknown crew callsign")
    directory = root / callsign / f"{day}_{code}"
    if not directory.resolve().is_relative_to(root) or any(p.is_symlink() or p.is_junction() for p in (root / callsign, directory)):
        raise ValueError("Crew export path leaves its configured root")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def prepare_directories():
    root = export_root()
    for callsign in sorted(CALLSIGNS):
        for visit in schedule.VISITS:
            _directory(root, callsign, schedule.planned_date(visit.ordinal).isoformat(), visit.code)


def context(db, attempt):
    if attempt.execution_purpose != "study":
        return None
    occasion = db.get(AssessmentOccasion, attempt.occasion_id)
    person = db.get(ParticipantRoster, occasion.participant_id) if occasion.participant_id else None
    visit = db.get(Visit, occasion.visit_id) if occasion.visit_id else None
    if (person is None or person.mission != "ASTRA-1" or person.callsign not in CALLSIGNS
            or visit is None or visit.visit_ordinal not in {v.ordinal for v in schedule.VISITS}
            or occasion.instrument not in {"pvt", "screen", "openmatb", "suas", "questionnaire"}):
        return None
    return person, visit, occasion


def enqueue(db, attempt):
    if context(db, attempt) and attempt.acquisition_state in {"finished", "interrupted"}:
        from app.station_resources import enqueue_source
        return enqueue_source(db, "crew_export", {"attempt_id": attempt.id})


def _flatten(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in PRIVATE_FIELDS:
                continue
            yield from _flatten(item, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _flatten(item, f"{prefix}[{index}]")
    else:
        yield prefix, value


def _cells(value):
    # Keep numbers numeric; prevent strings from becoming spreadsheet formulas.
    if isinstance(value, str) and re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value.strip()):
        return value
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _source_rows(db, attempt):
    tables = set(inspect(db.connection()).get_table_names())
    links = db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.attempt_id == attempt.id)).all()
    # Include persisted mission blocks even when imported adapters linked only the session.
    for link in links[:]:
        if link.source_table == "simulation_session" and "simulation_block" in tables:
            for row in db.execute(text("SELECT id FROM simulation_block WHERE session_id=:id"), {"id": link.source_id}):
                links.append(AssessmentSourceLink(attempt_id=attempt.id, source_table="simulation_block", source_id=str(row[0])))
    seen = set()
    for link in links:
        table = link.source_table
        if table not in FIELDS or table not in tables or (table, link.source_id) in seen:
            continue
        seen.add((table, link.source_id))
        source = db.execute(text(f'SELECT * FROM "{table}" WHERE id=:id'), {"id": link.source_id}).mappings().first()
        if not source:
            continue
        for key in FIELDS[table]:
            value = source.get(key)
            if key.endswith("_json") and value is not None:
                value = json.loads(value)
            for field, cell in _flatten(value, key.removesuffix("_json")):
                yield table, link.source_id, field, cell
        if table == "simulation_session":
            from app.artifact_paths import resolve_artifact
            root = resolve_artifact(source["artifact_root"]).resolve()
            for name in ("events.jsonl", "questionnaires.json", "metrics.json"):
                artifact = root / name
                if not artifact.resolve().is_relative_to(root):
                    raise ValueError("Mission artifact outside its session root")
                if not artifact.is_file():
                    # Derived metrics may still be queued; raw source state stays explicit.
                    yield table, link.source_id, f"{name}.available", False
                    continue
                with artifact.open(encoding="utf-8-sig") as stream:
                    if name.endswith(".jsonl"):
                        for index, line in enumerate(stream):
                            for field, cell in _flatten(json.loads(line), f"events[{index}]"):
                                yield table, link.source_id, field, cell
                    else:
                        for field, cell in _flatten(json.load(stream), name.removesuffix(".json")):
                            yield table, link.source_id, field, cell
        if table == "openmatb_block_attempt" and source.get("session_csv"):
            from app.artifact_paths import resolve_artifact
            parent = db.execute(text("SELECT artifact_root FROM openmatb_suite_session WHERE id=:id"), {"id": source["session_id"]}).first()
            path = resolve_artifact(source["session_csv"]).resolve()
            if not parent or not path.is_relative_to(resolve_artifact(parent[0]).resolve()):
                raise ValueError("Native CSV outside its recorded session root")
            # Stream the original table into explicit row/column fields; no JSON blobs.
            with path.open(encoding="utf-8-sig", newline="") as stream:
                sample = stream.read(4096)
                stream.seek(0)
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                for index, row in enumerate(csv.reader(stream, dialect)):
                    for column, cell in enumerate(row):
                        yield table, link.source_id, f"native_csv[{index}][{column}]", cell


def export_attempt(db, identity):
    attempt = db.get(AssessmentAttempt, identity)
    details = context(db, attempt) if attempt else None
    if details is None or attempt.acquisition_state not in {"finished", "interrupted"}:
        return None
    person, visit, occasion = details
    observed = attempt.started_at or attempt.finished_at
    if observed is None:
        raise ValueError("Cannot assign an export date without an observed timestamp")
    from app.crew_workflow import aware
    observed = aware(observed).astimezone(schedule.BOGOTA)
    definition = next(v for v in schedule.VISITS if v.ordinal == visit.visit_ordinal)
    if not re.fullmatch(r"[A-Za-z0-9-]+", attempt.id):
        raise ValueError("Unsafe attempt identity in export filename")
    folder = _directory(export_root(), person.callsign, observed.date().isoformat(), definition.code)
    name = f"{person.callsign}_{observed.strftime('%Y%m%dT%H%M%S%f%z')}_{occasion.instrument}_{attempt.id}.csv"
    destination = folder / name
    if destination.is_symlink():
        raise ValueError("Refusing a linked export file")
    temporary = folder / f".{uuid4().hex}.tmp"
    prefix = (person.callsign, person.participant_id, definition.code, schedule.planned_date(visit.visit_ordinal).isoformat(),
              observed.date().isoformat(), observed.isoformat() if attempt.started_at else "", occasion.instrument, attempt.id, attempt.ordinal, attempt.acquisition_state)
    try:
        with temporary.open("x", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(HEADER)
            writer.writerow((*prefix, "assessment_attempt", attempt.id, "raw_saving", attempt.raw_saving))
            for row in _source_rows(db, attempt):
                writer.writerow((*prefix, *(_cells(cell) for cell in row)))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination.relative_to(export_root()).as_posix()


def run_export(engine, identity):
    with Session(engine) as db:
        return export_attempt(db, identity)


def queue_all(db):
    """Rebuild derived CSVs on request; all attempts and source artifacts remain intact."""
    prepare_directories()
    count = 0
    for attempt in db.exec(select(AssessmentAttempt).where(AssessmentAttempt.execution_purpose == "study",
            AssessmentAttempt.acquisition_state.in_(["finished", "interrupted"]))):
        if enqueue(db, attempt):
            count += 1
    return count
