import pytest
from matb_integration.inference.contracts import ProviderAttempt, canonical_bytes
from test_privacy import reviewed_input
import json


def wire():
    return dict(model='jev-1.13.0', answers={
        'reported_task_tradeoff': {'type':'noul','noul':0.8},
        'reported_instruction_difficulty': {'type':'noul','noul':0.1},
        'automation_belief': {'type':'choice','choice':'expected_active','confidence':0.8,
            'probabilities':dict(expected_active=0.8,expected_inactive=0.1,conflicting=0.0,not_stated=0.1)}},
        usage={'input_tokens':10,'output_tokens':5})


def attempt(raw, status=200):
    return ProviderAttempt(attempt_id='a', outcome='received', status=status,
        raw_response=raw, started_at_ns='100', finished_at_ns='200')


def test_valid_response_preserves_all_probabilities():
    from matb_integration.inference.response_validation import validate_response
    result = validate_response(json.loads(reviewed_input().outbound_bytes), attempt(canonical_bytes(wire())))
    assert result.outcome == 'valid'
    assert json.loads(result.answers_json) == wire()['answers']
    assert result.confirmatory_eligible is False


@pytest.mark.parametrize('mutation', ['model','missing','bool','nan','sum','options','primitive','json'])
def test_invalid_response_is_never_promoted(mutation):
    from matb_integration.inference.response_validation import validate_response
    response = wire()
    if mutation == 'model': response['model'] = 'jev-latest'
    if mutation == 'missing': response['answers'].pop('reported_task_tradeoff')
    if mutation == 'bool': response['answers']['reported_task_tradeoff']['noul'] = True
    if mutation == 'nan': response['answers']['reported_task_tradeoff']['noul'] = float('nan')
    if mutation == 'sum': response['answers']['automation_belief']['probabilities']['expected_active'] = 0.2
    if mutation == 'options': response['answers']['automation_belief']['probabilities']['unknown'] = 0.0
    if mutation == 'primitive': response['answers']['reported_task_tradeoff']['type'] = 'score'
    raw = b'bad json' if mutation == 'json' else json.dumps(response).encode()
    result = validate_response(json.loads(reviewed_input().outbound_bytes), attempt(raw))
    assert result.outcome == 'invalid'
    assert result.answers_json == '{}'


@pytest.mark.parametrize('status, expected', [(401,'unavailable'),(402,'unavailable'),(429,'throttled'),(422,'unavailable')])
def test_provider_failure_is_typed(status, expected):
    from matb_integration.inference.response_validation import validate_response
    result = validate_response(json.loads(reviewed_input().outbound_bytes), attempt(b'{}', status))
    assert result.outcome == expected
