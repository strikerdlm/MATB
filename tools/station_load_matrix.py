#!/usr/bin/env python3
"""Runnable software-only station load observations; no hardware qualification.

Example (from backend): PYTHONPATH=.:/tmp/matb-predictability-testdeps python
../../tools/station_load_matrix.py --output ../../.test-tmp/repeatable-study/load

Exercises actual simulated H10 decode/queues/Parquet closure and durable station
admission. Scheduler frame gaps are event-loop observations, NOT physical display
latency. The synthetic foreground labels do not execute native/flight stimuli.
"""
import argparse
import asyncio
from datetime import date
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'webui/backend'))
sys.path.insert(0,str(ROOT))
from sqlmodel import Session, SQLModel, create_engine
from app import assessment_models, purpose_models, study_models, study_registry_models, study_analysis_models, evidence_models
from app.models import Participant
from app.physiology_runtime import PolarCaptureManager
from app import station_resources as station
from matb_integration.physiology.transport import SimulatedPolarTransport


async def scenario(output,phase):
    folder=output/phase;folder.mkdir(parents=True,exist_ok=False)
    engine=create_engine('sqlite:///'+str(folder/'station.db'),connect_args={'check_same_thread':False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db: db.add(Participant(id='P01',enrollment_date=date.today()));db.commit()
    transport=SimulatedPolarTransport()
    manager=PolarCaptureManager(engine=engine,artifact_root=folder/'raw',transport=transport)
    await manager.startup();token,_=(await manager.scan(.25))[0];await manager.connect(token)
    capture,lease=manager.create_capture(participant_id='P01',session_kind='generic',session_id='synthetic-load',execution_purpose='practice',settings={'ecg_sample_rate_hz':130,'ecg_resolution_bits':14,'acc_sample_rate_hz':50,'acc_resolution_bits':16,'acc_range_g':2})
    await manager.start_capture(capture.capture_id,lease)
    with Session(engine) as db:
        # Frozen-protocol lane pairing is covered separately by the integration tests.
        # Here the real raw pipeline owns its standalone acquisition reservation.
        for kind in ('import','reconcile','analysis','export','assets'):
            station.enqueue(db,'software_load_'+kind,{'scenario':phase})
        db.commit()
        assert station.claim_job(db) is None
    gaps=[];high_water=0;start=time.perf_counter();last=start
    for index in range(40):
        transport.emit_hr(bytes.fromhex('16 3c 00 04'))
        transport.emit_ecg(10_000_000_000+index*100_000_000,tuple(range(13)))
        transport.emit_acc(10_000_000_000+index*100_000_000,tuple((0,0,1000) for _ in range(5)))
        high_water=max(high_water,max(q.qsize() for q in manager._capture.queues.values()))
        await asyncio.sleep(.01)
        tick=time.perf_counter();gaps.append((tick-last)*1000);last=tick
    await manager.add_marker(capture.capture_id,lease,phase,{'evidence':'software_only'})
    before=time.perf_counter();final=await manager.stop_capture(capture.capture_id,lease);closure_ms=(time.perf_counter()-before)*1000
    row,manifest,partials=manager.inventory(capture.capture_id,lease)
    assert final.lifecycle=='complete' and manifest and not partials
    # Explicit whole-visit gap model, independent of raw physiology source above.
    with Session(engine) as db:
        station.admit(db,'synthetic-foreground',instrument='pvt',owner='assignment:software-load',participant='P01',visit=1)
        station.finish(db,'synthetic-foreground');db.commit()
        assert station.claim_job(db) is None
        queued=len(station.snapshot(db)['jobs'])
        station.close_visit(db,actor='Software load harness',reason=phase+' gap finished');db.commit()
        job=station.claim_job(db);db.commit()
        assert job is not None
        station.finish_job(db,job.id,result={'synthetic':True});db.commit()
    await manager.shutdown()
    sizes={p.relative_to(folder).as_posix():p.stat().st_size for p in folder.rglob('*') if p.is_file()}
    return dict(phase=phase,status='software_only',samples=manifest.stream_counters,queue_high_water_packets=high_water,queue_limit_packets=manager.QUEUE_PACKETS,
                deferred_heavy_jobs=queued,scheduler_frame_gap_ms={'maximum':max(gaps),'mean':sum(gaps)/len(gaps)},raw_closure_ms=closure_ms,
                elapsed_seconds=time.perf_counter()-start,disk_bytes=sum(sizes.values()),artifacts=sizes,incomplete_reasons=list(manifest.incomplete_reasons))


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    rows=[]
    for phase in ('foreground_collection','ratings_gap','recovery_gap'):
        rows.append(await scenario(output,phase))
    report=dict(status='software_only',hardware_qualification=False,physical_frame_timing=False,native_stimuli_executed=False,
                observations=rows,limits='Synthetic H10 transport and event-loop scheduler; no BLE radio, physical display, simulator, controller or station certification.')
    (output/'observations.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__': asyncio.run(main())
