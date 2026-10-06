"""Durable station admission. Every mutation shares SQLite's single writer lock.

A reservation survives every task/rating/recovery gap until explicit visit close.
Cancellation is a request: running ownership ends only after actual work returns.
"""
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Field, Session, SQLModel, select

MAX_QUEUE = 32
MAX_PAYLOAD = 128 * 1024


class StationState(SQLModel, table=True):
    __tablename__ = 'station_state'
    id: int = Field(default=1, primary_key=True)
    revision: int = 0
    reservation_json: str = 'null'
    lanes_json: str = '{}'
    maintenance: bool = False
    maintenance_actor: str | None = None


class StationJob(SQLModel, table=True):
    __tablename__ = 'station_job'
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    kind: str
    payload_json: str
    deduplication: str = Field(index=True)
    status: str = 'queued'
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    result_json: str | None = None


class StationEvent(SQLModel, table=True):
    __tablename__ = 'station_event'
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    kind: str
    actor: str
    reason: str
    snapshot_json: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def now():
    return datetime.now(timezone.utc).isoformat()


def lock(db):
    db.execute(text('INSERT OR IGNORE INTO station_state (id,revision,reservation_json,lanes_json,maintenance) VALUES (1,0,\'null\',\'{}\',0)'))
    db.execute(text('UPDATE station_state SET revision=revision+1 WHERE id=1'))
    row = db.get(StationState, 1)
    db.refresh(row)
    return row


def blocked(code, message):
    raise HTTPException(409, dict(code=code, message=message, station_url='/station', next_action='Inspect station status; stop acquisition and explicitly close or recover the visit.'))


def snapshot(db):
    row = db.get(StationState, 1)
    jobs = db.exec(select(StationJob).where(StationJob.status.in_(['queued','running','cancelling','uncertain','waiting_capacity'])).order_by(StationJob.created_at)).all()
    return dict(reservation=json.loads(row.reservation_json) if row else None,
                acquisitions=json.loads(row.lanes_json) if row else {}, maintenance=bool(row and row.maintenance),
                jobs=[public_job(j) for j in jobs], queue_limit=MAX_QUEUE)


def public_job(job):
    return job.model_dump(exclude={'payload_json','deduplication'})


def running(db):
    return db.exec(select(StationJob).where(StationJob.status.in_(['running','cancelling','uncertain']))).first()


def _independent_physiology_pair(left, right):
    """An unlinked practice recording may coexist with one standalone task."""
    if not all(item['owner'].startswith('standalone:') for item in (left, right)):
        return False
    if bool(left.get('independent_physiology')) == bool(right.get('independent_physiology')):
        return False
    physiology, foreground = (left, right) if left.get('independent_physiology') else (right, left)
    return physiology['instrument'] == 'physiology' and foreground['instrument'] != 'physiology'


def admit(db, source, *, instrument, owner, participant=None, visit=None, occasion_key=None, group=None, accompanying=None, attempt_id=None, held=False, pid=None, initializing=False, independent_physiology=False):
    row = lock(db)
    if row.maintenance or running(db): blocked('station_heavy_work_active', 'Heavy work or maintenance owns the station.')
    reservation = json.loads(row.reservation_json)
    lanes = json.loads(row.lanes_json)
    proposed = dict(initializing=initializing,instrument=instrument,owner=owner,participant=participant,visit=visit,occasion_key=occasion_key,group=group,accompanying=accompanying,attempt_id=attempt_id,held=held,pid=pid)
    if independent_physiology:
        proposed['independent_physiology'] = True
    if reservation and reservation.get('uncertain'): blocked('station_recovery_required', 'Lost acquisition ownership requires explicit idle recovery.')
    if reservation and (reservation['owner'],reservation.get('participant'),reservation.get('visit')) != (owner,participant,visit):
        reserved = [other for other in lanes.values() if other['owner'] == reservation['owner']]
        if not reserved or not all(_independent_physiology_pair(proposed, other) for other in reserved):
            blocked('station_visit_reserved', 'Another participant visit owns the station.')
    if held and initializing and reservation and any(key != source for key in lanes):
        blocked('station_preflight_requires_idle','Complete native preparation before opening the protected visit.')
    for key, other in lanes.items():
        if key == source: continue
        if _independent_physiology_pair(proposed, other) and not other.get('initializing'):
            continue
        if (other['owner'],other['participant'],other['visit']) != (owner,participant,visit):
            blocked('station_visit_reserved','A held or active runtime belongs to another visit.')
        if other.get('initializing'):
            blocked('station_preflight_initializing','Wait for the held native preflight to finish initializing before baseline.')
        # Actual prepared native runtime is idle until the same process is released.
        if held or other['held']: continue
        paired = (instrument == 'physiology') != (other['instrument'] == 'physiology')
        physiology = proposed if instrument == 'physiology' else other
        foreground = other if instrument == 'physiology' else proposed
        if not (paired and group and group == other['group'] and physiology['accompanying'] == foreground['occasion_key']):
            blocked('station_acquisition_conflict', 'Only the frozen protocol declared physiology/foreground pair may overlap.')
    lanes[source] = proposed
    if not held:
        row.reservation_json = json.dumps(reservation or dict(owner=owner,participant=participant,visit=visit,opened_at=now(),uncertain=False))
    row.lanes_json = json.dumps(lanes)
    db.add(row); db.flush()


