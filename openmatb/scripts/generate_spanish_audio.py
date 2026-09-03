"""Generate the Spanish COMM prompt fragments used by OpenMATB.

This maintenance script requires ``edge-tts`` and ``ffmpeg``. Generated files
are mono PCM WAV so they can be loaded by pyglet without an online dependency.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "includes" / "sounds" / "spanish"
VOICES = {
    "female": "es-CO-SalomeNeural",
    "male": "es-CO-GonzaloNeural",
}
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
}


def write_silence(path: Path, duration_ms: int = 50, rate: int = 22050) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(rate)
        wav_file.writeframes(b"\0\0" * (rate * duration_ms // 1000))


async def synthesize_fragment(text: str, voice: str, output: Path, ffmpeg: str) -> None:
    with tempfile.TemporaryDirectory(prefix="openmatb-es-") as temp_dir:
        mp3_path = Path(temp_dir) / "fragment.mp3"
        await edge_tts.Communicate(text, voice, rate="-8%").save(str(mp3_path))
        subprocess.run(
            [
                ffmpeg,
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(mp3_path),
                "-ac",
                "1",
                "-ar",
                "22050",
                "-c:a",
                "pcm_s16le",
                str(output),
            ],
            check=True,
        )


async def generate(genders: list[str], overwrite: bool) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to generate PCM WAV files")
    for gender in genders:
        voice = VOICES[gender]
        output_dir = OUTPUT_ROOT / gender
        output_dir.mkdir(parents=True, exist_ok=True)
        write_silence(output_dir / "empty.wav")
        for token, spoken_text in TOKENS.items():
            output = output_dir / f"{token}.wav"
            if output.exists() and not overwrite:
                continue
            print(f"{gender}: {token} -> {spoken_text}")
            await synthesize_fragment(spoken_text, voice, output, ffmpeg)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gender", choices=["female", "male", "all"], default="all")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    genders = list(VOICES) if args.gender == "all" else [args.gender]
    asyncio.run(generate(genders, args.overwrite))


if __name__ == "__main__":
    main()
