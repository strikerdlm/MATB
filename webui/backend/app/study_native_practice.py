"""Read actual reconciled practice metrics before any measurement reservation opens."""
import json
from sqlmodel import select
from .study_preparation import fail, digest


def observe_practice(db, preparation, attempt):
    from .assessment_models import AssessmentSourceLink
    from .openmatb_models import OpenMatbSuiteSession, OpenMatbBlockAttempt
    from .evidence_models import EvidenceCapture, EvidenceRun, EvidenceMetric, EvidenceRecord
    from .study_preflight import snapshot_for_attempt
    link = db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.attempt_id == attempt.id,
        AssessmentSourceLink.source_table == 'openmatb_suite_session')).first()
    if not link: fail('Complete the exact native practice runtime first.')
    suite = db.get(OpenMatbSuiteSession, link.source_id)
    snapshot = snapshot_for_attempt(db, attempt.id)
    if suite.lifecycle not in {'COMPLETE','ABORTED','FAILED','INTERRUPTED'}: fail('Finish native practice before grading.')
    from .assessment_service import transition
    if attempt.acquisition_state == 'started':
        transition(db, attempt.id, 'finished' if suite.lifecycle == 'COMPLETE' else 'interrupted', None if suite.lifecycle == 'COMPLETE' else 'unknown')
    blocks = db.exec(select(OpenMatbBlockAttempt).where(OpenMatbBlockAttempt.session_id == suite.id)).all()
    if len(blocks) > 1: fail('Select a standalone native practice with one exact block.')
    block = blocks[0] if blocks else None
    failure = dict(session_id=suite.id, snapshot=json.loads(snapshot.snapshot_json) if snapshot else None,
        outcome=suite.lifecycle, failure=suite.last_error)
    if not snapshot or json.loads(snapshot.snapshot_json)['issues']:
        return {}, None, {**failure, 'failure':'practice_mapping_unavailable'}, block or suite
    if block is None: return {}, None, {**failure, 'failure':'practice_not_acquired'}, suite
    if block.evidence_status in {'queued','processing','awaiting_completion'}:
        fail('Practice observations are still processing; retry grading before opening measurement.')
    if not block.capture_id: return {}, None, {**failure, 'failure':'practice_capture_unavailable'}, block
    capture = db.get(EvidenceCapture, block.capture_id)
    if (not capture or capture.block_instance_id != block.id or capture.parent_session_id != suite.id
            or capture.participant_id != preparation.participant_id or capture.execution_purpose != 'practice'):
        fail('Practice capture identity differs from the exact native block; inspect original sources.')
    runs = db.exec(select(EvidenceRun).where(EvidenceRun.capture_id == block.capture_id, EvidenceRun.status == 'succeeded')).all()
    if not runs:
        return {}, None, {**failure, 'capture_id':block.capture_id, 'failure':'practice_derivation_unsuccessful'}, block
    # Repeated derivations must agree; conflicting derivations require explicit research review.
    fingerprints = {r.fingerprint for r in runs}
    if len(fingerprints) != 1: fail('Practice derivations disagree; review the exact evidence before using competence.')
    run = sorted(runs, key=lambda r:r.id)[0]
    metrics = db.exec(select(EvidenceMetric).where(EvidenceMetric.run_id == run.id)).all()
    metric_names = {'sysmon_hit_rate':'sysmon.hit_rate', 'track_rmse_deviation':'track.rmse_deviation'}
    observations = {metric_names[m.key]:m.value for m in metrics if m.key in metric_names and m.status == 'succeeded'}
    records = db.exec(select(EvidenceRecord).where(EvidenceRecord.capture_id == block.capture_id, EvidenceRecord.stream == 'events')).all()
    times = [json.loads(r.record_json).get('scenario_time_ns') for r in records]
    known = [t for t in times if isinstance(t, int)]
    seconds = (max(known) - min(known)) / 1e9 if len(known) > 1 else None
    return observations, seconds, dict(capture_id=block.capture_id, run_id=run.id, fingerprint=run.fingerprint,
        metric_ids=[m.id for m in metrics], snapshot=json.loads(snapshot.snapshot_json)), block
