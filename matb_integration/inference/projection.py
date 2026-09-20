"""Pure allowlist projection of a backend-verified immutable evidence run."""
from .contracts import InferenceInputV1, QuestionPackV1, ReviewAnnotationV1, canonical_bytes, sha256


def project_review(source: dict, annotation: ReviewAnnotationV1, pack: QuestionPackV1) -> InferenceInputV1:
    if source['capture_id'] != annotation.capture_id:
        raise ValueError('cross-capture annotation')
    if not set(annotation.source_event_ids).issubset(source['event_ids']):
        raise ValueError('source event unavailable')
    payload = canonical_bytes(dict(model='jev-1.13.0', state=dict(
        source_kind=annotation.source_kind, language=annotation.language,
        excerpt=annotation.original_text,
        scope='Code the explicit report only; do not infer medical or operational fitness.'),
        questions=pack.model_dump()['questions']))
    return InferenceInputV1(capture_id=annotation.capture_id,
        evidence_run_id=source['evidence_run_id'],
        reconciliation_fingerprint=source['reconciliation_fingerprint'],
        source_artifact_hashes=tuple(sorted(source['source_artifact_hashes'])),
        annotation_id=annotation.annotation_id, annotation_hash=sha256(annotation),
        source_event_ids=annotation.source_event_ids, source_kind=annotation.source_kind,
        language=annotation.language, question_pack_hash=sha256(pack),
        outbound_bytes=payload, payload_hash=sha256(payload),
        quality_snapshot_json=canonical_bytes(source['quality_snapshot']).decode(),
        exclusions_json=canonical_bytes(source['exclusions']).decode())
