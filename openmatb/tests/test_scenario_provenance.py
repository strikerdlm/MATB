from __future__ import annotations

import json
import shutil
from hashlib import sha256
from pathlib import Path

import pytest
from matb_integration.contracts import ExperimentSpecV1, TimelineEventV1
from matb_integration.experiment_compiler import compile_experiment_spec
from matb_integration.openmatb_visual_profiles import load_visual_profile, profile_sha256

import core.scenarioprovenance as provenance_module
from core.scenarioprovenance import (
    ScenarioProvenanceError,
    load_adjacent_scenario_manifest,
)


def _verified_builder_artifact(tmp_path: Path) -> tuple[Path, str, dict[str, object]]:
    repository = Path(__file__).resolve().parents[2]
    source_scenario = repository / "scenarios/military_aviation/low_workload.txt"
    source_manifest = source_scenario.with_suffix(".txt.manifest.json")
    scenario_path = tmp_path / source_scenario.name
    scenario_content = source_scenario.read_bytes()
    scenario_path.write_bytes(scenario_content)
    digest = sha256(scenario_content).hexdigest()
    payload = json.loads(source_manifest.read_text(encoding="utf-8"))
    payload.update(
        {
            "artifact_scope": "session_bound",
            "participant_id": "P01",
            "visit_ordinal": 1,
        }
    )
    payload["generated_by"].update(
        {
            "source_commit": "c" * 40,
            "source_dirty": False,
            "provenance_status": "complete",
        }
    )
    payload["scenario"].update(
        {"filename": scenario_path.name, "sha256": digest}
    )
    return scenario_path, digest, payload


def _verified_compiled_artifact(
    tmp_path: Path,
) -> tuple[Path, str, dict[str, object], ExperimentSpecV1]:
    scenario_path = tmp_path / "compiled.txt"
    source = ExperimentSpecV1.create(
        experiment_id="demo",
        revision=1,
        title="Demo",
        seed=7,
        profile_id="MATB-EXTENDED-2.0",
        duration_ns=60_000_000_000,
        components=("matb-runtime",),
        timeline=(
            TimelineEventV1.create(
                event_key="track-start",
                at_ns=0,
                duration_ns=None,
                component_id="matb-runtime",
                task="track",
                event_type="openmatb.command",
                parameters={"command": "start"},
            ),
            TimelineEventV1.create(
                event_key="track-stop",
                at_ns=59_000_000_000,
                duration_ns=None,
                component_id="matb-runtime",
                task="track",
                event_type="openmatb.command",
                parameters={"command": "stop"},
            ),
        ),
    )
    compiled = compile_experiment_spec(
        source, source_commit="d" * 40, source_dirty=False
    )
    scenario_path.write_text(compiled.scenario_text, encoding="utf-8", newline="\n")
    digest = sha256(compiled.scenario_text.encode()).hexdigest()
    return scenario_path, digest, compiled.manifest, source


def test_adjacent_manifest_is_verified_and_snapshotted_byte_for_byte(tmp_path):
    scenario_path, digest, payload = _verified_builder_artifact(tmp_path)
    manifest_content = json.dumps(payload, sort_keys=True).encode()
    scenario_path.with_suffix(".txt.manifest.json").write_bytes(manifest_content)

    bound = load_adjacent_scenario_manifest(scenario_path, scenario_sha256=digest)

    assert bound.content == manifest_content
    assert bound.evidence["status"] == "verified"
    assert bound.evidence["scenario_manifest_sha256"] == sha256(manifest_content).hexdigest()
    assert bound.evidence["manifest_identity"] == {
        "manifest_schema_version": "3",
        "metrics_schema_version": "2.0",
        "experiment_spec_sha256": None,
        "experiment_seed": 42,
        "scenario_compiler_id": "matb_integration.scenario_builder",
        "scenario_compiler_version": "3.0.0",
        "manifest_source_commit": "c" * 40,
        "manifest_source_dirty": False,
        "manifest_provenance_status": "complete",
    }


