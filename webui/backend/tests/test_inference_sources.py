import pytest
from sqlmodel import Session, SQLModel
from matb_integration.inference.contracts import ReviewAnnotationV1, sha256


def test_source_versions_and_artifact_integrity(engine):
    from app.inference_service import create_annotation, resolve_input, InferenceError
    from app.evidence_models import EvidenceCapture, EvidenceArtifact, EvidenceRecord, EvidenceRun
    from app.inference_models import InferenceAnnotation
    SQLModel.metadata.create_all(engine)
    note = ReviewAnnotationV1(annotation_id='n1', capture_id='c1', language='en',
        author_role='participant', source_kind='synthetic', original_text='Tracking was on.',
        created_at_ns='9007199254740993', source_event_ids=('e1',))
    with Session(engine) as db:
        db.add(EvidenceCapture(id='c1', manifest_sha256='a'*64, artifact_fingerprint='b'*64,
            session_id='s', block_instance_id='b', condition='LOW', execution_purpose='practice',
            completion='complete', manifest_json='{}'))
        db.commit()
        artifact = EvidenceArtifact(capture_id='c1', role='events', sha256=sha256(b'original'), content=b'original')
        db.add(artifact)
        db.add(EvidenceRecord(capture_id='c1', stream='events', ordinal=1, record_id='r1', event_id='e1', record_json='{}'))
        db.add(EvidenceRun(id='run1', capture_id='c1', version='1', status='complete', fingerprint='c'*64, result_json='{}'))
        db.commit()
        create_annotation(db, note)
        db.commit()
        for run_id in ('latest', 'missing'):
            with pytest.raises(InferenceError):
                resolve_input(db, 'c1', run_id, 'n1', 'matb-debrief-v1')
        with pytest.raises(InferenceError):
            resolve_input(db, 'c1', 'run1', 'missing', 'matb-debrief-v1')
        result = resolve_input(db, 'c1', 'run1', 'n1', 'matb-debrief-v1')
        assert result.evidence_run_id == 'run1'
        assert db.get(InferenceAnnotation, 'n1').content_json == note.model_dump_json()
        db.add(EvidenceRun(id='run2', capture_id='c1', version='2', status='complete', fingerprint='d'*64, result_json='{}'))
        db.commit()
        assert resolve_input(db, 'c1', 'run1', 'n1', 'matb-debrief-v1') == result
        artifact.content = b'altered'
        db.add(artifact)
        db.commit()
        with pytest.raises(InferenceError):
            resolve_input(db, 'c1', 'run1', 'n1', 'matb-debrief-v1')
