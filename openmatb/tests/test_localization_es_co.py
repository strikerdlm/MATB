"""Regression tests for the Colombian Spanish OpenMATB localization."""

from __future__ import annotations

import configparser
import gettext
import hashlib
import importlib.util
import json
import string
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "locales"
CATALOG_DIR = LOCALES / "es_CO" / "LC_MESSAGES"
SOUNDS = ROOT / "includes" / "sounds" / "spanish"


def _catalog_tools():
    path = LOCALES / "build_catalog.py"
    spec = importlib.util.spec_from_file_location("openmatb_catalog_tools", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_es_co_is_the_configured_default_locale():
    config = configparser.ConfigParser()
    config.read(ROOT / "config.ini", encoding="utf-8")
    assert config["Openmatb"]["language"] == "es_CO"


def test_compiled_catalog_loads_aviation_terms_and_placeholders():
    translation = gettext.translation("openmatb", LOCALES, languages=["es_CO"])
    assert translation.gettext("System monitoring") == "Vigilancia de sistemas"
    assert translation.gettext("Tracking") == "Seguimiento"
    assert translation.gettext("Communications") == "Comunicaciones"
    assert translation.gettext("Resources management") == "Gestión de recursos"
    assert translation.gettext("Callsign \t\t %s") % "ABC123" == (
        "Distintivo de llamada \t\t ABC123"
    )


def test_spanish_catalog_covers_every_gettext_literal():
    tools = _catalog_tools()
    messages = tools.extract_messages(ROOT)
    entries = tools.parse_po(CATALOG_DIR / "openmatb.po")
    assert tools.validate_catalog(messages, entries) == []


def test_participant_instructions_are_spanish_and_define_task_abbreviations():
    instruction_dir = ROOT / "includes" / "instructions" / "default"
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in instruction_dir.glob("*.txt")
    )
    for abbreviation in ("SYSMON", "TRACK", "COMM", "RESMAN"):
        assert abbreviation in combined
    assert "Présentation des tâches" not in combined
    assert "distintivo de llamada" in combined
    assert (
        "voces de estas instrucciones son generadas por inteligencia artificial"
        in combined
    )


def test_spanish_questionnaires_use_openmatb_four_field_format():
    # The installer also copies SAGAT probe banks, which have their own format.
    # Check the actual MATB-FAC scales in both the runtime and install source.
    for questionnaire_dir in (
        ROOT / "includes" / "questionnaires",
        ROOT.parent / "matb_integration" / "questionnaires",
    ):
        for name in ("isa_es.txt", "nasatlx_es.txt", "bedford_es.txt"):
            path = questionnaire_dir / name
            rows = [
                line
                for line in path.read_text(encoding="utf-8").splitlines()
                if line and not line.startswith("#")
            ]
            assert rows, f"No questionnaire rows in {path}"
            assert all(len(row.split(";")) == 4 for row in rows), str(path)


def test_spanish_comm_audio_manifest_and_pcm_format():
    expected = set(string.digits + string.ascii_lowercase)
    expected.update({"radio", "point", "frequency", "nav_1", "nav_2", "com_1", "com_2", "empty"})
    expected.update(
        {
            "nav_1_frequency",
            "nav_2_frequency",
            "com_1_frequency",
            "com_2_frequency",
        }
    )

    manifest = json.loads((SOUNDS / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["language"] == "es-CO"
    assert manifest["generator"]["provider"] == "OpenAI"
    assert manifest["generator"]["endpoint"] == "/v1/audio/speech"
    assert manifest["generator"]["model"].startswith("gpt-4o-mini-tts-")
    assert manifest["voices"]["female"]["voice"] == "marin"
    assert manifest["voices"]["male"]["voice"] == "cedar"
    assert "inteligencia artificial" in manifest["ai_voice_disclosure"]
    assert manifest["qualified_max_prompt_duration_s"] <= 24.0
    assets = {asset["path"]: asset for asset in manifest["assets"]}

    for gender in ("female", "male"):
        directory = SOUNDS / gender
        actual = {path.stem for path in directory.glob("*.wav")}
        assert actual == expected
        for path in directory.glob("*.wav"):
            relative = path.relative_to(SOUNDS).as_posix()
            assert relative in assets
            assert hashlib.sha256(path.read_bytes()).hexdigest() == assets[relative]["sha256"]
            if path.stem == "empty":
                assert assets[relative]["peak_amplitude"] == 0
            else:
                assert assets[relative]["peak_amplitude"] >= 200
            with wave.open(str(path), "rb") as wav_file:
                assert wav_file.getnchannels() == 1
                assert wav_file.getsampwidth() == 2
                assert wav_file.getframerate() == 22050
                assert wav_file.getnframes() > 0

    assert set(assets) == {
        f"{gender}/{token}.wav"
        for gender in ("female", "male")
        for token in expected
    }


def test_spanish_voice_options_preserve_internal_scenario_values():
    source = (ROOT / "scenario_generator_ui.py").read_text(encoding="utf-8")
    assert '"options": ["spanish", "french", "english"]' in source
    assert '"default": "spanish"' in source
    scenario = (ROOT / "includes" / "scenarios" / "basic.txt").read_text(encoding="utf-8")
    assert ";communications;voiceidiom;spanish" in scenario
    assert ";genericscales;filename;nasatlx_es.txt" in scenario