def test_missing_adjacent_manifest_is_explicitly_provisional(tmp_path):
    scenario_path = tmp_path / "legacy.txt"
    bound = load_adjacent_scenario_manifest(scenario_path, scenario_sha256="a" * 64)
    assert bound.content is None
    assert bound.evidence["status"] == "provisional_missing_scenario_manifest"


def _visual_parameters(theme: str = "fac_modern") -> dict[str, str]:
    profile = load_visual_profile(
        Path(__file__).resolve().parents[1] / "themes" / f"{theme}.json"
    )
    return {
        "visual_theme": theme,
        "visual_profile_id": profile["profile_id"],
        "visual_profile_version": profile["version"],
        "visual_profile_schema_version": profile["schema_version"],
        "visual_profile_sha256": profile_sha256(profile),
    }


@pytest.mark.parametrize("theme", ["classic", "cockpit", "fac_modern"])
@pytest.mark.parametrize("locale", ["en", "es"])
@pytest.mark.parametrize("block", ["PRACTICE", "LOW", "MEDIUM", "HIGH"])
def test_relocated_console_manifest_loads_with_visual_profile(
    tmp_path, monkeypatch, theme, locale, block,
):
    from aircraft_monitor.research.protocol import WorkloadLevel
    from matb_integration.scenario_builder import (
        _write_scenario_with_manifest,
        build_block_scenario,
    )

    profiles = {
        "PRACTICE": (0.15, 0.9, 100, 90),
        "LOW": (0.2, 0.8, 200, 90),
        "MEDIUM": (0.5, 0.5, 600, 60),
        "HIGH": (0.8, 0.2, 1000, 45),
    }
    settings = dict(zip(
        ("difficulty", "track_target_proportion", "resman_loss_per_min", "isa_probe_interval_sec"),
        profiles[block],
    ))
    options = dict(
        level=WorkloadLevel.LOW if block == "PRACTICE" else WorkloadLevel[block],
        block_duration_sec=180 if block == "PRACTICE" else 900, seed=52,
        isa_questionnaire=f"isa_{locale}.txt", include_nasatlx=False, include_bedford=False,
        workload_settings=settings,
    )
    text = build_block_scenario(**options)
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir()
    scenario_path = generated_dir / f"0_{block}.txt"
    _write_scenario_with_manifest(
        scenario_path, text, **options,
        nasatlx_questionnaire=f"nasatlx_{locale}.txt",
        bedford_questionnaire=f"bedford_{locale}.txt",
        participant_id="P01", block_num=1, visit_ordinal=1, profile_name=block,
        source_commit="c" * 40, source_dirty=False, **_visual_parameters(theme),
    )
    relocated_dir = tmp_path / "Estación ñ con espacios"
    relocated_dir.mkdir()
    for source in generated_dir.iterdir():
        shutil.copyfile(source, relocated_dir / source.name)
    scenario_path = relocated_dir / scenario_path.name
    unrelated_dir = tmp_path / "unrelated working directory"
    unrelated_dir.mkdir()
    monkeypatch.chdir(unrelated_dir)

    bound = load_adjacent_scenario_manifest(
        scenario_path, scenario_sha256=sha256(scenario_path.read_bytes()).hexdigest()
    )

    assert bound.evidence["status"] == "verified"
    assert json.loads(bound.content)["parameters"]["visual_profile_sha256"] == (
        _visual_parameters(theme)["visual_profile_sha256"]
    )


