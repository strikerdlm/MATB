# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass(slots=True)
class PowerProfile:
    """Tracks VTOL power reserves for a single aircraft."""

    name: str
    capacity: float
    remaining: float
    warning: float
    critical: float
    consumption_rate: float


class Vtolpower(AbstractPlugin):
    """Models VTOL-specific energy usage and warnings."""

    def __init__(self, label: str = '', taskplacement: str = 'bottomright', taskupdatetime: int = 250) -> None:
        super().__init__(label or _('VTOL Power Monitor'), taskplacement, taskupdatetime)
        self.profiles: Dict[str, PowerProfile] = {}
        self._widget: Optional[Simpletext] = None

    def create_widgets(self) -> None:
        super().create_widgets()
        if self.task_container is None:
            return
        self._widget = self.add_widget(
            'status',
            Simpletext,
            container=self.task_container,
            text=_('No VTOL power profiles configured.'),
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
    def configure(self, payload: str) -> None:
        """
        payload: uav,capacity,warning,critical[,consumption_rate]
        """
        parts = self._split(payload, 4)
        if parts is None:
            return
        name = parts[0]
        try:
            capacity = float(parts[1])
            warning = float(parts[2])
            critical = float(parts[3])
            rate = float(parts[4]) if len(parts) > 4 else 1.0
        except ValueError:
            return
        profile = PowerProfile(
            name=name,
            capacity=capacity,
            remaining=capacity,
            warning=warning,
            critical=critical,
            consumption_rate=max(0.1, rate),
        )
        self.profiles[name] = profile
        self.log_performance('power_profile_set', f'{name}:{capacity}:{warning}:{critical}:{rate}')
        self._update_widget()

    def draw(self, payload: str) -> None:
        """
        payload: uav,duration_seconds[,multiplier]
        """
        parts = self._split(payload, 2)
        if parts is None:
            return
        profile = self.profiles.get(parts[0])
        if profile is None:
            return
        try:
            duration = float(parts[1])
            multiplier = float(parts[2]) if len(parts) > 2 else 1.0
        except ValueError:
            return
        consumption = duration * profile.consumption_rate * max(0.1, multiplier)
        self._update_remaining(profile.name, -consumption, f'draw:{duration:.1f}:{multiplier:.2f}')

    def recharge(self, payload: str) -> None:
        """
        payload: uav,amount
        """
        parts = self._split(payload, 2)
        if parts is None:
            return
        profile = self.profiles.get(parts[0])
        if profile is None:
            return
        try:
            amount = float(parts[1])
        except ValueError:
            return
        self._update_remaining(profile.name, amount, 'recharge')

    def set(self, payload: str) -> None:
        """
        payload: uav,remaining
        """
        parts = self._split(payload, 2)
        if parts is None:
            return
        profile = self.profiles.get(parts[0])
        if profile is None:
            return
        try:
            value = float(parts[1])
        except ValueError:
            return
        new_remaining = self._clamp(value, 0.0, profile.capacity)
        self.profiles[profile.name] = replace(profile, remaining=new_remaining)
        self._log_levels(profile.name)
        self._update_widget()

    # Helpers ------------------------------------------------------------
    def _update_remaining(self, name: str, delta: float, reason: str) -> None:
        profile = self.profiles.get(name)
        if profile is None:
            return
        new_remaining = self._clamp(profile.remaining + delta, 0.0, profile.capacity)
        self.profiles[name] = replace(profile, remaining=new_remaining)
        self.log_performance('vtol_power_change', f'{name}:{new_remaining:.2f}:{reason}')
        self._log_levels(name)
        self._update_widget()

    def _log_levels(self, name: str) -> None:
        profile = self.profiles.get(name)
        if profile is None:
            return
        remaining = profile.remaining
        if remaining <= profile.critical:
            self.log_performance('power_critical', f'{name}:{remaining:.2f}')
        elif remaining <= profile.warning:
            self.log_performance('power_warning', f'{name}:{remaining:.2f}')

    def _update_widget(self) -> None:
        if self._widget is None:
            return
        if not self.profiles:
            self._widget.set_text(_('No VTOL power profiles configured.'))
            return

        def _fraction(profile: PowerProfile) -> float:
            if profile.capacity <= 0.0:
                return 0.0
            return max(0.0, min(1.0, profile.remaining / profile.capacity))

        # Order profiles by lowest remaining fraction for quick scan of the
        # most constrained aircraft. This is a 2D, text-only representation of
        # the energy state and does not change any underlying power logic.
        lines = [
            _('UAV | Remaining / Capacity | %   | Timeline        | Status'),
        ]
        for profile in sorted(self.profiles.values(), key=_fraction):
            frac = _fraction(profile)
            pct = frac * 100.0
            bar = self.format_progress_bar(frac, length=10)
            if profile.remaining <= profile.critical:
                status = 'CRITICAL'
            elif profile.remaining <= profile.warning:
                status = 'WARNING'
            else:
                status = 'NORMAL'
            lines.append(
                f"{profile.name:>4} | "
                f"{profile.remaining:6.1f}/{profile.capacity:6.1f} | "
                f"{pct:3.0f}% {bar} | {status}"
            )
        self._widget.set_text('\n'.join(lines))

    @staticmethod
    def _split(payload: Optional[str], expected: int) -> Optional[list[str]]:
        if payload is None:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < expected:
            return None
        return parts

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))


