from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from matb_integration.physiology.contracts import (
    PolarArtifactManifestV1,
    PolarCaptureEventV1,
    PolarCaptureV1,
    PolarDeviceCapabilitiesV1,
)


ROOT = Path(__file__).resolve().parents[2]


def test_committed_polar_schemas_match_runtime_contracts() -> None:
    models = {
        "polar-device-capabilities-v1.schema.json": PolarDeviceCapabilitiesV1,
        "polar-capture-v1.schema.json": PolarCaptureV1,
        "polar-capture-event-v1.schema.json": PolarCaptureEventV1,
        "polar-artifact-manifest-v1.schema.json": PolarArtifactManifestV1,
    }
    for filename, model in models.items():
        committed = json.loads((ROOT / "docs" / "contracts" / filename).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(committed)
        assert committed == model.model_json_schema()
