"""Platform profile synchronization plugin."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin
from plugins.platformregistry import PlatformDefinition, PlatformRegistry, format_assignment


class Platformprofile(AbstractPlugin):
    """Keeps UAV platform assignments aligned with the mission plan."""

    def __init__(self, label: str = '', taskplacement: str = 'bottomleft', taskupdatetime: int = 1000) -> None:
        super().__init__(label or _('Platform Profiles'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'defaultprofile': validation.is_string,
        }
        self.parameters.update({'defaultprofile': 'generic'})
        self.registry = PlatformRegistry()
        self.assignments: Dict[str, PlatformDefinition] = {}
        self._widgets: Dict[str, Simpletext] = {}

    def start(self) -> None:
        self.assignments.clear()
        super().start()

    def create_widgets(self) -> None:
        super().create_widgets()
        header = _('UAV | Platform | Endurance | Payload | Launch/Recovery')
        self._widgets['header'] = self.add_widget(
            'header',
            Simpletext,
            container=self.task_container,
            text=header,
            font_size=F['SMALL'],
            y=0.9,
            color=C['WHITE'],
            bold=True,
        )
        for idx in range(4):
            self._widgets[f'row_{idx}'] = self.add_widget(
                f'row_{idx}',
                Simpletext,
                container=self.task_container,
                text='',
                font_size=F['SMALL'],
                y=0.75 - idx * 0.2,
                color=C['WHITE'],
                wrap_width=0.98,
            )

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        for idx, (asset, definition) in enumerate(self.assignments.items()):
            if idx >= 4:
                break
            self._widgets[f'row_{idx}'].set_text(self._format_row(asset, definition))
        return True

    # Scenario commands --------------------------------------------------
    def set(self, payload: str) -> None:
        """Associate a UAV with a predefined platform profile."""
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < 2:
            return
        asset_id = parts[0]
        profile_name = parts[1]
        overrides = self._parse_overrides(parts[2:])
        definition = self.registry.get(profile_name)
        if definition is None:
            default_name = self.parameters['defaultprofile']
            definition = self.registry.get(default_name)
            if definition is None:
                return
        if overrides:
            definition = PlatformRegistry.apply_overrides(definition, overrides)
        self.registry.assign(asset_id, definition)
        self.assignments[asset_id] = definition
        self._log_assignment(asset_id, definition, overrides)
        self.refresh_widgets()

    def define(self, payload: str) -> None:
        """
        Register a new platform profile.

        payload syntax: name,display,endurance_hours,payload_kg,bandwidth_mbps,launch,recovery,sensors
        """
        parts = [part.strip() for part in payload.split(',')]
        if len(parts) < 8:
            return
        try:
            endurance = float(parts[2])
            payload_mass = float(parts[3])
            bandwidth = float(parts[4])
        except ValueError:
            return
        sensors = tuple(sensor.strip() for sensor in parts[7].split('|') if sensor.strip())
        definition = PlatformDefinition(
            identifier=parts[0],
            display_name=parts[1],
            endurance_hours=endurance,
            payload_capacity_kg=payload_mass,
            bandwidth_limit_mbps=bandwidth,
            launch_method=parts[5],
            recovery_method=parts[6],
            sensors=sensors,
        )
        self.registry.register(parts[0], definition)
        self.log_performance('platform_profile_defined', definition.identifier)

    def clear(self, payload: str) -> None:
        """Remove an assignment for a UAV."""
        asset_id = payload.strip()
        if not asset_id:
            return
        if asset_id in self.assignments:
            del self.assignments[asset_id]
            self.log_performance('platform_profile_clear', asset_id)
        self.refresh_widgets()

    # Helpers ------------------------------------------------------------
    def _format_row(self, asset_id: str, definition: PlatformDefinition) -> str:
        endurance = f"{definition.endurance_hours:.1f}h"
        payload = f"{definition.payload_capacity_kg:.1f}kg"
        launch = definition.launch_method
        recovery = definition.recovery_method
        return f"{asset_id} | {definition.identifier} | {endurance} | {payload} | {launch}/{recovery}"

    def _parse_overrides(self, tokens: Tuple[str, ...]) -> Dict[str, str]:
        overrides: Dict[str, str] = {}
        for token in tokens:
            if '=' not in token:
                continue
            key, value = token.split('=', 1)
            key = key.strip()
            value = value.strip()
            if not key or not value:
                continue
            overrides[key] = value
        return overrides

    def _log_assignment(
        self,
        asset_id: str,
        definition: PlatformDefinition,
        overrides: Optional[Dict[str, str]],
    ) -> None:
        payload = format_assignment(asset_id, definition)
        if overrides:
            override_str = ','.join(f'{k}={v}' for k, v in overrides.items())
            payload = f'{payload}|overrides:{override_str}'
        self.log_performance('platform_profile_set', payload)
        self.log_performance('platform_endurance_hours', definition.endurance_hours)
        self.log_performance('platform_payload_capacity', definition.payload_capacity_kg)
        self.log_performance('platform_bandwidth_limit', definition.bandwidth_limit_mbps)

