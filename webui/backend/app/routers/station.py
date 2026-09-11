"""Local researcher station status, explicit closure, recovery and bounded job artifacts."""
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from app.db import get_session
from app import station_resources as service

router=APIRouter(prefix='/station',tags=['station resources'])


class Attestation(BaseModel):
    actor: str=Field(min_length=1,max_length=200)
    reason: str=Field(min_length=1,max_length=2000)


class Maintenance(Attestation):
    enabled: bool


@router.get('')
def status(db: Session=Depends(get_session)):
    return service.snapshot(db)


@router.post('/close')
def close(body: Attestation,db: Session=Depends(get_session)):
    service.close_visit(db,**body.model_dump());db.commit();return service.snapshot(db)


@router.post('/recover-idle')
def recover(body: Attestation,request: Request,db: Session=Depends(get_session)):
    # Do not trust a client-provided PID list or disconnect as proof of idle.
    from app.station_worker import MANAGERS
    native=MANAGERS.get(str(db.get_bind().url))
    pids=[]
    if native:
        pids.extend(h.process.pid for h in native._handles.values() if h.process.returncode is None)
        if native._preview.handle: pids.append(native._preview.handle.process.pid)
        from app.openmatb_models import OpenMatbSuiteSession
        for row in db.exec(select(OpenMatbSuiteSession)):
            if row.active_pid: pids.append(row.active_pid)
            if row.recovery_pid: pids.append(row.recovery_pid)
    for name in ('polar_manager','physiology_manager','liftoff_manager','simulation_manager'):
        runtime=getattr(request.app.state,name,None)
        handle=getattr(runtime,'_handle',None) if runtime else None
        if runtime and (getattr(runtime,'_capture',None) or (handle and handle.lifecycle not in {'FINISHED','ABORTED','INTERRUPTED'})):
            service.blocked('station_runtime_active','Stop the runtime recording before idle recovery.')
    service.recover_idle(db,native_pids=pids,**body.model_dump());db.commit();return service.snapshot(db)


@router.post('/maintenance')
def maintenance(body: Maintenance,db: Session=Depends(get_session)):
    service.maintenance(db,**body.model_dump());db.commit();return service.snapshot(db)


@router.get('/jobs')
def jobs(db: Session=Depends(get_session)):
    return [service.public_job(j) for j in db.exec(select(service.StationJob).order_by(service.StationJob.created_at.desc()).limit(100))]


@router.get('/jobs/{identity}')
def job(identity: str,db: Session=Depends(get_session)):
    row=db.get(service.StationJob,identity)
    if row is None: raise HTTPException(404,'Station job not found')
    return service.public_job(row)


@router.post('/jobs/{identity}/cancel')
def cancel(identity: str,db: Session=Depends(get_session)):
    row=service.cancel_job(db,identity);db.commit();return service.public_job(row)


@router.get('/jobs/{identity}/artifact')
def artifact(identity: str,db: Session=Depends(get_session)):
    row=db.get(service.StationJob,identity)
    if row is None or not row.result_json or row.status not in {'complete','failed','cancelled'}:
        raise HTTPException(409,'Job artifact is not complete')
    result=json.loads(row.result_json)
    from app.station_http import artifact_root
    path=artifact_root(db.get_bind())/(row.id+'.response')
    headers=dict(result['headers'])
    return FileResponse(path,media_type=headers.get('content-type','application/octet-stream'),filename=row.id+('.zip' if 'zip' in headers.get('content-type','') else '.json'))


@router.get('/events')
def events(db: Session=Depends(get_session)):
    return db.exec(select(service.StationEvent).order_by(service.StationEvent.created_at.desc()).limit(100)).all()


@router.post('/backups')
def create_backup(body: Attestation, db: Session = Depends(get_session)):
    """A bounded control request; SQLite holds exclusion while streaming files to disk."""
    from pathlib import Path
    import tempfile
    from starlette.background import BackgroundTask
    from app.study_backup import backup
    database = db.get_bind().url.database
    if not database or database == ':memory:':
        raise HTTPException(409, 'Whole-study backup requires a file-backed workspace')
    row = service.lock(db)
    service.attest(db, 'backup_requested', body.actor, body.reason, row)
    db.commit()
    folder = tempfile.TemporaryDirectory(prefix='matb-study-backup-')
    target = Path(folder.name) / 'study.zip'
    try:
        backup(database, target)
    except (ValueError, OSError) as exc:
        folder.cleanup()
        raise HTTPException(409, str(exc)) from exc
    return FileResponse(target, filename='matb-whole-study.zip', media_type='application/zip',
                        background=BackgroundTask(folder.cleanup))
