"""Generate the offline Spanish COMM voice bank with the OpenAI Speech API.

The network and ``OPENAI_API_KEY`` are needed only while maintaining the voice
bank. OpenMATB plays the committed PCM WAV assets without an API dependency.
The script never prints or stores the credential in generated metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import tempfile
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent
OUTPUT_ROOT = ROOT / "includes" / "sounds" / "spanish"
MANIFEST_PATH = OUTPUT_ROOT / "manifest.json"
LOCAL_ENV_PATH = REPOSITORY_ROOT / ".env.local"

# Pin the model so a regenerated bank does not silently move to a new snapshot.
MODEL = "gpt-4o-mini-tts-2025-12-15"
VOICES = {
    # Directory names are legacy OpenMATB selectors. OpenAI does not document
    # these voices as gender classifications.
    "female": "marin",
    "male": "cedar",
}
SPEECH_INSTRUCTIONS = (
    "Speak only the supplied Spanish text in a neutral Colombian accent. "
    "Deliver it as a calm, concise aviation radiotelephony fragment with an "
    "even pace and crisp articulation. Preserve the supplied ICAO spelling-"
    "alphabet word or digit exactly; pronounce NAV as 'nav' and COM as 'com'. "
    "When the supplied text ends with 'frecuencia', stop after that word and "
    "never append a number. "
    "Do not add, omit, translate, repeat, or explain anything. Do not add music, "
    "radio static, emotional acting, or audible breaths. Start immediately and "
    "avoid long leading or trailing pauses."
)
TOKENS = {
    "0": "cero",
    "1": "uno",
    "2": "dos",
    "3": "tres",
    "4": "cuatro",
    "5": "cinco",
    "6": "seis",
    "7": "siete",
    "8": "ocho",
    "9": "nueve",
    "a": "Alfa",
    "b": "Bravo",
    "c": "Charlie",
    "d": "Delta",
    "e": "Echo",
    "f": "Foxtrot",
    "g": "Golf",
    "h": "Hotel",
    "i": "India",
    "j": "Juliett",
    "k": "Kilo",
    "l": "Lima",
    "m": "Mike",
    "n": "November",
    "o": "Oscar",
    "p": "Papa",
    "q": "Quebec",
    "r": "Romeo",
    "s": "Sierra",
    "t": "Tango",
    "u": "Uniform",
    "v": "Victor",
    "w": "Whiskey",
    "x": "X-ray",
    "y": "Yankee",
    "z": "Zulu",
    "radio": "radio",
    "point": "decimal",
    "frequency": "frecuencia",
    "nav_1": "NAV uno",
    "nav_2": "NAV dos",
    "com_1": "COM uno",
    "com_2": "COM dos",
    # Contextual chunks reduce joins and improve cadence. The player uses these
    # when present and retains the historical token-bank fallback otherwise.
    "nav_1_frequency": "Radio NAV uno, frecuencia.",
    "nav_2_frequency": "Radio NAV dos, frecuencia.",
    "com_1_frequency": "Radio COM uno, frecuencia.",
    "com_2_frequency": "Radio COM dos, frecuencia.",
}
CONTEXTUAL_TOKENS = (
    "nav_1_frequency",
    "nav_2_frequency",
    "com_1_frequency",
    "com_2_frequency",
)

AUDIO_FORMAT = {
    "channels": 1,
    "sample_width_bytes": 2,
    "frame_rate_hz": 22050,
    "encoding": "PCM signed 16-bit little-endian",
}
AI_DISCLOSURE = (
    "Las instrucciones de voz de COMM son generadas por inteligencia artificial; "
    "no corresponden a la voz de una persona ni a una comunicación ATS real."
)


def _read_env_value(path: Path, name: str) -> str | None:
    """Read one dotenv value without logging any part of the file."""
    if not path.is_file():
        return None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value or None
    return None


def load_api_key() -> str:
    """Load the key from the process or repository-local ignored env file."""
    key = os.environ.get("OPENAI_API_KEY") or _read_env_value(
        LOCAL_ENV_PATH, "OPENAI_API_KEY"
    )
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is unavailable. Use the secure Codex API-key setup "
            "flow; do not paste a key into chat or a command."
        )
    return key


def write_silence(path: Path, duration_ms: int = 50) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = int(AUDIO_FORMAT["frame_rate_hz"])
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(int(AUDIO_FORMAT["channels"]))
        wav_file.setsampwidth(int(AUDIO_FORMAT["sample_width_bytes"]))
        wav_file.setframerate(rate)
        wav_file.writeframes(b"\0\0" * (rate * duration_ms // 1000))


def _normalize_wav(source: Path, output: Path, ffmpeg: str) -> None:
    """Trim long edge silence, normalize level, and enforce PCM format."""
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-af",
            (
                "silenceremove=start_periods=1:start_duration=0.01:"
                "start_threshold=-45dB:stop_periods=-1:stop_duration=0.20:"
                "stop_threshold=-45dB:stop_silence=0.08,"
                "loudnorm=I=-19:TP=-3:LRA=7,apad=pad_dur=0.04"
            ),
            "-ac",
            str(AUDIO_FORMAT["channels"]),
            "-ar",
            str(AUDIO_FORMAT["frame_rate_hz"]),
            "-c:a",
            "pcm_s16le",
            str(output),
        ],
        check=True,
    )


def synthesize_fragment(
    client: Any,
    text: str,
    voice: str,
    output: Path,
    ffmpeg: str,
    model: str,
) -> None:
    """Create one normalized WAV without exposing the API credential."""
    with tempfile.TemporaryDirectory(prefix="openmatb-es-openai-") as temp_dir:
        temp_root = Path(temp_dir)
        raw_path = temp_root / "speech.wav"
        normalized_path = temp_root / "normalized.wav"
        with client.audio.speech.with_streaming_response.create(
            model=model,
            voice=voice,
            input=text,
            instructions=SPEECH_INSTRUCTIONS,
            response_format="wav",
        ) as response:
            response.stream_to_file(raw_path)
        _normalize_wav(raw_path, normalized_path, ffmpeg)
        shutil.copyfile(normalized_path, output)


def inspect_wav(path: Path) -> dict[str, int | float]:
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frame_rate = wav_file.getframerate()
        frames = wav_file.getnframes()
        frame_bytes = wav_file.readframes(frames)
    if channels != AUDIO_FORMAT["channels"]:
        raise RuntimeError(f"{path} is not mono PCM")
    if sample_width != AUDIO_FORMAT["sample_width_bytes"]:
        raise RuntimeError(f"{path} is not 16-bit PCM")
    if frame_rate != AUDIO_FORMAT["frame_rate_hz"]:
        raise RuntimeError(f"{path} does not use the qualified sample rate")
    if frames <= 0:
        raise RuntimeError(f"{path} is empty")
    peak_amplitude = max(
        (abs(sample[0]) for sample in struct.iter_unpack("<h", frame_bytes)),
        default=0,
    )
    return {
        "channels": channels,
        "sample_width_bytes": sample_width,
        "frame_rate_hz": frame_rate,
        "frames": frames,
        "duration_ms": round(frames * 1000 / frame_rate, 1),
        "peak_amplitude": peak_amplitude,
    }


def _asset_entry(
    path: Path,
    selector: str,
    voice: str,
    token: str,
    text: str,
    model: str,
) -> dict[str, Any]:
    audio = inspect_wav(path)
    if token != "empty" and audio["peak_amplitude"] < 200:
        raise RuntimeError(f"{selector}/{token}.wav is silent or below the audio floor")
    if token == "empty" and audio["peak_amplitude"] != 0:
        raise RuntimeError(f"{selector}/empty.wav must contain digital silence")
    return {
        "id": token,
        "path": f"{selector}/{token}.wav",
        "selector": selector,
        "voice": voice,
        "spoken_text": text,
        "model": model,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        **audio,
    }


def _qualified_max_prompt_duration_s(assets: list[dict[str, Any]]) -> float:
    by_selector: dict[str, dict[str, float]] = {}
    for asset in assets:
        by_selector.setdefault(asset["selector"], {})[asset["id"]] = (
            float(asset["duration_ms"]) / 1000
        )
    maxima: list[float] = []
    for durations in by_selector.values():
        longest_letters = sorted(
            (durations[token] for token in "abcdefghijklmnopqrstuvwxyz"),
            reverse=True,
        )[:3]
        longest_digits = sorted(
            (durations[token] for token in "0123456789"), reverse=True
        )[:3]
        callsign = 2 * (sum(longest_letters) + sum(longest_digits))
        frequency = max(
            sum(durations["point" if character == "." else character] for character in f"{tenths / 10:.1f}")
            for tenths in range(1080, 1371)
        )
        contextual = max(
            durations[f"{radio}_frequency"]
            for radio in ("nav_1", "nav_2", "com_1", "com_2")
        )
        # The default callsign has three unique letters and three unique digits;
        # the player repeats it. Exhaustively qualify every default frequency.
        maxima.append(21 * durations["empty"] + callsign + contextual + frequency)
    return round(max(maxima), 3)


def build_manifest(assets: list[dict[str, Any]], model: str) -> dict[str, Any]:
    maximum = _qualified_max_prompt_duration_s(assets)
    if maximum > 24.0:
        raise RuntimeError(
            f"voice bank exceeds the qualified 24-second ceiling ({maximum:.3f}s)"
        )
    return {
        "schema_version": "1.0",
        "language": "es-CO",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": {
            "provider": "OpenAI",
            "endpoint": "/v1/audio/speech",
            "model": model,
            "response_format": "wav",
            "instructions": SPEECH_INSTRUCTIONS,
        },
        "audio_format": AUDIO_FORMAT,
        "voices": {
            selector: {
                "voice": voice,
                "selector_note": (
                    "Legacy OpenMATB compatibility selector; not an OpenAI "
                    "gender classification."
                ),
            }
            for selector, voice in VOICES.items()
        },
        "phraseology": {
            "scope": (
                "OACI-aligned spelling alphabet and frequency pronunciation "
                "inside an experimental MATB prompt; not operational ATS phraseology."
            ),
            "alphabet": "International Radiotelephony Spelling Alphabet",
            "frequency_rule": (
                "Digits individually; decimal separator spoken as 'decimal'."
            ),
            "contextual_prompt_pattern": (
                "[distintivo twice], [NAV/COM selector], frecuencia, [digits]"
            ),
        },
        "ai_voice_disclosure": AI_DISCLOSURE,
        "qualified_max_prompt_duration_s": maximum,
        "assets": sorted(assets, key=lambda item: item["path"]),
    }


def generate(genders: list[str], overwrite: bool, model: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to normalize PCM WAV files")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "The maintenance dependency is missing; install 'openai>=1.66,<3'."
        ) from exc

    if set(genders) != set(VOICES):
        raise RuntimeError(
            "Partial regeneration is disabled so the manifest describes one build."
        )
    existing_wavs = list(OUTPUT_ROOT.glob("*/*.wav"))
    if existing_wavs and not overwrite:
        raise RuntimeError("voice assets already exist; pass --overwrite to replace them")

    client = OpenAI(api_key=load_api_key())
    OUTPUT_ROOT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="spanish-openai-build-", dir=OUTPUT_ROOT.parent
    ) as temp_dir:
        build_root = Path(temp_dir)
        assets: list[dict[str, Any]] = []
        for selector in genders:
            voice = VOICES[selector]
            output_dir = build_root / selector
            output_dir.mkdir(parents=True, exist_ok=True)
            silence = output_dir / "empty.wav"
            write_silence(silence)
            assets.append(
                _asset_entry(
                    silence, selector, voice, "empty", "", model
                )
            )
            for token, spoken_text in TOKENS.items():
                output = output_dir / f"{token}.wav"
                print(f"{selector}: {token} -> {spoken_text}")
                synthesize_fragment(client, spoken_text, voice, output, ffmpeg, model)
                assets.append(
                    _asset_entry(
                        output,
                        selector,
                        voice,
                        token,
                        spoken_text,
                        model,
                    )
                )

        manifest = build_manifest(assets, model)
        staged_manifest = build_root / "manifest.json"
        staged_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        for asset in assets:
            source = build_root / asset["path"]
            destination = OUTPUT_ROOT / asset["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        shutil.copyfile(staged_manifest, MANIFEST_PATH)
    print(
        f"Generated {len(assets)} offline assets; qualified maximum prompt "
        f"{manifest['qualified_max_prompt_duration_s']:.3f}s"
    )


def repair_assets(targets: list[tuple[str, str]], model: str) -> None:
    """Regenerate selected assets and atomically refresh the complete manifest."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to normalize PCM WAV files")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "The maintenance dependency is missing; install 'openai>=1.66,<3'."
        ) from exc

    current = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if current["generator"]["model"] != model:
        raise RuntimeError("partial repair requires the manifest model to match")
    target_set = set(targets)
    if not target_set:
        raise RuntimeError("at least one repair target is required")
    invalid = [
        f"{selector}/{token}"
        for selector, token in target_set
        if selector not in VOICES or token not in TOKENS
    ]
    if invalid:
        raise RuntimeError("invalid repair target: " + ", ".join(sorted(invalid)))
    client = OpenAI(api_key=load_api_key())
    with tempfile.TemporaryDirectory(
        prefix="spanish-openai-repair-", dir=OUTPUT_ROOT.parent
    ) as temp_dir:
        build_root = Path(temp_dir)
        staged_paths: dict[tuple[str, str], Path] = {}
        for selector, token in sorted(target_set):
            voice = VOICES[selector]
            output_dir = build_root / selector
            output_dir.mkdir(parents=True, exist_ok=True)
            spoken_text = TOKENS[token]
            output = output_dir / f"{token}.wav"
            print(f"{selector}: {token} -> {spoken_text}")
            synthesize_fragment(client, spoken_text, voice, output, ffmpeg, model)
            staged_paths[(selector, token)] = output

        assets: list[dict[str, Any]] = []
        for selector, voice in VOICES.items():
            for token in ("empty", *TOKENS):
                path = staged_paths.get(
                    (selector, token), OUTPUT_ROOT / selector / f"{token}.wav"
                )
                assets.append(
                    _asset_entry(
                        path,
                        selector,
                        voice,
                        token,
                        "" if token == "empty" else TOKENS[token],
                        model,
                    )
                )
        manifest = build_manifest(assets, model)
        staged_manifest = build_root / "manifest.json"
        staged_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        for (selector, token), source in staged_paths.items():
            shutil.copyfile(source, OUTPUT_ROOT / selector / f"{token}.wav")
        shutil.copyfile(staged_manifest, MANIFEST_PATH)
    print(
        f"Repaired {len(target_set)} assets; qualified maximum "
        f"prompt {manifest['qualified_max_prompt_duration_s']:.3f}s"
    )


