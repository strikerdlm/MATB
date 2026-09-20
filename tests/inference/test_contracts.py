import base64
import pytest
from pydantic import ValidationError


def annotation(**changes):
    from matb_integration.inference.contracts import ReviewAnnotationV1
    values = dict(annotation_id='note-1', capture_id='capture-1', source_event_ids=('event-1',),
                  language='en', author_role='participant', original_text='I expected tracking on.',
                  created_at_ns='9007199254740993', source_kind='synthetic')
    return ReviewAnnotationV1(**(values | changes))


@pytest.mark.parametrize('changes', [dict(extra=True), dict(language='fr'),
    dict(original_text=''), dict(created_at_ns=9007199254740993)])
def test_annotation_rejects_invalid_source(changes):
    with pytest.raises(ValidationError):
        annotation(**changes)


def test_annotation_is_immutable_and_preserves_exact_time():
    note = annotation()
    assert note.model_dump()['created_at_ns'] == '9007199254740993'
    with pytest.raises(ValidationError):
        note.original_text = 'changed'


def test_canonical_identity_order_and_material_changes():
    from matb_integration.inference.contracts import canonical_bytes, sha256
    assert canonical_bytes({'b': 2, 'a': 1}) == b'{"a":1,"b":2}'
    assert sha256({'b': 2, 'a': 1}) == sha256({'a': 1, 'b': 2})
    assert sha256({'text': 'a'}) != sha256({'text': 'b'})
    for value in (float('nan'), float('inf')):
        with pytest.raises(ValueError):
            canonical_bytes({'value': value})


def test_attempt_serializes_bytes_explicitly():
    from matb_integration.inference.contracts import ProviderAttempt
    attempt = ProviderAttempt(attempt_id='a', outcome='received', status=200,
        raw_response=b'{}', started_at_ns='1', finished_at_ns='2')
    assert attempt.model_dump(mode='json')['raw_response'] == base64.b64encode(b'{}').decode()
    assert ProviderAttempt.model_validate_json(attempt.model_dump_json()) == attempt


def test_default_headers_cannot_bypass_allowlist():
    from matb_integration.inference.contracts import ProviderAttempt
    attempt = ProviderAttempt(attempt_id='a', outcome='received', status=200,
        started_at_ns='1', finished_at_ns='2')
    with pytest.raises(TypeError):
        attempt.headers['authorization'] = 'secret'


@pytest.mark.parametrize('encoded', ['not json', '{"value":NaN}', '{"value":Infinity}'])
def test_result_rejects_invalid_json(encoded):
    from matb_integration.inference.contracts import InferenceResultV1
    with pytest.raises(ValidationError):
        InferenceResultV1(attempt_id='a', requested_model='jev-1.13.0',
            raw_response_hash='a'*64, started_at_ns='1', finished_at_ns='2',
            latency_ms=0.0, outcome='invalid', answers_json=encoded)