def admit_attempt(db, attempt, *, source=None, held=False, pid=None, initializing=False, independent_physiology=False):
    from .assessment_models import AssessmentOccasion
    occasion = db.get(AssessmentOccasion, attempt.occasion_id)
    context = {}
    if attempt.execution_purpose == 'study':
        from .study_admission import for_occasion
        context = for_occasion(db, occasion.id)
    else:
        from .study_preparation import practice_context
        preparation=practice_context(db,attempt.id)
        state=lock(db);reservation=json.loads(state.reservation_json)
        if preparation and reservation and reservation['owner']=='assignment:'+preparation['assignment_id']:
            if occasion.instrument=='openmatb':
                blocked('native_practice_requires_idle','Finish and grade native practice before opening measurement collection.')
            context=preparation
    admit(db,source or attempt.id,instrument=occasion.instrument,
          owner='assignment:'+context['assignment_id'] if context else 'standalone:'+(source or attempt.id),
          participant=occasion.participant_id,visit=occasion.visit_id,
          occasion_key=context.get('occasion_key',context.get('key')),group=context.get('collection_group'),
          accompanying=context.get('accompanying_key'),attempt_id=attempt.id,held=held,pid=pid,initializing=initializing,
          independent_physiology=independent_physiology and attempt.execution_purpose == 'practice' and not context)


def admit_source(db, source, *, held=False, pid=None, initializing=False):
    from app.artifact_paths import require_new_acquisition
    require_new_acquisition(db, source.__tablename__, source.id)
    from .assessment_adapters import source_attempt
    attempt = source_attempt(db, source.__tablename__, source.id)
    independent = (source.__tablename__ == 'polar_capture'
                   and source.execution_purpose == 'practice' and source.matb_session_kind == 'generic')
    admit_attempt(db,attempt,source=source.__tablename__+':'+str(source.id),held=held,pid=pid,initializing=initializing,
                  independent_physiology=independent)
    if not held and attempt.acquisition_state == 'created':
        from .assessment_service import transition
        transition(db,attempt.id,'started',native_session_id=source.id if source.__tablename__ == 'openmatb_suite_session' else None)


def finish(db, source, *, uncertain=False):
    row = lock(db); lanes = json.loads(row.lanes_json)
    affected = [key for key,value in lanes.items() if key == source or value.get('attempt_id') == source]
    if not affected: return
    reservation = json.loads(row.reservation_json)
    if uncertain:
        if reservation is None:
            value=lanes[affected[0]]
            reservation=dict(owner=value['owner'],participant=value['participant'],visit=value['visit'],opened_at=now())
        reservation['uncertain']=True
    else:
        for key in affected: del lanes[key]
        if reservation and reservation['owner'].startswith('standalone:'):
            if not lanes:
                reservation = None
            elif not any(value['owner'] == reservation['owner'] for value in lanes.values()):
                remaining = next(iter(lanes.values()))
                reservation = {**reservation, **{key: remaining[key] for key in ('owner', 'participant', 'visit')}}
    row.lanes_json=json.dumps(lanes);row.reservation_json=json.dumps(reservation);db.add(row);db.flush()


def close_visit(db, *, actor, reason):
    row=lock(db)
    if json.loads(row.lanes_json): blocked('station_acquisition_active','Stop every recording and close the held native runtime before closing the visit.')
    reservation=json.loads(row.reservation_json)
    if reservation and reservation.get('uncertain'): blocked('station_recovery_required','Use explicit idle recovery for uncertain ownership.')
    attest(db,'close',actor,reason,row)
    row.reservation_json='null';db.add(row)


def attest(db,kind,actor,reason,row):
    if not actor.strip() or not reason.strip(): raise HTTPException(422,'Named actor and reason required.')
    db.add(StationEvent(kind=kind,actor=actor.strip(),reason=reason.strip(),snapshot_json=json.dumps(row.model_dump())))


def recover_idle(db, *, actor, reason, native_pids):
    from .native_process_guard import process_alive
    row=lock(db)
    lanes=json.loads(row.lanes_json)
    pids=set(native_pids)|{v['pid'] for v in lanes.values() if v.get('pid')}
    if any(process_alive(pid) for pid in pids): blocked('station_native_process_alive','A retained native process is still alive; terminate it before recovery.')
    if running(db): blocked('station_worker_not_terminated','Actual worker termination must be established before recovery.')
    attest(db,'idle_recovery',actor,reason,row)
    from .assessment_models import AssessmentAttempt
    for lane in lanes.values():
        attempt=db.get(AssessmentAttempt,lane['attempt_id']) if lane.get('attempt_id') else None
        if attempt and attempt.acquisition_state=='started':
            attempt.acquisition_state='interrupted';attempt.finished_at=datetime.now(timezone.utc);attempt.interruption_category='unknown';db.add(attempt)
    row.reservation_json='null';row.lanes_json='{}';db.add(row)


