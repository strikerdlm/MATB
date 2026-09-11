"""Deferred optional mission replay/derivation after indispensable raw closure."""
import json
from pathlib import Path

MANAGERS={}


def finalize(engine,payload):
    from app.simulation_persistence import SQLModelSimulationPersistence
    from matb_integration.suas.recording.recorder import SessionRecorder
    from matb_integration.suas.recording.replay import ReplayVerifier,effective_records
    from matb_integration.suas.recording.artifacts import artifact_inventory,verify_checksum_file
    from matb_integration.suas.metrics.debrief import build_public_debrief,block_metric_summary
    from matb_integration.suas.metrics.research import derive_research_metrics
    from matb_integration.suas.domain.serialization import canonical_json
    from app.simulation_runtime import _read_records
    manager=MANAGERS.get(str(engine.url))
    persistence=manager.persistence if manager else SQLModelSimulationPersistence(engine)
    root=Path(payload['run_dir'])
    if (root/'checksums.sha256').exists():
        if verify_checksum_file(root/'checksums.sha256'): raise ValueError('Existing mission artifact checksum mismatch')
        persistence.replace_artifacts(payload['session_id'],artifact_inventory(root,partial=payload['disposition']=='abort'))
        return
    recorder=SessionRecorder.open_existing(root);recorder.close()
    if payload['disposition']=='abort':
        persistence.replace_artifacts(payload['session_id'],recorder.seal_partial(reason='aborted'));return
    manifest=json.loads((root/'manifest.json').read_text())
    replay=ReplayVerifier().verify(root)
    if replay.status.value!='match': raise ValueError('Mission replay did not match; raw source retained')
    records=_read_records(root/'events.jsonl')
    debrief,questionnaires=build_public_debrief(root,manifest,replay,records,validity=payload['validity'],live_frames=payload['live_frames'])
    artifacts=recorder.seal(questionnaires=questionnaires,metrics=debrief.get('metrics',{}),debrief=debrief,replay=replay)
    persistence.replace_artifacts(payload['session_id'],artifacts)
    effective=tuple(effective_records(records))
    for block_id in sorted({record.block_id for record in effective}):
        block_records=tuple(record for record in effective if record.block_id==block_id)
        metrics={**block_metric_summary(block_records,manifest),**derive_research_metrics(block_records).to_dict(),'calculation_version':'suas-debrief-v2'}
        persistence.update_block(payload['session_id'],block_id,metrics_json=canonical_json(metrics))
