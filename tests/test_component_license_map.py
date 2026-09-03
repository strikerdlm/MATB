from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_component_license_map_is_deterministic_and_resolves_openmatb() -> None:
    payload = json.loads((ROOT / "LICENSES" / "component-map.json").read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1.0"
    assert payload["default_license_expression"] == "MIT"
    components = payload["components"]
    assert len({component["component_id"] for component in components}) == len(components)
    assert [component["path_prefix"] for component in components] == [
        "",
        "matb_integration/physiology/analysis.py",
        "matb_integration/physiology/broadcast.py",
        "openmatb/",
    ]

    for component in components:
        assert (ROOT / component["license_file"]).is_file()

    openmatb = max(
        (component for component in components if "openmatb/core/logger.py".startswith(component["path_prefix"])),
        key=lambda component: len(component["path_prefix"]),
    )
    assert openmatb["license_expression"] == "CECILL-2.1"

    polar = max(
        (
            component
            for component in components
            if "matb_integration/physiology/broadcast.py".startswith(component["path_prefix"])
        ),
        key=lambda component: len(component["path_prefix"]),
    )
    assert polar["license_expression"] == "LicenseRef-Polar-SDK"


def test_public_release_keeps_component_license_evidence() -> None:
    manifest = json.loads((ROOT / "release" / "core-manifest.json").read_text(encoding="utf-8"))

    assert "LICENSES" in manifest["include"]
    assert "THIRD_PARTY_NOTICES.md" in manifest["include"]
    assert "privacy_and_licensing_reviews_pending" in manifest["release_blockers"]
