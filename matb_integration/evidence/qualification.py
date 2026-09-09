"""Immutable, context-bound qualification evidence; never promotes a metric.

Session reconciliation, external measurement qualification and protocol release
eligibility are distinct. Legacy captures require an explicit reviewer context
attestation because their acquisition manifest did not record the rig.
"""
from __future__ import annotations

import base64
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from matb_integration.qualification.contracts import evaluate_timing_qualification
from .contracts import canonical_bytes

SHA = r"^[a-f0-9]{64}$"


class QualificationContextV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    rig_id: str = Field(min_length=1, max_length=200)
    os: str = Field(min_length=1, max_length=200)
    display: dict = Field(min_length=1)
    input_device: dict = Field(min_length=1)
    audio_path: dict = Field(min_length=1)
    acquisition: dict = Field(min_length=1)
    presentation: dict = Field(min_length=1)
    software_versions: dict[str, str] = Field(min_length=1)
    protocol_id: str = Field(min_length=1, max_length=200)
    protocol_version: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def source_bindings(self):
        if not self.software_versions.get("acquisition_commit") or not self.presentation.get("profile_id"):
            raise ValueError("acquisition_commit and presentation.profile_id are required")
        canonical_bytes(self.model_dump())
        return self


class QualificationAttachmentV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}$")
    sha256: str = Field(pattern=SHA)
    content_base64: str = Field(max_length=12 * 1024 * 1024)


class QualificationSubmissionV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["physical_timing", "human_calibration"]
    context: QualificationContextV1
    reviewer: str = Field(min_length=1, max_length=200)
    assessed_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d\d:\d\d)$")
    assessment: dict
    evidence: list[QualificationAttachmentV1] = Field(min_length=1, max_length=8)


class QualificationBindingV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    record_id: str = Field(pattern=SHA)
    capture_manifest_sha256: str = Field(pattern=SHA)
    context: QualificationContextV1
    context_source: Literal["reviewer_attestation"]
    reviewer: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=4000)


def prepare_qualification(submission: QualificationSubmissionV1) -> tuple[dict, dict[str, bytes]]:
    if sum(len(item.content_base64) for item in submission.evidence) > 12 * 1024 * 1024:
        raise ValueError("qualification encoded evidence capacity exceeded")
    if len(canonical_bytes(submission.assessment)) > 1024 * 1024:
        raise ValueError("qualification assessment capacity exceeded")
    artifacts: dict[str, bytes] = {}
    for item in submission.evidence:
        content = base64.b64decode(item.content_base64, validate=True)
        if not content or item.name in artifacts or sha256(content).hexdigest() != item.sha256:
            raise ValueError("qualification evidence is empty, duplicate or has an incorrect checksum")
        artifacts[item.name] = content
    if sum(map(len, artifacts.values())) > 8 * 1024 * 1024:
        raise ValueError("qualification evidence exceeds 8 MiB")
    context = submission.context.model_dump()
    assessment = submission.assessment
    if submission.kind == "physical_timing":
        rig = assessment.get("rig", {})
        expected = {"rig_id": context["rig_id"], "os": context["os"], "display": context["display"],
                    "audio_device": context["audio_path"], "input_device": context["input_device"]}
        if rig != expected:
            raise ValueError("timing report rig differs from qualification context")
        result = evaluate_timing_qualification(assessment)
    else:
        # A linked reviewed study report is evidence, not an automated claim of
        # human validity. The applicability judgment remains with its reviewer.
        if assessment.get("status") not in {"PASS", "FAIL", "NOT_TESTED"} or not assessment.get("method"):
            raise ValueError("human calibration requires an explicit reviewed result and method")
        result = {**assessment, "evaluation_basis": "reviewed_external_study_report"}
    record = {
        "schema_version": "1.0", "kind": submission.kind, "context": context,
        "context_sha256": sha256(canonical_bytes(context)).hexdigest(),
        "reviewer": submission.reviewer, "assessed_at": submission.assessed_at,
        "assessment": result,
        "evidence": {name: {"sha256": sha256(content).hexdigest(), "size_bytes": len(content)}
                     for name, content in sorted(artifacts.items())},
        "invalidation_conditions": [f"context_changed:{key}" for key in sorted(context)] + ["record_revoked"],
        "claim_boundary": "Linked qualification applies only to the exact declared context; session timing QC and protocol eligibility remain separate.",
    }
    return {"id": sha256(canonical_bytes(record)).hexdigest(), **record}, artifacts
