"""Local authorization checks; reviewer approval is not proof of anonymity."""
import json
import time
import re
from .contracts import InferenceInputV1, sha256


class EgressError(ValueError):
    """Typed bounded rejection, containing no narrative or provider error text."""


def validate_egress(input: InferenceInputV1, authorization: dict, provider_id: str) -> None:
    a = authorization
    if provider_id != input.provider_id or a.get('provider_id') != provider_id:
        raise EgressError('provider_mismatch')
    if a.get('purpose') != input.mode or a.get('payload_hash') != input.payload_hash:
        raise EgressError('approval_mismatch')
    if sha256(input.outbound_bytes) != input.payload_hash:
        raise EgressError('payload_integrity')
    if a.get('revoked') is not False:
        raise EgressError('approval_revoked')
    if a.get('redaction_reviewed') is not True or input.redaction_status != 'reviewed':
        raise EgressError('redaction_review_required')
    for key in ('approved_by', 'protocol_authorization', 'data_processing_authorization'):
        if not isinstance(a.get(key), str) or not a[key].strip():
            raise EgressError('authorization_missing')
    try:
        approved, expires = int(a['approved_at_ns']), int(a['expires_at_ns'])
    except (KeyError, TypeError, ValueError):
        raise EgressError('approval_time_invalid') from None
    if not approved <= time.time_ns() < expires:
        raise EgressError('approval_expired')
    payload = json.loads(input.outbound_bytes)
    if set(payload) != {'model', 'state', 'questions'} or set(payload['state']) != {'source_kind', 'language', 'excerpt', 'scope'}:
        raise EgressError('payload_not_allowlisted')
    # Assistance only: no regex can establish narrative anonymity. Keep manual
    # review mandatory and block recognizable secrets, contact details and raw streams.
    if re.search(r'https?://|[\w.+-]+@[\w.-]+\.[a-z]{2,}|bearer\s+|api[_ -]?key|access[_ -]?token|rr_intervals|raw_ecg|ScientificEventV3|device_serial',
                 payload['state']['excerpt'],re.IGNORECASE):
        raise EgressError('sensitive_pattern_review_required')
    # Participant use remains disabled until institutional arrangements are
    # implemented and independently reviewed. An API caller cannot waive this.
    if input.source_kind != 'synthetic':
        raise EgressError('participant_egress_not_enabled')
