"""Exact shared-attempt source snapshots. Raw bytes are retained for offline replay."""

import base64
import hashlib
import json
from app.artifact_paths import resolve_artifact
from pathlib import Path
from sqlalchemy import inspect, text
from sqlmodel import select
from app.assessment_models import AssessmentSourceLink
from app.evidence_models import EvidenceCapture, EvidenceMetric, EvidenceRun


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(data):
    return base64.b64encode(data).decode()


def _files(root, inventory):
    root = resolve_artifact(root).resolve()
    result = {}
    for item in inventory:
        name = item["relative_path"]
        path = (root / name).resolve()
        if not path.is_relative_to(root) or (root / name).is_symlink():
            raise ValueError("Invalid source artifact path.")
        data = path.read_bytes()
        if digest(data) != item["sha256"]:
            raise ValueError("Source artifact checksum mismatch.")
        result[name] = encoded(data)
    return result


def read_source(db, attempt, instrument, *, metric_ids):
    tables = set(inspect(db.connection()).get_table_names())
    links = db.exec(
        select(AssessmentSourceLink)
        .where(AssessmentSourceLink.attempt_id == attempt.id)
        .order_by(AssessmentSourceLink.id)
    ).all()
    records = []
    from app.assessment_adapters import SOURCE_INSTRUMENTS

    for link in links:
        if link.source_table in tables and link.source_table in SOURCE_INSTRUMENTS:
            row = (
                db.execute(
                    text(f'SELECT * FROM "{link.source_table}" WHERE id=:id'),
                    dict(id=link.source_id),
                )
                .mappings()
                .first()
            )
            if row:
                row = dict(row)
                # Controller leases authorize acquisition, never become research artifacts.
                row.pop("controller_lease_hash", None)
                if (
                    row.get("purpose_provenance_id")
                    and link.purpose_provenance_id
                    and row["purpose_provenance_id"] != link.purpose_provenance_id
                ):
                    raise ValueError(
                        "Source identity differs from immutable UUID association; an integer ID may have been reused."
                    )
                records.append(dict(link=link.model_dump(mode="json"), record=row))

    def one(table):
        candidates = [
            r["record"]
            for r in records
            if r["link"]["source_table"] == table and r["link"]["role"] == "acquisition"
        ]
        if not candidates and table in {"pvt_assessment", "screenresult"}:
            expected = "pvt" if table == "pvt_assessment" else "screen"
            for item in records:
                if (
                    item["link"]["source_table"] == "archived_assessment"
                    and item["record"].get("experiment_id") == expected
                ):
                    original = json.loads(item["record"]["snapshot_json"])
                    # Archive identity is preserved separately; never look up its reused original ID.
                    original["id"] = "archive:" + str(item["record"]["id"])
                    candidates.append(original)
        if len(candidates) != 1:
            raise ValueError(f"Exact acquisition source missing or ambiguous: {table}")
        return candidates[0]

    source = dict(
        instrument=instrument,
        attempt_id=attempt.id,
        records=records,
        files={},
        verified=False,
    )
    if instrument == "pvt":
        row = one("pvt_assessment")
        timing = json.loads(row["timing_evidence_json"])
        ordinal = db.execute(
            text("SELECT visit_ordinal FROM visit WHERE id=:id"),
            dict(id=row["visit_id"]),
        ).scalar_one()
        raw = dict(
            participant_id=row["participant_id"],
            visit_ordinal=ordinal,
            kss_score=row["kss_score"],
            administered_at=row["administered_at"],
            duration_ms=row["duration_ms"],
            trials=json.loads(row["raw_trials_json"]),
            execution_purpose=row["execution_purpose"],
            **{k: v for k, v in timing.items() if k != "validity_reasons"},
        )
        from matb_integration.pvt_scoring import PvtAssessmentIn, _metrics

        body = PvtAssessmentIn.model_validate(raw)
        source.update(
            raw=raw,
            verified=row["pvt_version"] == 2
            and _metrics(body.trials, duration_ms=body.duration_ms)
            == json.loads(row["metrics_json"]),
            protocol_valid=bool(row["protocol_valid"]),
        )
    elif instrument == "screen":
        row = one("screenresult")
        from matb_integration.screen.scoring import score_screen

        raw = json.loads(row["raw_trials_json"])
        source.update(
            raw=raw,
            screen_id=str(row["id"]),
            verified=row["screen_version"] == 2
            and score_screen(raw) == json.loads(row["scores_json"]),
        )
    elif instrument == "questionnaire":
        row = one("study_native_rating")
        source.update(
            raw=json.loads(row["payload_json"]),
            verified=digest(row["payload_json"].encode()) == row["payload_sha256"],
            target_attempt_id=row["target_attempt_id"],
        )
    elif instrument == "openmatb":
        row = one("evidence_capture")
        capture = db.get(EvidenceCapture, row["id"])
        from app.evidence_service import source_artifacts

        selected = []
        for identity in metric_ids:
            metric = db.get(EvidenceMetric, identity)
            if metric is None or metric.capture_id != capture.id:
                raise ValueError(
                    "Native metric ID is outside this exact attempt capture."
                )
            selected.append(metric)
        if not selected or len({m.run_id for m in selected}) != 1:
            raise ValueError(
                "Explicit native metric IDs from exactly one preserved derivation are required."
            )
        run = db.get(EvidenceRun, selected[0].run_id)
        source.update(
            raw=dict(
                artifacts={
                    k: encoded(v) for k, v in source_artifacts(db, capture.id).items()
                },
                derivation_version=run.version,
                analysis_execution=json.loads(run.result_json).get(
                    "analysis_execution"
                ),
            ),
            selected_metrics=[m.model_dump(mode="json") for m in selected],
            capture=capture.model_dump(mode="json"),
            run=run.model_dump(mode="json"),
            verified=all(m.eligible for m in selected),
        )
    elif instrument in {"liftoff", "suas"}:
        table = "liftoff_session" if instrument == "liftoff" else "simulation_session"
        row = one(table)
        inventory = [
            dict(r)
            for r in db.execute(
                text(
                    f'SELECT * FROM {"liftoff_artifact" if instrument=="liftoff" else "simulation_artifact"} WHERE session_id=:id'
                ),
                dict(id=row["id"]),
            ).mappings()
        ]
        files = _files(row["artifact_root"], inventory)
        source.update(
            files=files,
            inventory=inventory,
            verified=bool(files),
            protocol_valid=row.get("validity") == "valid",
        )
        if instrument == "liftoff":
            if row["telemetry_profile"] != "liftoff-telemetry-all-v1":
                raise ValueError(
                    "Unsupported canonical telemetry profile; packet context cannot be recovered."
                )
            source["packet_context"] = dict(
                profile=row["telemetry_profile"],
                motor_count_basis="fixed_four_by_existing_protocol_decoder",
                original_datagram_metadata_recovered=False,
            )
            visible = (
                db.execute(
                    text("SELECT * FROM liftoff_result WHERE session_id=:id"),
                    dict(id=row["id"]),
                )
                .mappings()
                .one()
            )
            source["raw"] = dict(
                telemetry=[
                    json.loads(line)
                    for line in base64.b64decode(files["telemetry.jsonl"]).splitlines()
                ],
                visible_results=dict(
                    valid_lap_times_s=json.loads(visible["valid_lap_times_json"]),
                    invalid_laps=visible["invalid_laps"],
                    observer_restart_count=visible["observer_restart_count"],
                ),
            )
            source["visible_results_record"] = dict(visible)
        else:
            streams = {}
            for name, data in files.items():
                if not name.endswith("events.jsonl"):
                    continue
                directory = name[: -len("events.jsonl")]
                streams[name] = dict(
                    records=[
                        json.loads(line)
                        for line in base64.b64decode(data).splitlines()
                        if line
                    ],
                    manifest=json.loads(
                        base64.b64decode(files[directory + "manifest.json"])
                    ),
                )
            if not streams:
                raise ValueError("No preserved mission event stream.")
            source["raw"] = dict(streams=streams)
    elif instrument == "physiology":
        row = one("polar_capture")
        manifest = json.loads(row["manifest_json"] or "{}")
        files = _files(row["artifact_root"], manifest.get("artifacts", []))
        markers = [
            dict(r)
            for r in db.execute(
                text(
                    "SELECT * FROM polar_capture_marker WHERE capture_id=:id ORDER BY sequence"
                ),
                dict(id=row["id"]),
            ).mappings()
        ]
        source.update(
            files=files,
            manifest=manifest,
            verified=bool(files) and row["artifact_state"] == "finalized",
            raw=dict(rr_parquet=files["rr.parquet"], markers=markers),
        )
    else:
        raise ValueError("Unsupported source adapter.")
    return source