def repair_contextual_assets(model: str) -> None:
    targets = [
        (selector, token)
        for selector in VOICES
        for token in CONTEXTUAL_TOKENS
    ]
    repair_assets(targets, model)


def validate_manifest() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = {
        f"{selector}/{token}.wav"
        for selector in VOICES
        for token in ("empty", *TOKENS)
    }
    actual = {asset["path"] for asset in manifest["assets"]}
    if actual != expected:
        raise RuntimeError("manifest asset inventory does not match the voice bank")
    for asset in manifest["assets"]:
        path = OUTPUT_ROOT / asset["path"]
        if not path.is_file():
            raise RuntimeError(f"missing asset: {asset['path']}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]:
            raise RuntimeError(f"hash mismatch: {asset['path']}")
        audio = inspect_wav(path)
        if audio != {
            key: asset[key]
            for key in (
                "channels",
                "sample_width_bytes",
                "frame_rate_hz",
                "frames",
                "duration_ms",
                "peak_amplitude",
            )
        }:
            raise RuntimeError(f"audio metadata mismatch: {asset['path']}")
        if asset["id"] != "empty" and audio["peak_amplitude"] < 200:
            raise RuntimeError(f"silent or low-level asset: {asset['path']}")
        if asset["id"] == "empty" and audio["peak_amplitude"] != 0:
            raise RuntimeError(f"empty asset is not digital silence: {asset['path']}")
    maximum = _qualified_max_prompt_duration_s(manifest["assets"])
    if maximum != manifest["qualified_max_prompt_duration_s"] or maximum > 24.0:
        raise RuntimeError("manifest prompt-duration qualification is invalid")
    print(f"Validated {len(actual)} assets; qualified maximum prompt {maximum:.3f}s")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--repair-contextual", action="store_true")
    parser.add_argument(
        "--repair-token",
        action="append",
        default=[],
        metavar="SELECTOR/TOKEN",
    )
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args()
    if args.check:
        validate_manifest()
        return
    if args.repair_contextual:
        repair_contextual_assets(args.model)
        return
    if args.repair_token:
        targets: list[tuple[str, str]] = []
        for value in args.repair_token:
            selector, separator, token = value.partition("/")
            if not separator:
                raise RuntimeError(
                    f"invalid repair target {value!r}; use SELECTOR/TOKEN"
                )
            targets.append((selector, token))
        repair_assets(targets, args.model)
        return
    generate(list(VOICES), args.overwrite, args.model)


if __name__ == "__main__":
    main()
