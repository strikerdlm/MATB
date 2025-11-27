# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Set

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass(slots=True)
class FormationMember:
    """Represents a single vehicle inside the swarm."""

    name: str
    status: str  # AUTO / MANUAL


class Swarmformation(AbstractPlugin):
    """Visualises swarm-level formations and manual override states."""

    def __init__(self, label: str = '', taskplacement: str = 'topmid', taskupdatetime: int = 300) -> None:
        super().__init__(label or _('Swarm Formation'), taskplacement, taskupdatetime)
        self.parameters.setdefault('maxmanualoverrides', 2)
        self.formation_type: str = 'line'
        self.members: List[str] = []
        self.manual_overrides: Set[str] = set()
        self.control_mode: str = 'direct'
        self._widget: Optional[Simpletext] = None

    def create_widgets(self) -> None:
        super().create_widgets()
        if self.task_container is None:
            return
        self._widget = self.add_widget(
            'status',
            Simpletext,
            container=self.task_container,
            text=_('No swarm members defined.'),
            font_size=F['SMALL'],
            color=C['WHITE'],
            wrap_width=0.95,
            x=0.5,
            y=0.5,
        )

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        return True

    # Scenario commands --------------------------------------------------
    def set(self, payload: str) -> None:
        """
        payload: formation_type[,members]
        members field accepts `drone1|drone2|drone3`.
        """
        parts = self._split(payload, 1)
        if parts is None:
            return
        formation = parts[0].lower()
        member_list: List[str] = []
        if len(parts) > 1:
            member_list = [name.strip() for name in parts[1].split('|') if name.strip()]
        if not member_list and not self.members:
            member_list = ['drone1', 'drone2']
        elif not member_list:
            member_list = self.members

        previous_size = len(self.members)
        self.formation_type = formation
        self.members = member_list
        self.manual_overrides.clear()
        if len(self.members) != previous_size:
            self.log_performance('swarm_size_change', f'{previous_size}->{len(self.members)}')
        self._update_widget()
        self.log_performance('swarm_formation_set', f'{formation}:{",".join(member_list)}')

    def override(self, payload: str) -> None:
        """
        payload: member,mode
        mode: manual | auto
        """
        parts = self._split(payload, 2)
        if parts is None:
            return
        member = parts[0]
        mode = parts[1].lower()
        if member not in self.members:
            self.members.append(member)
        if mode == 'manual':
            if member not in self.manual_overrides:
                self.manual_overrides.add(member)
                self.log_performance('swarm_formation_break', member)
        else:
            if member in self.manual_overrides:
                self.manual_overrides.remove(member)
                self.log_performance('swarm_formation_rejoin', member)
        self._check_overrides()
        self._update_widget()

    def memberscmd(self, payload: str) -> None:
        """payload: drone list separated by |"""
        if not payload:
            return
        members = [name.strip() for name in payload.split('|') if name.strip()]
        if not members:
            return
        previous_size = len(self.members)
        self.members = members
        if len(members) != previous_size:
            self.log_performance('swarm_size_change', f'{previous_size}->{len(members)}')
        self.manual_overrides.intersection_update(members)
        self._update_widget()
        self.log_performance('swarm_formation_members', ','.join(members))

    def mode(self, payload: str) -> None:
        """payload: control_mode (direct|indirect|hybrid)."""
        mode = (payload or '').strip().lower()
        if not mode:
            return
        self.control_mode = mode
        self.log_performance('control_mode_switch', mode)
        self._update_widget()

    # Helpers ------------------------------------------------------------
    def _update_widget(self) -> None:
        if self._widget is None:
            return
        if not self.members:
            self._widget.set_text(_('No swarm members defined.'))
            return
        lines = [
            _('Formation: {0} | Mode: {1}').format(
                self.formation_type.upper(),
                self.control_mode.upper(),
            )
        ]
        for member in self.members:
            status = _('MANUAL') if member in self.manual_overrides else _('AUTO')
            lines.append(f'• {member} [{status}]')
        self._widget.set_text('\n'.join(lines))

    def _check_overrides(self) -> None:
        max_overrides = int(self.parameters.get('maxmanualoverrides', 2))
        if len(self.manual_overrides) > max_overrides:
            self.log_performance('swarm_cognitive_overload', len(self.manual_overrides))

    @staticmethod
    def _split(payload: Optional[str], expected: int) -> Optional[list[str]]:
        if payload is None:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < expected:
            return None
        return parts


