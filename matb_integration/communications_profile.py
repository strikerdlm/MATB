"""Verified OpenMATB communications-audio timing profile.

The upstream scenario generator's 13-second value is an average and cannot be
used as a lossless presentation boundary.  This profile pins the exact shipped
English/male WAV inventory and derives a conservative upper bound from WAV
headers using the runtime's prompt-concatenation grammar.
"""

from __future__ import annotations

import hashlib
import math
import wave
from pathlib import Path
from typing import Final


COMM_AUDIO_PROFILE_ID: Final[str] = "openmatb-english-male-wav-v1"
COMM_VOICE_IDIOM: Final[str] = "english"
COMM_VOICE_GENDER: Final[str] = "male"
COMM_AUDIO_INVENTORY_SHA256: Final[str] = (
    "d44fa4acd68332f38e14e77868051b88af91dd1d035f389f1a41de06a30f79d9"
)
COMM_PROMPT_UPPER_BOUND_SEC: Final[int] = 24
COMM_MAX_RESPONSE_DELAY_MS: Final[int] = 20_000
COMM_REFRACTORY_SEC: Final[int] = 1
COMM_RESPONSE_AVAILABILITY_SEC: Final[int] = (
    COMM_PROMPT_UPPER_BOUND_SEC + COMM_MAX_RESPONSE_DELAY_MS // 1000
)
COMM_MIN_ONSET_SEPARATION_SEC: Final[int] = (
    COMM_RESPONSE_AVAILABILITY_SEC + COMM_REFRACTORY_SEC
)


class CommunicationsProfileError(RuntimeError):
    """The pinned communications assets are missing or no longer match."""


def _sound_directory(runtime_root: Path | None = None) -> Path:
    selected_root = (
        Path(__file__).resolve().parents[1] / "openmatb"
        if runtime_root is None
        else Path(runtime_root).expanduser().resolve()
    )
    return (
        selected_root
        / "includes"
        / "sounds"
        / COMM_VOICE_IDIOM
        / COMM_VOICE_GENDER
    )


def _inventory_sha256(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _wav_duration_sec(path: Path) -> float:
    with wave.open(str(path), "rb") as source:
        return source.getnframes() / source.getframerate()


def verify_communications_audio_profile(
    *, runtime_root: Path | None = None
) -> dict[str, object]:
    """Verify current assets and return the measured prompt boundary.

    This intentionally performs a fresh byte-level inventory check per call.
    Designer/backend processes are long-lived, so a process-global cache could
    continue qualifying a manifest after a WAV was replaced on disk.
    """
    # Preserve the no-argument helper call for downstream test/customization
    # hooks while ensuring an explicitly selected external runtime is verified
    # against its own audio bytes.
    directory = (
        _sound_directory()
        if runtime_root is None
        else _sound_directory(runtime_root)
    )
    files = sorted(directory.glob("*.wav")) if directory.is_dir() else []
    if not files:
        raise CommunicationsProfileError(
            f"pinned communications audio directory is unavailable: {directory}"
        )
    observed_digest = _inventory_sha256(files)
    if observed_digest != COMM_AUDIO_INVENTORY_SHA256:
        raise CommunicationsProfileError(
            "pinned communications audio inventory changed; requalify its timing "
            f"before compilation (observed {observed_digest})"
        )

    durations = {path.stem: _wav_duration_sec(path) for path in files}
    alphanumeric = tuple("abcdefghijklmnopqrstuvwxyz0123456789")
    frequency_characters = tuple("0123456789") + ("point",)
    radio_names = ("nav_1", "nav_2", "com_1", "com_2")
    required = {*alphanumeric, *frequency_characters, *radio_names, "empty", "radio", "frequency"}
    missing = sorted(required - set(durations))
    if missing:
        raise CommunicationsProfileError(
            "pinned communications audio profile lacks required samples: "
            + ", ".join(missing)
        )

    # Runtime grammar: 20 leading empty samples + the 6-character callsign
    # repeated twice + radio/name/frequency + up to five frequency characters
    # + one trailing empty sample.  Per-class maxima intentionally overbound
    # combinations while remaining tied to measured WAV headers.
    measured_upper_bound = (
        21 * durations["empty"]
        + 12 * max(durations[key] for key in alphanumeric)
        + durations["radio"]
        + max(durations[key] for key in radio_names)
        + durations["frequency"]
        + 5 * max(durations[key] for key in frequency_characters)
    )
    if math.ceil(measured_upper_bound) > COMM_PROMPT_UPPER_BOUND_SEC:
        raise CommunicationsProfileError(
            "measured communications prompt bound exceeds the qualified ceiling: "
            f"{measured_upper_bound:.6f}s > {COMM_PROMPT_UPPER_BOUND_SEC}s"
        )
    return {
        "profile_id": COMM_AUDIO_PROFILE_ID,
        "voice_idiom": COMM_VOICE_IDIOM,
        "voice_gender": COMM_VOICE_GENDER,
        "asset_inventory_sha256": observed_digest,
        "wav_file_count": len(files),
        "measured_conservative_upper_bound_sec": measured_upper_bound,
        "qualified_ceiling_sec": COMM_PROMPT_UPPER_BOUND_SEC,
        "max_response_delay_ms": COMM_MAX_RESPONSE_DELAY_MS,
    }