@pytest.mark.parametrize("parameters", [
    {"visual_theme": "cockpit"},
    {**_visual_parameters(), "visual_profile_id": "custom-profile", "visual_profile_version": "2.1.0"},
    {key: value for key, value in _visual_parameters().items() if key != "visual_theme"},
])
def test_legacy_theme_and_custom_profile_metadata_are_supported(tmp_path, parameters):
    scenario_path, digest, payload = _verified_builder_artifact(tmp_path)
    payload["parameters"].update(parameters)
    scenario_path.with_suffix(".txt.manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    bound = load_adjacent_scenario_manifest(scenario_path, scenario_sha256=digest)

    assert bound.evidence["status"] == "verified"


@pytest.mark.parametrize("field,value", [
    ("visual_theme", "unknown"), ("visual_theme", []),
    ("visual_profile_id", "../profile"), ("visual_profile_id", None),
    ("visual_profile_version", "v1"), ("visual_profile_version", 1),
    ("visual_profile_schema_version", "unsupported"),
    ("visual_profile_sha256", "invalid"), ("visual_profile_sha256", None),
    ("unexpected_parameter", True),
])
def test_visual_metadata_does_not_allow_malformed_or_unknown_parameters(tmp_path, field, value):
    scenario_path, digest, payload = _verified_builder_artifact(tmp_path)
    payload["parameters"].update(_visual_parameters())
    payload["parameters"][field] = value
    scenario_path.with_suffix(".txt.manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ScenarioProvenanceError):
        load_adjacent_scenario_manifest(scenario_path, scenario_sha256=digest)


@pytest.mark.parametrize("missing", [
    "visual_profile_id", "visual_profile_version",
    "visual_profile_schema_version", "visual_profile_sha256",
])
def test_partial_visual_profile_identity_fails_closed(tmp_path, missing):
    scenario_path, digest, payload = _verified_builder_artifact(tmp_path)
    payload["parameters"].update(_visual_parameters())
    del payload["parameters"][missing]
    scenario_path.with_suffix(".txt.manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ScenarioProvenanceError, match="visual profile"):
        load_adjacent_scenario_manifest(scenario_path, scenario_sha256=digest)


def test_present_manifest_with_wrong_scenario_hash_fails_closed(tmp_path):
    scenario_path, _, payload = _verified_builder_artifact(tmp_path)
    manifest_path = scenario_path.with_suffix(".txt.manifest.json")
    payload["scenario"]["sha256"] = "b" * 64
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ScenarioProvenanceError, match="does not match"):
        load_adjacent_scenario_manifest(scenario_path, scenario_sha256="a" * 64)


def test_dirty_builder_manifest_is_bound_but_never_upgraded_to_verified(tmp_path):
    scenario_path, digest, payload = _verified_builder_artifact(tmp_path)
    payload["generated_by"]["source_dirty"] = True
    payload["generated_by"]["provenance_status"] = "provisional_dirty_source_tree"
    scenario_path.with_suffix(".txt.manifest.json").write_text(json.dumps(payload))

    bound = load_adjacent_scenario_manifest(scenario_path, scenario_sha256=digest)
    assert bound.evidence["status"] == "verified_provisional_manifest_source"
    assert bound.evidence["manifest_identity"]["manifest_source_dirty"] is True


def test_sagat_binding_is_never_called_fully_verified_without_probe_artifacts(
    tmp_path, monkeypatch
):
    scenario_path, _, payload = _verified_builder_artifact(tmp_path)
    payload["expected"]["sagat_freezes"] = 1
    payload["sagat"] = {
        "manifest_filename": "probes.json",
        "sha256": "e" * 64,
    }
    monkeypatch.setattr(
        provenance_module,
        "_validate_builder_payload",
        lambda *args, **kwargs: None,
    )

    _, status = provenance_module._builder_identity(
        payload,
        scenario_content=scenario_path.read_bytes(),
        scenario_path=scenario_path,
    )

    assert status == "verified_provisional_sagat_artifacts_unverified"


def test_forged_unknown_manifest_type_fails_closed(tmp_path):
    scenario_path = tmp_path / "low.txt"
    content = b"0:00:00;track;start\n"
    scenario_path.write_bytes(content)
    digest = sha256(content).hexdigest()
    scenario_path.with_suffix(".txt.manifest.json").write_text(
        json.dumps({"scenario": {"sha256": digest}, "seed": 42})
    )

    with pytest.raises(ScenarioProvenanceError, match="unknown adjacent"):
        load_adjacent_scenario_manifest(scenario_path, scenario_sha256=digest)


def test_compiled_manifest_requires_hash_verified_canonical_spec(tmp_path):
    scenario_path, scenario_digest, payload, source = _verified_compiled_artifact(
        tmp_path
    )
    record_digest = source.sha256()
    manifest_path = scenario_path.with_suffix(".txt.manifest.json")
    manifest_path.write_text(json.dumps(payload))

    bound = load_adjacent_scenario_manifest(
        scenario_path, scenario_sha256=scenario_digest
    )
    assert bound.evidence["status"] == "verified"
    assert bound.evidence["manifest_identity"]["experiment_spec_sha256"] == record_digest

    payload["spec"]["canonical_record"]["title"] = "Tampered"
    manifest_path.write_text(json.dumps(payload))
    with pytest.raises(ScenarioProvenanceError, match="hash does not verify"):
        load_adjacent_scenario_manifest(scenario_path, scenario_sha256=scenario_digest)


def test_minimal_builder_manifest_cannot_be_upgraded_to_verified(tmp_path):
    scenario_path = tmp_path / "minimal.txt"
    content = b"0:00:00;track;start\n"
    scenario_path.write_bytes(content)
    digest = sha256(content).hexdigest()
    scenario_path.with_suffix(".txt.manifest.json").write_text(json.dumps({
        "manifest_version": 3,
        "metrics_schema_version": "2.0",
        "generated_by": {
            "component": "matb_integration.scenario_builder",
            "version": "3.0.0",
            "source_commit": "c" * 40,
            "source_dirty": False,
            "provenance_status": "complete",
        },
        "artifact_scope": "session_bound",
        "participant_id": "P01",
        "visit_ordinal": 1,
        "workload_label_status": "engineering_preset_pending_human_calibration",
        "seed": 42,
        "scenario": {"filename": scenario_path.name, "sha256": digest},
    }))

    with pytest.raises(ScenarioProvenanceError, match=r"fields|structure|parameters"):
        load_adjacent_scenario_manifest(scenario_path, scenario_sha256=digest)


@pytest.mark.parametrize("with_visual_profile", [False, True])
def test_builder_manifest_rejects_parameter_tampering_even_when_hash_is_updated(
    tmp_path, with_visual_profile,
):
    scenario_path, _, payload = _verified_builder_artifact(tmp_path)
    if with_visual_profile:
        payload["parameters"].update(_visual_parameters())
    tampered = scenario_path.read_text(encoding="utf-8").replace(
        "0:00:00;track;targetproportion;0.8",
        "0:00:00;track;targetproportion;0.2",
    )
    assert tampered != scenario_path.read_text(encoding="utf-8")
    scenario_path.write_text(tampered, encoding="utf-8", newline="\n")
    digest = sha256(tampered.encode()).hexdigest()
    payload["scenario"].update(
        {
            "sha256": digest,
            "line_count": len(tampered.splitlines()),
        }
    )
    scenario_path.with_suffix(".txt.manifest.json").write_text(json.dumps(payload))

    with pytest.raises(ScenarioProvenanceError, match="deterministic builder"):
        load_adjacent_scenario_manifest(scenario_path, scenario_sha256=digest)


def test_nonfinite_manifest_json_fails_closed(tmp_path):
    scenario_path = tmp_path / "nonfinite.txt"
    content = b"0:00:00;track;start\n"
    scenario_path.write_bytes(content)
    digest = sha256(content).hexdigest()
    scenario_path.with_suffix(".txt.manifest.json").write_text(
        '{"manifest_version":3,"seed":NaN,"scenario":{"sha256":"'
        + digest
        + '"}}'
    )

    with pytest.raises(ScenarioProvenanceError, match="valid UTF-8 JSON"):
        load_adjacent_scenario_manifest(scenario_path, scenario_sha256=digest)


def test_compiled_manifest_rejects_empty_timeline_even_with_matching_hash(tmp_path):
    scenario_path, scenario_digest, payload, _ = _verified_compiled_artifact(tmp_path)
    record = payload["spec"]["canonical_record"]
    record["timeline"] = []
    payload["spec"]["sha256"] = sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    scenario_path.with_suffix(".txt.manifest.json").write_text(json.dumps(payload))

    with pytest.raises(ScenarioProvenanceError, match="timeline"):
        load_adjacent_scenario_manifest(scenario_path, scenario_sha256=scenario_digest)
