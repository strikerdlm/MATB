import time
import pytest
from test_contracts import annotation
from test_projection import source


def reviewed_input():
    from matb_integration.inference.projection import project_review
    from matb_integration.inference.question_packs import load_question_pack
    from matb_integration.inference.contracts import InferenceInputV1
    data = project_review(source(), annotation(), load_question_pack('matb-debrief-v1')).model_dump()
    return InferenceInputV1(**(data | {'redaction_status': 'reviewed'}))


def approval(value):
    return dict(provider_id='jev_ai_pro', purpose='retrospective_annotation',
        payload_hash=value.payload_hash, approved_by='synthetic-reviewer',
        approved_at_ns=str(time.time_ns()-1000000), expires_at_ns=str(time.time_ns()+10**10),
        revoked=False, redaction_reviewed=True, protocol_authorization='synthetic-protocol',
        data_processing_authorization='synthetic-only')


@pytest.mark.parametrize('change', [dict(revoked=True), dict(provider_id='other'),
    dict(payload_hash='a'*64), dict(protocol_authorization=''), dict(expires_at_ns='1'),
    dict(redaction_reviewed=False), dict(purpose='prediction')])
def test_current_exact_authorization_required(change):
    from matb_integration.inference.privacy import validate_egress, EgressError
    value = reviewed_input()
    with pytest.raises(EgressError):
        validate_egress(value, approval(value) | change, 'jev_ai_pro')


def test_valid_synthetic_authorization_and_input_identity():
    from matb_integration.inference.privacy import validate_egress
    from matb_integration.inference.contracts import InferenceInputV1
    value = reviewed_input()
    validate_egress(value, approval(value), 'jev_ai_pro')
    data = value.model_dump()
    a = InferenceInputV1(**(data | {'quality_snapshot_json': '{"a":1,"b":2}'}))
    b = InferenceInputV1(**(data | {'quality_snapshot_json': '{"b":2,"a":1}'}))
    assert a.input_identity == b.input_identity


@pytest.mark.parametrize('excerpt',['Contact pilot@example.com','Bearer secret-token',
    'JEV_AI_API_KEY=secret','https://example.com/?token=secret','{"rr_intervals":[1000,999]}'])
def test_obvious_sensitive_material_is_rejected_even_after_review(excerpt):
    import json
    from matb_integration.inference.privacy import validate_egress,EgressError
    from matb_integration.inference.contracts import InferenceInputV1,canonical_bytes,sha256
    value=reviewed_input()
    payload=json.loads(value.outbound_bytes);payload['state']['excerpt']=excerpt
    raw=canonical_bytes(payload)
    value=InferenceInputV1(**(value.model_dump()|{'outbound_bytes':raw,'payload_hash':sha256(raw)}))
    with pytest.raises(EgressError):validate_egress(value,approval(value),'jev_ai_pro')
