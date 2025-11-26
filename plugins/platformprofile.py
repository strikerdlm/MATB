"""Platform profile management plugin."""

from __future__ import annotations

from typing import Dict, Optional

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin
from plugins.platformprofile_data import (
    build_profile,
    canonical_platform_id,
    parse_override_block,
    list_supported_platforms,
)


class Platformprofile(AbstractPlugin):
    """Tracks UAV platform assignments and propagates capabilities to other plugins."""

    def __init__(self, label: str = '', taskplacement: str = 'bottommid', taskupdatetime: int = 750) -> None:
        super().__init__(label or _('Platform Profiles'), taskplacement, taskupdatetime)
        self.parameters['taskfeedback']['overdue'].update({
            'active': True,
            'color': C['ORANGE'],
            'delayms': 0,
            'blinkdurationms': 500,
        })
        self._profiles: Dict[str, Dict[str, object]] = {}
        self._widget: Optional[Simpletext] = None

    # Lifecycle ----------------------------------------------------------
    def start(self) -> None:
        self._profiles = {}
        super().start()

    def create_widgets(self) -> None:
        super().create_widgets()
        header = _('UAV | Platform | Endurance | Payload | Link | Launch/Recovery')
        self.add_widget(
            'header',
            Simpletext,
            container=self.task_container,
            text=header,
            font_size=F['SMALL'],
            y=0.9,
            color=C['WHITE'],
            bold=True,
        )
        self._widget = self.add_widget(
            'summary',
            Simpletext,
            container=self.task_container,
            text=self._empty_summary_text(),
            font_size=F['SMALL'],
            y=0.65,
            wrap_width=0.97,
            color=C['WHITE'],
        )

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        if self._widget is not None:
            self._widget.set_text(self._build_summary_text())
        self._update_overdue_state()
        return True

    # Scenario commands --------------------------------------------------
    def set(self, payload: str) -> None:
        """Assign a platform: ``platformprofile;set;uav1,scaneagle,endurance=20h|sensors=EO/IR``."""
        parts = [part.strip() for part in payload.split(',', 2) if part.strip()]
        if len(parts) < 2:
            return
        uav_label = self._canonical_uav(parts[0])
        platform_id = canonical_platform_id(parts[1])
        overrides = parse_override_block(parts[2]) if len(parts) == 3 else {}
        profile = build_profile(platform_id, overrides or None)
        profile['uav'] = uav_label
        profile['overrides'] = tuple(sorted(overrides.keys()))
        self._profiles[uav_label] = profile
        self.log_performance('platform_profile_set', self._format_log_payload(uav_label, profile))
        for key, value in overrides.items():
            self.log_performance('platform_profile_override', f'{uav_label}:{key}={value}')
        self._push_endurance_update(uav_label, profile)
        self._push_payload_update(profile)

    def clear(self, payload: str) -> None:
        """Clear a platform assignment: ``platformprofile;clear;uav1``."""
        key = self._canonical_uav(payload)
        if key in self._profiles:
            del self._profiles[key]
            self.log_performance('platform_profile_clear', key)

    def catalog(self, _payload: str = '') -> None:
        """Log the supported platform identifiers (diagnostic aid)."""
        platforms = ','.join(list_supported_platforms())
        self.log_performance('platform_catalog', platforms)

    # Helpers -------------------------------------------------------------
    def _canonical_uav(self, label: str) -> str:
        return label.strip().upper()

    def _empty_summary_text(self) -> str:
        return _('Awaiting platform assignments…')

    def _build_summary_text(self) -> str:
        if not self._profiles:
            return self._empty_summary_text()
        lines = []
        for uav in sorted(self._profiles.keys()):
            profile = self._profiles[uav]
            line = self._format_summary_line(uav, profile)
            lines.append(line)
        return '\n'.join(lines)

    def _format_summary_line(self, uav: str, profile: Dict[str, object]) -> str:
        name = profile.get('name', 'N/A')
        endurance = profile.get('endurance_hours', 0)
        payload = profile.get('payload_capacity_kg', 0.0)
        datalink = profile.get('datalink_mbps', 0.0)
        launch = profile.get('launch_method', 'n/a')
        recovery = profile.get('recovery_method', 'n/a')
        sensors = profile.get('sensors', ())
        sensor_str = f" | Sensors: {', '.join(sensors)}" if sensors else ''
        notes = profile.get('notes') or ''
        notes_str = f" | {notes}" if notes else ''
        return (
            f"{uav} | {name} | {endurance}h | {payload:.1f} kg | "
            f"{datalink:.0f} Mbps | {launch}/{recovery}{sensor_str}{notes_str}"
        )

    def _format_log_payload(self, uav: str, profile: Dict[str, object]) -> str:
        return (
            f"{uav}:{profile.get('id')}:{int(profile.get('endurance_sec', 0))}:"
            f"{profile.get('payload_capacity_kg')}"
        )

    def _get_plugin(self, alias: str) -> Optional[AbstractPlugin]:
        if self.scheduler is None:
            return None
        return self.scheduler.plugins.get(alias)

    def _push_endurance_update(self, uav: str, profile: Dict[str, object]) -> None:
        mission = self._get_plugin('missiondirector')
        if mission is None:
            return
        duration = int(profile.get('endurance_sec', 0))
        warn = int(profile.get('warning_buffer_sec', max(600, duration // 10 or 600)))
        try:
            mission.endurance(f'{uav},{duration},{warn}')
            self.log_performance('platform_endurance_push', f'{uav}:{duration}:{warn}')
        except Exception:  # pragma: no cover - defensive integration
            pass

    def _push_payload_update(self, profile: Dict[str, object]) -> None:
        payload_mgr = self._get_plugin('payloadmanager')
        if payload_mgr is None or not hasattr(payload_mgr, 'apply_platform_profile'):
            return
        try:
            payload_mgr.apply_platform_profile(profile.get('name', 'platform'), profile)
            self.log_performance(
                'platform_payload_push',
                f"{profile.get('name')}:{profile.get('datalink_mbps', 0)}",
            )
        except Exception:  # pragma: no cover - defensive integration
            pass

    def _update_overdue_state(self) -> None:
        overdue = self.parameters['taskfeedback']['overdue']
        overdue['active'] = True
        overdue['_is_visible'] = len(self._profiles) == 0

