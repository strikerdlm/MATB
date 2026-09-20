"""Strict validation of intermediary System One responses; no renormalization."""
import json
import math
from datetime import timezone
from email.utils import parsedate_to_datetime
from .contracts import InferenceResultV1, ProviderAttempt, canonical_bytes, sha256


def probability(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('invalid_probability')


def retry_time(value: str | None, finished: str) -> str:
    try:
        if value and value.isdigit():
            return str(int(finished) + int(value)*10**9)
        stamp = parsedate_to_datetime(value).replace(tzinfo=timezone.utc).timestamp()
        return str(max(int(finished), int(stamp*10**9)))
    except (ValueError, TypeError, OverflowError):
        return str(int(finished)+60*10**9)


def validate_response(payload: dict, attempt: ProviderAttempt) -> InferenceResultV1:
    base = dict(attempt_id=attempt.attempt_id, requested_model=payload['model'],
        raw_response_hash=sha256(attempt.raw_response), started_at_ns=attempt.started_at_ns,
        finished_at_ns=attempt.finished_at_ns,
        latency_ms=max(0.0, (int(attempt.finished_at_ns)-int(attempt.started_at_ns))/10**6))
    if attempt.outcome != 'received':
        outcome = 'blocked' if attempt.outcome == 'not_sent' else 'outcome_unknown'
        return InferenceResultV1(**base, outcome=outcome, error_code=attempt.error_code)
    if attempt.status == 429:
        return InferenceResultV1(**base, outcome='throttled', error_code='provider_throttled',
            earliest_retry_ns=retry_time(attempt.headers.get('retry-after'), attempt.finished_at_ns))
    if attempt.status != 200:
        return InferenceResultV1(**base, outcome='unavailable', error_code='provider_http_'+str(attempt.status))
    try:
        response = json.loads(attempt.raw_response)
        canonical_bytes(response)
        if set(response) - {'model', 'answers', 'usage'} or response['model'] != payload['model']:
            raise ValueError('model_or_schema_mismatch')
        answers = response['answers']
        if set(answers) != set(payload['questions']):
            raise ValueError('question_coverage')
        for name, question in payload['questions'].items():
            answer = answers[name]
            if answer['type'] != question['type']:
                raise ValueError('primitive_mismatch')
            if question['type'] == 'noul':
                if set(answer) != {'type', 'noul'}:
                    raise ValueError('noul_schema')
                probability(answer['noul'])
            elif question['type'] == 'choice':
                if set(answer) != {'type', 'choice', 'confidence', 'probabilities'}:
                    raise ValueError('choice_schema')
                distribution = answer['probabilities']
                if set(distribution) != set(question['criteria']) or answer['choice'] not in distribution:
                    raise ValueError('option_mismatch')
                for value in distribution.values():
                    probability(value)
                probability(answer['confidence'])
                if abs(sum(distribution.values())-1.0) > 1e-6:
                    raise ValueError('probability_sum')
                if distribution[answer['choice']] < max(distribution.values()):
                    raise ValueError('choice_distribution_mismatch')
            else:
                raise ValueError('unsupported_primitive')
        usage = response.get('usage', {})
        if set(usage) - {'input_tokens', 'output_tokens'} or any(type(v) is not int or v < 0 for v in usage.values()):
            raise ValueError('usage_schema')
        return InferenceResultV1(**base, outcome='valid', resolved_model=response['model'],
            answers_json=canonical_bytes(answers).decode(), usage_json=canonical_bytes(usage).decode())
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return InferenceResultV1(**base, outcome='invalid', error_code='response_schema')
