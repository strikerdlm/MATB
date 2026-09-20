"""Immutable local contracts; identities and scientific provenance stay local."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator
from matb_integration.contracts._immutability import deep_freeze_json, deep_thaw_json

Identifier = Annotated[str, Field(min_length=1, max_length=200)]
Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Nanoseconds = Annotated[str, Field(pattern=r'^(0|[1-9][0-9]*)$', max_length=30)]
Language = Literal['en', 'es']


def canonical_bytes(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode='json')
    return json.dumps(deep_thaw_json(value), sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def sha256(value: Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical_bytes(value)).hexdigest()


class FrozenContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', strict=True, validate_default=True,
                              allow_inf_nan=False, ser_json_bytes='base64', val_json_bytes='base64')


class ReviewAnnotationV1(FrozenContract):
    schema_version: Literal['1.0'] = '1.0'
    annotation_id: Identifier
    capture_id: Identifier
    source_event_ids: tuple[Identifier, ...] = ()
    language: Language
    author_role: Literal['participant', 'observer', 'researcher']
    source_kind: Literal['synthetic', 'participant_debrief_excerpt', 'observer_note', 'report_excerpt']
    original_text: str = Field(min_length=1, max_length=8000)
    created_at_ns: Nanoseconds
    observation_start_ns: Nanoseconds | None = None
    observation_end_ns: Nanoseconds | None = None
    supersedes_annotation_id: Identifier | None = None

    @model_validator(mode='after')
    def interval(self):
        if not self.original_text.strip():
            raise ValueError('empty annotation')
        if (self.observation_start_ns is None) != (self.observation_end_ns is None):
            raise ValueError('observation interval requires both endpoints')
        if self.observation_start_ns is not None and int(self.observation_start_ns) > int(self.observation_end_ns):
            raise ValueError('invalid observation interval')
        if len(set(self.source_event_ids)) != len(self.source_event_ids):
            raise ValueError('duplicate source events')
        return self


class QuestionPackV1(FrozenContract):
    schema_version: Literal['1.0'] = '1.0'
    pack_id: Literal['matb-debrief-v1']
    version: Literal['1.0.0']
    questions: Mapping[str, Any]

    @field_validator('questions')
    @classmethod
    def validate_questions(cls, value):
        expected = {'reported_task_tradeoff': 'noul', 'automation_belief': 'choice',
                    'reported_instruction_difficulty': 'noul'}
        if set(value) != set(expected):
            raise ValueError('question IDs do not match frozen pack')
        for name, question in value.items():
            if set(question) - {'type', 'instructions', 'criteria'} or question.get('type') != expected[name]:
                raise ValueError('invalid question primitive or fields')
            if not isinstance(question.get('instructions'), str) or not question['instructions'].strip():
                raise ValueError('instructions required')
            criteria = question.get('criteria')
            if criteria is not None and (not isinstance(criteria, Mapping) or not criteria or
                    any(not isinstance(x, str) or not x.strip() for x in criteria.values())):
                raise ValueError('criteria must be nonempty textual descriptions')
            if name == 'automation_belief' and (criteria is None or set(criteria) != {
                    'expected_active', 'expected_inactive', 'conflicting', 'not_stated'}):
                raise ValueError('incorrect choice options')
            if expected[name] == 'noul' and criteria is not None and set(criteria) != {'true', 'false'}:
                raise ValueError('incorrect noul criteria')
        canonical_bytes(value)
        return deep_freeze_json(deep_thaw_json(value))

    @field_serializer('questions')
    def serialize_questions(self, value):
        return deep_thaw_json(value)


class InferenceInputV1(FrozenContract):
    schema_version: Literal['1.0'] = '1.0'
    capture_id: Identifier
    evidence_run_id: Identifier
    reconciliation_fingerprint: Digest
    source_artifact_hashes: tuple[Digest, ...]
    annotation_id: Identifier
    annotation_hash: Digest
    source_event_ids: tuple[Identifier, ...]
    source_kind: Literal['synthetic', 'participant_debrief_excerpt', 'observer_note', 'report_excerpt']
    language: Language
    mode: Literal['retrospective_annotation'] = 'retrospective_annotation'
    projection_version: Literal['1.0.0'] = '1.0.0'
    provider_id: Literal['jev_ai_pro'] = 'jev_ai_pro'
    requested_model: Literal['jev-1.13.0'] = 'jev-1.13.0'
    question_pack_id: Literal['matb-debrief-v1'] = 'matb-debrief-v1'
    question_pack_hash: Digest
    outbound_bytes: bytes = Field(max_length=32768)
    payload_hash: Digest
    quality_snapshot_json: str
    exclusions_json: str
    redaction_status: Literal['review_required', 'reviewed'] = 'review_required'

    @field_validator('quality_snapshot_json', 'exclusions_json')
    @classmethod
    def canonical_json_field(cls, value):
        return canonical_bytes(json.loads(value)).decode('utf-8')

    @model_validator(mode='after')
    def identity_check(self):
        if self.evidence_run_id == 'latest':
            raise ValueError('explicit immutable run required')
        if sha256(self.outbound_bytes) != self.payload_hash:
            raise ValueError('payload hash mismatch')
        for encoded in (self.quality_snapshot_json, self.exclusions_json):
            canonical_bytes(json.loads(encoded))
        return self

    @property
    def input_identity(self) -> str:
        return sha256({key: value for key, value in self.model_dump(mode='json').items()
                       if key not in {'redaction_status'}})


class ProviderAttempt(FrozenContract):
    attempt_id: Identifier
    outcome: Literal['received', 'not_sent', 'outcome_unknown', 'cancelled', 'oversize']
    status: int | None = Field(default=None, ge=100, le=599)
    raw_response: bytes = Field(default=b'', max_length=65536)
    headers: Mapping[str, str] = Field(default_factory=dict)
    started_at_ns: Nanoseconds
    finished_at_ns: Nanoseconds
    error_code: Literal['disabled', 'missing_key', 'timeout', 'transport', 'cancelled', 'oversize'] | None = None

    @field_validator('headers')
    @classmethod
    def allowed_headers(cls, value):
        allowed = {'retry-after', 'x-jev-billing', 'x-jev-credits-charged', 'x-jev-credits-remaining'}
        if set(value) - allowed or any(len(x) > 200 for x in value.values()):
            raise ValueError('unsupported response headers')
        return deep_freeze_json(value)

    @field_serializer('headers')
    def serialize_headers(self, value):
        return deep_thaw_json(value)


class InferenceResultV1(FrozenContract):
    schema_version: Literal['1.0'] = '1.0'
    attempt_id: Identifier
    requested_model: Identifier
    resolved_model: Identifier | None = None
    answers_json: str = '{}'
    raw_response_hash: Digest
    started_at_ns: Nanoseconds
    finished_at_ns: Nanoseconds
    latency_ms: float = Field(ge=0)
    usage_json: str = '{}'
    outcome: Literal['valid', 'invalid', 'blocked', 'outcome_unknown', 'throttled', 'unavailable', 'late']
    error_code: Identifier | None = None
    earliest_retry_ns: Nanoseconds | None = None
    confirmatory_eligible: Literal[False] = False
    review_disposition: Literal['unreviewed'] = 'unreviewed'

    @field_validator('answers_json', 'usage_json')
    @classmethod
    def valid_json(cls, value):
        return canonical_bytes(json.loads(value)).decode('utf-8')
