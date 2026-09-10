"""Purpose provenance; callers own transactions, raw purpose is never rewritten.

An explicit event attests a newly declared request, not retrospective scientific
eligibility. Consumers must independently apply their analysis-plan rules.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import inspect, text
from sqlmodel import Session, select

from .purpose_models import PurposeClassification, PurposeProvenance

ACQUISITION_TABLES = (
    'screenresult', 'pvt_assessment', 'practiceresult', 'openmatb_suite_session',
    'liftoff_session', 'polar_capture', 'simulation_session', 'technical_simulation_session',
    'archived_assessment', 'assessment_attempt',
)


def _identity(db, *, table, source_id, purpose, snapshot):
    row = PurposeProvenance(source_table=table, source_id=str(source_id), recorded_purpose=purpose,
        source_snapshot_sha256=hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest())
    db.add(row)
    db.flush()
    return row.id


def _append(db, identity, *, purpose, classification, actor, reason, references=()):
    row = PurposeClassification(provenance_id=identity, purpose=purpose,
        classification=classification, actor=actor, reason=reason,
        supporting_references_json=json.dumps(list(references), allow_nan=False))
    db.add(row)
    db.flush()
    return row


def declare_acquisition(db: Session, row, *, purpose: str, attempt_id: str | None = None) -> str:
    """Persist a new row and explicit request declaration in the caller's transaction.

    Never call for historical imports; use migration + retrospective review.
    Existing identities cannot receive another prospective declaration.
    """
    if row.__tablename__ not in ACQUISITION_TABLES:
        raise ValueError('unsupported acquisition record')
    if getattr(row, 'execution_purpose', purpose) != purpose:
        raise ValueError('record and declaration purpose mismatch')
    if purpose not in {'practice', 'study'}:
        raise ValueError('invalid execution purpose')
    if row.purpose_provenance_id is not None or inspect(row).persistent or inspect(row).detached:
        raise ValueError('explicit declaration requires a new acquisition')
    if attempt_id is not None:
        from .assessment_service import bind_new_source
        return bind_new_source(db, attempt_id, row, purpose=purpose)
    db.add(row)
    db.flush()
    identity = _identity(db, table=row.__tablename__, source_id=row.id,
                         purpose=purpose, snapshot=row.model_dump(mode='json'))
    row.purpose_provenance_id = identity
    db.add(row)
    _append(db, identity, purpose=purpose, classification='explicit', actor='local:acquisition-request',
            reason='Purpose explicitly declared in the new acquisition request')
    if row.__tablename__ != "assessment_attempt":
        from .assessment_adapters import attach_source
        attempt = attach_source(db, row.__tablename__, row.model_dump(mode="json"), historical=False)
        if attempt is not None and hasattr(row, "attempt_id"):
            row.attempt_id = attempt.id
            db.add(row)
            db.flush()
    return identity


def classify_retrospectively(db: Session, identity: str, *, purpose: str,
                            reviewer: str, reason: str, supporting_references=()):
    """Append a named local attestation; does not mutate records or earlier events."""
    if purpose not in {'practice', 'study', 'exploration'} or not reviewer.strip() or not reason.strip():
        raise ValueError('valid purpose, named reviewer and reason are required')
    if reviewer.strip().startswith(('system:', 'local:')):
        raise ValueError('reserved system actor prefix')
    if db.get(PurposeProvenance, identity) is None:
        raise KeyError(identity)
    return _append(db, identity, purpose=purpose, classification='retrospective',
        actor=reviewer.strip(), reason=reason.strip(), references=supporting_references)


def provenance_view(db: Session, identity: str) -> dict:
    row = db.get(PurposeProvenance, identity)
    if row is None:
        raise KeyError(identity)
    history = []
    for event in db.exec(select(PurposeClassification).where(
            PurposeClassification.provenance_id == identity).order_by(PurposeClassification.id)).all():
        item = event.model_dump(mode='json')
        item['supporting_references'] = json.loads(item.pop('supporting_references_json'))
        history.append(item)
    return {**row.model_dump(mode='json'), 'current': history[-1] if history else None, 'history': history}


def migrate_purpose_provenance(engine) -> None:
    """Idempotently label unsupported historic intent unknown at migration time.

    Fast-mode inference is a system retrospective event, never a human decision
    or fabricated acquisition date. Legacy purpose and payload bytes are retained.
    """
    PurposeProvenance.__table__.create(engine, checkfirst=True)
    PurposeClassification.__table__.create(engine, checkfirst=True)
    with Session(engine) as db:
        connection = db.connection()
        tables = set(inspect(connection).get_table_names())
        for table in ACQUISITION_TABLES:
            if table not in tables:
                continue
            columns = {c['name'] for c in inspect(connection).get_columns(table)}
            if 'purpose_provenance_id' not in columns:
                connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN purpose_provenance_id VARCHAR'))
            rows = connection.execute(text(f'SELECT * FROM "{table}" WHERE purpose_provenance_id IS NULL')).mappings().all()
            for original in rows:
                snapshot = dict(original)
                if table == 'archived_assessment':
                    try:
                        archived = json.loads(snapshot.get('snapshot_json', '{}'))
                        snapshot['execution_purpose'] = archived.get('execution_purpose', 'study')
                    except (ValueError, AttributeError, TypeError):
                        pass
                purpose = snapshot.get('execution_purpose') or ('practice' if table in {'practiceresult', 'technical_simulation_session'} else 'study')
                identity = _identity(db, table=table, source_id=snapshot['id'], purpose=purpose, snapshot=snapshot)
                _append(db, identity, purpose=purpose, classification='unknown', actor='system:migration',
                        reason='Historical recorded purpose retained; prospective declaration evidence unavailable')
                fast = False
                if table == 'screenresult':
                    # Preserve the old SQLite migration predicate, including
                    # JSON true, 1 and 1.0; new HTTP requests remain strict booleans.
                    fast = connection.execute(text(
                        "SELECT CASE WHEN json_valid(:raw) THEN "
                        "json_extract(:raw, '$.fast_mode') = 1 ELSE 0 END"
                    ), {'raw': snapshot.get('raw_trials_json')}).scalar_one() == 1
                if table == 'pvt_assessment':
                    fast = snapshot.get('pvt_version') == 1 and snapshot.get('protocol_valid') == 0
                if fast:
                    _append(db, identity, purpose='practice', classification='retrospective', actor='system:migration',
                        reason='Legacy fast-screen flag or invalid version-1 PVT inferred practice; no human attestation')
                connection.execute(text(f'UPDATE "{table}" SET purpose_provenance_id=:identity WHERE id=:id'),
                    {'identity': identity, 'id': snapshot['id']})
        db.commit()


def historical_association_identity(db, *, source_table, source_id, purpose, snapshot):
    """Append unknown provenance for an imported instance lacking its own ledger.

    This is an association migration, never a prospective declaration. In particular
    a historic practice block cannot borrow the enclosing study suite declaration.
    """
    identity = _identity(db, table=source_table, source_id=source_id, purpose=purpose, snapshot=snapshot)
    _append(db, identity, purpose=purpose, classification='unknown', actor='system:migration',
            reason='Historical instance association; prospective declaration evidence unavailable')
    return identity
