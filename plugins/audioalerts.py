# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin

try:
    import pyglet  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pyglet = None  # type: ignore


class Audioalerts(AbstractPlugin):
    """Plays cockpit audio warnings registered via scenario commands."""

    def __init__(self, label: str = '', taskplacement: str = 'invisible', taskupdatetime: int = 500) -> None:
        super().__init__(label or _('Audio Alerts'), taskplacement, taskupdatetime)
        self.parameters.update({
            'defaultvolume': 0.9,
        })
        self.registry: Dict[str, Path] = {}
        self._sources: Dict[str, Any] = {}
        self._players: Dict[str, Any] = {}
        self._widget: Optional[Simpletext] = None

    def start(self) -> None:
        self._stop_all()
        super().start()

    def stop(self) -> None:
        self._stop_all()
        super().stop()

    def create_widgets(self) -> None:
        super().create_widgets()
        if self.task_container is None:
            return
        self._widget = self.add_widget(
            'registry',
            Simpletext,
            container=self.task_container,
            text=_('No audio cues registered.'),
            font_size=F['SMALL'],
            y=0.5,
            wrap_width=0.95,
            color=C['WHITE'],
        )

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        return True

    # Scenario commands -------------------------------------------------
    def register(self, payload: str) -> None:
        parts = self._split(payload, 2)
        if not parts:
            return
        cue = parts[0].strip().lower()
        path = Path(parts[1]).expanduser()
        self.registry[cue] = path
        self._sources.pop(cue, None)
        self.log_performance('audio_register', f'{cue}:{path}')

    def play(self, payload: str) -> None:
        cue = payload.strip().lower()
        if not cue or cue not in self.registry:
            return
        player = self._create_player(cue)
        if player is None:
            return
        player.volume = float(self.parameters['defaultvolume'])
        player.play()
        self._players[cue] = player
        self.log_performance('audio_play', cue)

    def stopcue(self, payload: str) -> None:
        cue = payload.strip().lower()
        player = self._players.pop(cue, None)
        if player is None:
            return
        try:
            player.pause()
            player.delete()
        except Exception:
            pass
        self.log_performance('audio_stop', cue)

    def volume(self, payload: str) -> None:
        try:
            volume = float(payload)
        except (TypeError, ValueError):
            return
        volume = self._clamp(volume, 0.0, 1.0)
        self.parameters['defaultvolume'] = volume
        for player in self._players.values():
            try:
                player.volume = volume
            except Exception:
                continue
        self.log_performance('audio_volume', volume)

    # Helpers -----------------------------------------------------------
    def _split(self, payload: str, expected: int) -> Optional[list[str]]:
        if not payload:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < expected:
            return None
        return parts

    def _create_player(self, cue: str) -> Optional[Any]:
        if pyglet is None:
            self.log_performance('audio_error', f'{cue}:pyglet_missing')
            return None
        source = self._sources.get(cue)
        if source is None:
            path = self.registry.get(cue)
            if path is None:
                return None
            try:
                source = pyglet.media.load(str(path), streaming=False)  # type: ignore[attr-defined]
            except Exception as exc:  # pragma: no cover - depends on local files
                self.log_performance('audio_error', f'{cue}:{exc}')
                return None
            self._sources[cue] = source
        try:
            player = pyglet.media.Player()  # type: ignore[attr-defined]
            player.queue(source)
            return player
        except Exception as exc:  # pragma: no cover
            self.log_performance('audio_error', f'{cue}:{exc}')
            return None

    def _stop_all(self) -> None:
        for cue in list(self._players.keys()):
            self.stopcue(cue)
        self._players.clear()

    def _update_widget(self) -> None:
        if self._widget is None:
            return
        if not self.registry:
            self._widget.set_text(_('No audio cues registered.'))
            return
        lines = [
            _('Cue "{0}" -> {1}').format(cue, path)
            for cue, path in sorted(self.registry.items())
        ]
        self._widget.set_text('\n'.join(lines))

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))