def maintenance(db, enabled, *, actor, reason):
    row=lock(db)
    if enabled and (json.loads(row.reservation_json) or json.loads(row.lanes_json) or running(db)):
        blocked('station_not_idle','Close/recover acquisition and wait for the running job before maintenance.')
    attest(db,'maintenance_start' if enabled else 'maintenance_end',actor,reason,row)
    row.maintenance=enabled;row.maintenance_actor=actor if enabled else None;db.add(row)


def enqueue(db,kind,payload):
    lock(db)
    encoded=json.dumps(payload,sort_keys=True,separators=(',',':'))
    if len(encoded.encode())>MAX_PAYLOAD: raise HTTPException(413,'Queued payload exceeds 128 KiB; retry large uploads after visit close.')
    digest=hashlib.sha256((kind+encoded).encode()).hexdigest()
    active=db.exec(select(StationJob).where(StationJob.status.in_(['queued','running','cancelling','uncertain','waiting_capacity']))).all()
    for prior in active:
        if prior.deduplication==digest: return prior
    if len(active)>=MAX_QUEUE: raise HTTPException(429,'Station heavy queue is full; cancel pending work or wait.')
    job=StationJob(kind=kind,payload_json=encoded,deduplication=digest);db.add(job);db.flush();return job


def enqueue_source(db,kind,payload):
    """Durable source outbox: recording closure never fails because user jobs filled the queue."""
    try: return enqueue(db,kind,payload)
    except HTTPException as exc:
        if exc.status_code!=429: raise
    encoded=json.dumps(payload,sort_keys=True,separators=(',',':'))
    digest=hashlib.sha256((kind+encoded).encode()).hexdigest()
    prior=db.exec(select(StationJob).where(StationJob.deduplication==digest,StationJob.status=='waiting_capacity')).first()
    if prior: return prior
    job=StationJob(kind=kind,payload_json=encoded,deduplication=digest,status='waiting_capacity')
    db.add(job);db.flush();return job


def claim_job(db, identity=None):
    row=lock(db)
    if json.loads(row.lanes_json) or row.maintenance or running(db): return None
    active=db.exec(select(StationJob).where(StationJob.status=='queued')).all()
    if len(active)<MAX_QUEUE:
        waiting=db.exec(select(StationJob).where(StationJob.status=='waiting_capacity').order_by(StationJob.created_at)).first()
        if waiting: waiting.status='queued';db.add(waiting);db.flush()
    query=select(StationJob).where(StationJob.status=='queued').order_by(StationJob.created_at,StationJob.id)
    # Flat result copies may finish while the participant keeps an idle reservation.
    # Acquisitions still block every job, and running work blocks new admission.
    if json.loads(row.reservation_json): query=query.where(StationJob.kind=='crew_export')
    job=db.exec(query).first()
    if identity and job and job.id!=identity: return None
    if job is None or job.status!='queued': return None
    job.status='running';job.started_at=now();db.add(job);db.flush();return job


def finish_job(db,identity,*,error=None,result=None):
    lock(db);job=db.get(StationJob,identity)
    job.status='failed' if error else ('cancelled' if job.status=='cancelling' else 'complete')
    job.error=error;job.result_json=json.dumps(result) if result else None;job.finished_at=now();db.add(job);db.flush()


def cancel_job(db,identity):
    lock(db);job=db.get(StationJob,identity)
    if job is None: raise HTTPException(404,'Station job not found')
    if job.status in {'queued','waiting_capacity'}: job.status='cancelled';job.finished_at=now()
    elif job.status=='running': job.status='cancelling'
    db.add(job);db.flush();return job


def recover(engine):
    with Session(engine) as db:
        row=lock(db);reservation=json.loads(row.reservation_json);lanes=json.loads(row.lanes_json)
        if reservation or lanes:
            reservation=reservation or dict(owner='recovered:unknown',opened_at=None)
            reservation['uncertain']=True;row.reservation_json=json.dumps(reservation);db.add(row)
            from .assessment_models import AssessmentAttempt
            for lane in lanes.values():
                attempt=db.get(AssessmentAttempt,lane['attempt_id']) if lane.get('attempt_id') else None
                if attempt and attempt.acquisition_state=='started':
                    attempt.acquisition_state='interrupted';attempt.finished_at=datetime.now(timezone.utc);attempt.interruption_category='unknown';db.add(attempt)
        # Backend PID lease is acquired before this; previous process is now proven dead.
        for job in db.exec(select(StationJob).where(StationJob.status.in_(['running','cancelling','uncertain']))):
            finish_job(db,job.id,error='backend_restart: execution interrupted; explicit new request required')
        db.commit()
