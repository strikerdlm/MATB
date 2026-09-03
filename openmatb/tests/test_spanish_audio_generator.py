"""Unit tests for the offline Spanish COMM voice-bank generator."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _generator():
    path = ROOT / "scripts" / "generate_spanish_audio.py"
    spec = importlib.util.spec_from_file_location("openmatb_spanish_audio", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generator_uses_pinned_openai_model_and_quality_voices():
    generator = _generator()

    assert generator.MODEL == "gpt-4o-mini-tts-2025-12-15"
    assert generator.VOICES == {"female": "marin", "male": "cedar"}
    assert generator.TOKENS["a"] == "Alfa"
    assert generator.TOKENS["j"] == "Juliett"
    assert generator.TOKENS["point"] == "decimal"
    assert generator.TOKENS["com_1_frequency"] == "Radio COM uno, frecuencia."


def test_dotenv_reader_returns_only_requested_value(tmp_path):
    generator = _generator()
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "# local only\nIGNORED=value\nOPENAI_API_KEY='secret-value'\n",
        encoding="utf-8",
    )

    assert generator._read_env_value(env_file, "OPENAI_API_KEY") == "secret-value"
    assert generator._read_env_value(env_file, "MISSING") is None


def test_manifest_rejects_voice_bank_over_runtime_ceiling():
    generator = _generator()
    assets = []
    for selector in generator.VOICES:
        for token in ("empty", *generator.TOKENS):
            assets.append(
                {
                    "selector": selector,
                    "id": token,
                    "path": f"{selector}/{token}.wav",
                    "duration_ms": 1800.0 if token != "empty" else 50.0,
                }
            )

    with pytest.raises(RuntimeError, match="24-second ceiling"):
        generator.build_manifest(assets, generator.MODEL)


def test_nonempty_asset_rejects_digital_silence(tmp_path):
    generator = _generator()
    path = tmp_path / "p.wav"
    generator.write_silence(path, duration_ms=40)

    with pytest.raises(RuntimeError, match="silent or below the audio floor"):
        generator._asset_entry(
            path,
            "female",
            "marin",
            "p",
            "Papa",
            generator.MODEL,
        )
