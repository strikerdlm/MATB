"""Offline Spanish briefing for direct native launches, before the task clock runs."""

import hashlib
from pathlib import Path

from pyglet.media import Player, get_audio_driver, load
from pyglet.window import key as winkey

from core.constants import COLORS
from core.logger import get_logger
from core.modaldialog import ModalDialog


class ParticipantBriefing(ModalDialog):
    def __init__(self, win):
        self.player = None
        super().__init__(
            win,
            [
                "Preste mucha atención a las instrucciones y a las llamadas durante toda la prueba.",
                "Pulse A para escuchar las instrucciones completas en español. Pulse R para repetirlas.",
                "Escuche el mensaje completo y responda solo a su indicativo: "
                "flechas para radio y frecuencia; Enter para confirmar.",
                "Controles habituales: F1–F6 en SYSMON, teclado numérico 1–8 en RESMAN y joystick para TRACK. "
                "Siga la asignación de su sesión.",
                "Compruebe el bloqueo numérico, las teclas de función y el sonido durante la práctica. "
                "Avise si algo no funciona.",
                "Durante la prueba: P para pausa; Espacio para reanudar con indicación del investigador.",
                "La narración utiliza una voz generada por IA. Al terminar, pulse Espacio para comenzar.",
            ],
            title="Instrucciones MATB-FAC",
            continue_key="SPACE",
            exit_key="Q",
        )
        self._instructions_html = self.html_label.text

    def play_instructions(self):
        path = Path(__file__).resolve().parents[2] / "webui/frontend/public/audio/instructions/openmatb-es.wav"
        try:
            driver = get_audio_driver()
            if driver is None or type(driver).__name__ == "SilentDriver":
                raise RuntimeError("No audible output device is available")
            self.stop_audio()
            self.player = Player()
            self.player.queue(load(str(path), streaming=False))
            self.player.play()
            self.continue_key = "SPACE"
            self.html_label.text = self._instructions_html
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            get_logger().log_manual_entry(
                f"Spanish offline instructions playback requested; sha256={digest}",
                key="briefing",
            )
        except Exception as exc:
            self.stop_audio()
            get_logger().log_manual_entry(f"Briefing playback failed: {type(exc).__name__}", key="briefing")
            # Keep the participant outside the timed task and show recovery text.
            color = "#%02x%02x%02x" % COLORS["TEXT"][:3]
            self.html_label.text = (
                f'<font color="{color}">No se pudo reproducir el audio. '
                "Avise al investigador y compruebe el dispositivo de salida y el volumen. "
                "Pulse A para reintentar o Q para salir.</font>"
            )
            self.continue_key = None

    def stop_audio(self):
        if self.player is not None:
            try:
                self.player.pause()
            finally:
                self.player.delete()
                self.player = None

    def on_key_release(self, symbol, modifiers):
        keystr = winkey.symbol_string(symbol)
        if keystr in {"A", "R"}:
            self.play_instructions()
            return
        if keystr == "SPACE" and self.player is not None and self.player.playing and self.player.source is not None:
            return
        super().on_key_release(symbol, modifiers)

    def on_delete(self):
        self.stop_audio()
        super().on_delete()
