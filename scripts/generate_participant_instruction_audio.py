"""Generate committed bilingual participant instructions with OpenAI tts-1-hd.

The API credential is loaded only from the process or repository-local ignored
``.env.local`` file. It is never printed, copied into the frontend, or written
to the generated manifest. Runtime playback uses the committed MP3 files and
does not require network access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCAL_ENV_PATH = REPOSITORY_ROOT / ".env.local"
OUTPUT_ROOT = REPOSITORY_ROOT / "webui" / "frontend" / "public" / "audio" / "instructions"
MANIFEST_PATH = OUTPUT_ROOT / "manifest.json"
MODEL = "tts-1-hd"

SCRIPTS = {
    "journey-en": {
        "language": "en",
        "voice": "alloy",
        "text": (
            "Welcome to your MATB-FAC visit. Follow the activities in the order shown. "
            "First, confirm your pseudonymous participant code and today's visit with the researcher. "
            "Second, rate your current sleepiness on the Karolinska Sleepiness Scale. "
            "Third, complete the ten-minute PVT. Fourth, remain seated and still for the Polar H10 baseline. "
            "Fifth, listen to the mission briefing. Sixth, complete practice. Seventh, complete the low, medium, and high mission blocks in the order displayed. "
            "Eighth, answer each workload question when it appears. Ninth, wait for the saved confirmation and tell the researcher before leaving the station."
        ),
    },
    "journey-es": {
        "language": "es-CO",
        "voice": "nova",
        "text": (
            "Bienvenido a su visita MATB-FAC. Siga las actividades en el orden indicado. "
            "Primero, confirme con el investigador su código seudonimizado y la visita de hoy. "
            "Segundo, indique su somnolencia actual en la Escala de Somnolencia de Karolinska. "
            "Tercero, complete la PVT de diez minutos. Cuarto, permanezca sentado y quieto durante la línea basal con Polar H10. "
            "Quinto, escuche las instrucciones de misión. Sexto, complete la práctica. Séptimo, complete los bloques de misión bajo, medio y alto en el orden mostrado. "
            "Octavo, responda cada pregunta de carga cuando aparezca. Noveno, espere la confirmación de guardado y avise al investigador antes de abandonar el puesto."
        ),
    },
    "kss-en": {
        "language": "en",
        "voice": "alloy",
        "text": (
            "Karolinska Sleepiness Scale. Select the number that represents your level of sleepiness during the immediately preceding five minutes. "
            "One: extremely alert. Two: very alert. Three: alert. Four: rather alert. Five: neither alert nor sleepy. "
            "Six: some signs of sleepiness. Seven: sleepy, but no effort to keep awake. Eight: sleepy, but some effort to keep awake. "
            "Nine: very sleepy, great effort to keep awake, fighting sleep. Select one response, then continue to the PVT instructions."
        ),
    },
    "kss-es": {
        "language": "es-CO",
        "voice": "nova",
        "text": (
            "Escala de Somnolencia de Karolinska. Seleccione el número que represente el nivel de somnolencia durante los cinco minutos inmediatamente anteriores. "
            "Uno: extremadamente despierto. Dos: muy despierto. Tres: despierto. Cuatro: más o menos despierto. Cinco: ni despierto, ni somnoliento. "
            "Seis: algunos signos de somnolencia. Siete: somnoliento, pero sin esfuerzo de mantenerse despierto. Ocho: somnoliento, algún esfuerzo para mantenerse despierto. "
            "Nueve: muy somnoliento, gran esfuerzo para mantenerse despierto, luchando contra el sueño. Seleccione una respuesta y continúe a las instrucciones de la PVT."
        ),
    },
    "pvt-en": {
        "language": "en",
        "voice": "alloy",
        "text": (
            "PVT instructions. This test lasts ten minutes. Rest one finger on the space bar, or use the black response area on the screen. "
            "Wait while the screen is blank. A millisecond counter will appear after a variable interval of two to ten seconds. "
            "Respond as soon as the counter appears. Your response time will be shown for one second. Do not anticipate the signal. "
            "If you respond early, the screen will say Too soon. Continue responding until the timer ends. Use the same hand and keep your attention at the center of the screen."
        ),
    },
    "pvt-es": {
        "language": "es-CO",
        "voice": "nova",
        "text": (
            "Instrucciones de la PVT. Esta prueba dura diez minutos. Apoye un dedo sobre la barra espaciadora, o use el área negra de respuesta en la pantalla. "
            "Espere mientras la pantalla esté vacía. Un contador de milisegundos aparecerá después de un intervalo variable de dos a diez segundos. "
            "Responda apenas aparezca el contador. Su tiempo de respuesta se mostrará durante un segundo. No se anticipe a la señal. "
            "Si responde antes, la pantalla dirá Demasiado pronto. Continúe respondiendo hasta que termine el tiempo. Use la misma mano y mantenga la atención en el centro de la pantalla."
        ),
    },
    "polar-en": {
        "language": "en",
        "voice": "alloy",
        "text": (
            "Polar H10 baseline instructions. Allow the researcher to fit the chest sensor and verify the signal. "
            "Sit with your back supported, both feet on the floor, and your hands resting still. Breathe normally. "
            "Avoid speaking and unnecessary movement for five minutes. Tell the researcher if you feel discomfort. "
            "Remain seated until the researcher confirms that the baseline has been saved."
        ),
    },
    "polar-es": {
        "language": "es-CO",
        "voice": "nova",
        "text": (
            "Instrucciones de línea basal con Polar H10. Permita que el investigador coloque el sensor torácico y compruebe la señal. "
            "Siéntese con la espalda apoyada, ambos pies en el suelo y las manos quietas. Respire normalmente. "
            "Evite hablar y hacer movimientos innecesarios durante cinco minutos. Avise al investigador si siente incomodidad. "
            "Permanezca sentado hasta que el investigador confirme que la línea basal fue guardada."
        ),
    },
    "mission-en": {
        "language": "en",
        "voice": "alloy",
        "text": (
            "sUAS mission instructions. The center map shows aircraft, assigned sectors, routes, detected contacts, restricted zones, and real coverage. "
            "Select an aircraft on the map or in the fleet list. The bottom command bar will then show only valid actions. "
            "Use Assign sector to begin a search. Use Set waypoint, then click the intended position on the map. Use Hold when necessary, and Return to base only when instructed or when reserve is low. "
            "Monitor the alert and contact panels. Acknowledge open alerts. For a detected contact, inspect it, classify it, set its priority, and report it in the order offered by the controls. "
            "During a question, stop issuing commands and respond to the prompt. Complete practice first, then each mission block in the order displayed."
        ),
    },
    "mission-es": {
        "language": "es-CO",
        "voice": "nova",
        "text": (
            "Instrucciones de la misión sUAS. El mapa central muestra aeronaves, sectores asignados, rutas, contactos detectados, zonas restringidas y la cobertura real. "
            "Seleccione una aeronave en el mapa o en la lista de flota. La barra inferior mostrará únicamente las acciones válidas. "
            "Use Asignar sector para iniciar la búsqueda. Use Fijar punto de ruta y después haga clic en la posición deseada del mapa. Use Mantener cuando sea necesario, y Regresar a base solamente cuando se le indique o cuando la reserva sea baja. "
            "Vigile los paneles de alertas y contactos. Confirme las alertas abiertas. Para un contacto detectado, inspecciónelo, clasifíquelo, asigne su prioridad y repórtelo en el orden ofrecido por los controles. "
            "Durante una pregunta, deje de emitir comandos y responda. Complete primero la práctica y luego cada bloque de misión en el orden mostrado."
        ),
    },
}


def _read_env_value(path: Path, name: str) -> str | None:
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
    key = os.environ.get("OPENAI_API_KEY") or _read_env_value(LOCAL_ENV_PATH, "OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is unavailable; use the secure key setup flow")
    return key


def validate_mp3(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    if len(data) < 1_000:
        raise RuntimeError(f"audio asset is unexpectedly small: {path.name}")
    if not (data.startswith(b"ID3") or data[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}):
        raise RuntimeError(f"audio asset has no recognized MP3 header: {path.name}")
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def generate(*, overwrite: bool) -> None:
    existing = list(OUTPUT_ROOT.glob("*.mp3"))
    if existing and not overwrite:
        raise RuntimeError("instruction assets already exist; pass --overwrite to regenerate")
    client = OpenAI(api_key=load_api_key())
    OUTPUT_ROOT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="matb-instruction-audio-", dir=OUTPUT_ROOT.parent) as temp_dir:
        build_root = Path(temp_dir)
        assets: list[dict[str, object]] = []
        for asset_id, specification in SCRIPTS.items():
            output = build_root / f"{asset_id}.mp3"
            print(f"Generating {output.name}")
            with client.audio.speech.with_streaming_response.create(
                model=MODEL,
                voice=specification["voice"],
                input=specification["text"],
                response_format="mp3",
            ) as response:
                response.stream_to_file(output)
            evidence = validate_mp3(output)
            assets.append({
                "id": asset_id,
                "path": output.name,
                "language": specification["language"],
                "voice": specification["voice"],
                "text_sha256": hashlib.sha256(specification["text"].encode("utf-8")).hexdigest(),
                **evidence,
            })
        manifest = {
            "schema_version": "1.0",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "provider": "OpenAI",
            "endpoint": "/v1/audio/speech",
            "model": MODEL,
            "runtime_network_required": False,
            "disclosure": "AI-generated instructional voice; not a recording of a human instructor.",
            "assets": assets,
        }
        manifest_path = build_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        for asset in assets:
            shutil.copyfile(build_root / str(asset["path"]), OUTPUT_ROOT / str(asset["path"]))
        shutil.copyfile(manifest_path, MANIFEST_PATH)
    print(f"Generated and validated {len(assets)} offline instruction assets with {MODEL}")


def check() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("model") != MODEL:
        raise RuntimeError("manifest model does not match tts-1-hd")
    expected = {f"{asset_id}.mp3" for asset_id in SCRIPTS}
    actual = {str(asset["path"]) for asset in manifest.get("assets", [])}
    if actual != expected:
        raise RuntimeError("manifest inventory does not match the instruction scripts")
    for asset in manifest["assets"]:
        evidence = validate_mp3(OUTPUT_ROOT / asset["path"])
        if evidence["sha256"] != asset["sha256"] or evidence["bytes"] != asset["bytes"]:
            raise RuntimeError(f"manifest evidence mismatch: {asset['path']}")
    print(f"Validated {len(actual)} offline instruction assets generated with {MODEL}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        generate(overwrite=args.overwrite)


if __name__ == "__main__":
    main()
