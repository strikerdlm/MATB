# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Set

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin

try:  # pragma: no cover - optional dependency
    import pyttsx3  # type: ignore
except Exception:  # pragma: no cover
    pyttsx3 = None  # type: ignore


@dataclass
class DatalinkMessage:
    msg_id: str
    channel: str
    priority: str
    text: str
    created_at: float
    due_seconds: float
    acknowledged: bool = False
    ack_time: Optional[float] = None

    def time_remaining(self, now: float) -> float:
        return max(0.0, self.due_seconds - (now - self.created_at))


class Datalink(AbstractPlugin):
    """Displays datalink messages and supports keyboard acknowledgement."""

    def __init__(self, label: str = '', taskplacement: str = 'bottomright', taskupdatetime: int = 300) -> None:
        super().__init__(label or _('Datalink'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'maxqueue': validation.is_positive_integer,
            'defaultdue': validation.is_positive_integer,
        }

        self.parameters.update({
            'maxqueue': 6,
            'defaultdue': 30,
        })

        self.parameters['taskfeedback']['overdue'].update({
            'active': True,
            'color': C['RED'],
            'delayms': 0,
            'blinkdurationms': 350,
        })

        self.keys.update({'UP', 'DOWN', 'ENTER'})
        self.messages: List[DatalinkMessage] = []
        self.selection_index: int = 0
        self._widget: Optional[Simpletext] = None
        self.voice_enabled: bool = False
        self.voice_priorities: Set[str] = {'PRIO'}
        self._tts_engine: Optional['pyttsx3.Engine'] = None

    # UI -----------------------------------------------------------------
    def create_widgets(self) -> None:
        super().create_widgets()
        self._widget = self.add_widget(
            'messages',
            Simpletext,
            container=self.task_container,
            text=_('No messages'),
            font_size=F['SMALL'],
            y=0.50,
            wrap_width=0.95,
            color=C['WHITE'],
        )

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget_text()
        self._update_overdue()
        return True

    # Keyboard handling --------------------------------------------------
    def do_on_key(self, keystr, state, emulate=False):
        keystr = super().do_on_key(keystr, state, emulate)
        if keystr is None or state != 'release':
            return
        if keystr == 'UP':
            self.selection_index = max(0, self.selection_index - 1)
        elif keystr == 'DOWN':
            if self.messages:
                self.selection_index = min(len(self.messages) - 1, self.selection_index + 1)
        elif keystr == 'ENTER':
            self._ack_selected()

    def _ack_selected(self) -> None:
        if not self.messages:
            return
        index = min(self.selection_index, len(self.messages) - 1)
        message = self.messages[index]
        message.acknowledged = True
        message.ack_time = self.scenario_time
        self.log_performance('datalink_ack', f'{message.msg_id}:{message.channel}:{self._response_time(message):.1f}')
        del self.messages[index]
        if self.messages:
            self.selection_index = min(index, len(self.messages) - 1)
        else:
            self.selection_index = 0

    # Scenario commands --------------------------------------------------
    def message(self, payload: str) -> None:
        """
        payload format: id,channel,priority,text[,due_seconds]
        """
        parts = self._split(payload, 4)
        if not parts:
            return
        try:
            due = float(parts[4]) if len(parts) > 4 else float(self.parameters['defaultdue'])
        except ValueError:
            due = float(self.parameters['defaultdue'])

        message = DatalinkMessage(
            msg_id=parts[0],
            channel=parts[1],
            priority=parts[2],
            text=parts[3],
            created_at=self.scenario_time,
            due_seconds=max(1.0, due),
        )
        self.messages.append(message)
        overflowed = False
        if len(self.messages) > int(self.parameters['maxqueue']):
            overflowed = True
            overflow = self.messages.pop(0)
            self.log_performance('datalink_drop', overflow.msg_id)
        if overflowed:
            if self.selection_index > 0:
                self.selection_index -= 1
            self.selection_index = min(self.selection_index, len(self.messages) - 1) if self.messages else 0
        else:
            self.selection_index = len(self.messages) - 1
        self.log_performance('datalink_receive', f'{message.msg_id}:{message.channel}:{message.priority}')
        self._maybe_voice(message)

    def forceack(self, payload: str) -> None:
        """
        Force acknowledgment via scenario command: payload is message id.
        """
        for index, message in enumerate(self.messages):
            if message.msg_id.lower() == payload.lower():
                message.acknowledged = True
                message.ack_time = self.scenario_time
                self.log_performance('datalink_ack', f'{message.msg_id}:{message.channel}:{self._response_time(message):.1f}')
                del self.messages[index]
                self.selection_index = min(self.selection_index, len(self.messages) - 1) if self.messages else 0
                break

    def clear(self, payload: str) -> None:
        self.messages = []
        self.selection_index = 0
        self.log_performance('datalink_clear', 'all')

    def voice(self, payload: str) -> None:
        """
        payload: bool[,priority_list]
        Example: datalink;voice;True,PRIO|CRIT
        """
        parts = self._split(payload, 1)
        if parts is None:
            return
        flag = parts[0].lower()
        enable = flag in {'true', '1', 'on', 'yes'}
        if not enable:
            self.voice_enabled = False
            self.log_performance('datalink_voice', 'disabled')
            return
        if len(parts) > 1:
            priorities = [p.strip().upper() for p in parts[1].split('|') if p.strip()]
            if priorities:
                self.voice_priorities = set(priorities)
        if pyttsx3 is None:  # pragma: no cover - depends on optional lib
            self.voice_enabled = False
            self.log_performance('datalink_voice_error', 'pyttsx3_missing')
            return
        try:  # pragma: no cover
            if self._tts_engine is None:
                self._tts_engine = pyttsx3.init()
            self.voice_enabled = True
            self.log_performance('datalink_voice', f'enabled:{"/".join(sorted(self.voice_priorities))}')
        except Exception as exc:
            self.voice_enabled = False
            self.log_performance('datalink_voice_error', str(exc))

    # Helpers -------------------------------------------------------------
    def _split(self, payload: str, min_parts: int) -> Optional[list]:
        if not payload:
            return None
        parts = [part.strip() for part in payload.split(',')]
        if len(parts) < min_parts:
            return None
        return parts

    def _update_widget_text(self) -> None:
        if self._widget is None:
            return
        if not self.messages:
            self._widget.set_text(_('No messages'))
            return
        now = self.scenario_time
        lines = []
        for idx, message in enumerate(self.messages):
            selector = '>' if idx == self.selection_index else ' '
            remaining = message.time_remaining(now)
            txt = message.text[:20]
            line = f"{selector}{message.msg_id}: {txt} ({remaining:.0f}s)"
            lines.append(line)
        self._widget.set_text('\n'.join(lines))

    def _update_overdue(self) -> None:
        now = self.scenario_time
        overdue_active = any(message.time_remaining(now) <= 0 for message in self.messages)
        overdue = self.parameters['taskfeedback']['overdue']
        overdue['active'] = True
        overdue['_is_visible'] = overdue_active
        if overdue_active:
            for message in self.messages:
                if message.time_remaining(now) <= 0:
                    self.log_performance('datalink_miss', message.msg_id)

    def _maybe_voice(self, message: DatalinkMessage) -> None:
        if not self.voice_enabled:
            return
        if message.priority.upper() not in self.voice_priorities:
            return
        if self._tts_engine is None:
            if pyttsx3 is None:  # pragma: no cover
                self.voice_enabled = False
                self.log_performance('datalink_voice_error', 'pyttsx3_missing')
                return
            try:  # pragma: no cover
                self._tts_engine = pyttsx3.init()
            except Exception as exc:
                self.voice_enabled = False
                self.log_performance('datalink_voice_error', str(exc))
                return
        utterance = f"{message.channel}. {message.priority}. {message.text}"
        try:  # pragma: no cover
            assert self._tts_engine is not None
            self._tts_engine.say(utterance)
            self._tts_engine.runAndWait()
            self.log_performance('datalink_voice_play', message.msg_id)
        except Exception as exc:
            self.voice_enabled = False
            self.log_performance('datalink_voice_error', str(exc))

    def _response_time(self, message: DatalinkMessage) -> float:
        if message.ack_time is None:
            return 0.0
        return max(0.0, message.ack_time - message.created_at)

