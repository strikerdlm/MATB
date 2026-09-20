import pytest
from test_contracts import annotation


def source():
    return dict(capture_id='capture-1', evidence_run_id='run-1',
        reconciliation_fingerprint='a'*64, source_artifact_hashes=['b'*64],
        event_ids=['event-1'], quality_snapshot={'eligible': False},
        exclusions=[{'task': 'track', 'reason': 'unqualified'}])


def test_projection_keeps_identifiers_local_and_exclusions_visible():
    from matb_integration.inference.projection import project_review
    from matb_integration.inference.question_packs import load_question_pack
    result = project_review(source(), annotation(), load_question_pack('matb-debrief-v1'))
    assert b'capture-1' not in result.outbound_bytes
    assert b'event-1' not in result.outbound_bytes
    assert 'unqualified' in result.exclusions_json
    assert result.redaction_status == 'review_required'


@pytest.mark.parametrize('change', [dict(capture_id='other'), dict(evidence_run_id='latest'),
    dict(evidence_run_id=''), dict(event_ids=[]), dict(reconciliation_fingerprint=None)])
def test_projection_requires_frozen_consistent_source(change):
    from matb_integration.inference.projection import project_review
    from matb_integration.inference.question_packs import load_question_pack
    with pytest.raises(ValueError):
        project_review(source() | change, annotation(), load_question_pack('matb-debrief-v1'))
