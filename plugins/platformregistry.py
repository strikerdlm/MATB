"""Platform profile registry helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Iterable, Mapping, MutableMapping, Optional, Tuple


SensorTuple = Tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlatformDefinition:
    """Immutable snapshot describing a UAV platform profile."""

    identifier: str
    display_name: str
    endurance_hours: float
    payload_capacity_kg: float
    bandwidth_limit_mbps: float
    launch_method: str
    recovery_method: str
    sensors: SensorTuple
    notes: str = ''

    def to_payload(self) -> Dict[str, str | float]:
        """Expose a serialisable representation."""
        return {
            'identifier': self.identifier,
            'display_name': self.display_name,
            'endurance_hours': round(self.endurance_hours, 3),
            'payload_capacity_kg': round(self.payload_capacity_kg, 3),
            'bandwidth_limit_mbps': round(self.bandwidth_limit_mbps, 3),
            'launch_method': self.launch_method,
            'recovery_method': self.recovery_method,
            'sensors': '|'.join(self.sensors),
            'notes': self.notes,
        }


def _default_profiles() -> Dict[str, PlatformDefinition]:
    return {
        'scaneagle': PlatformDefinition(
            identifier='ScanEagle',
            display_name='ScanEagle Group-2',
            endurance_hours=24.0,
            payload_capacity_kg=3.4,
            bandwidth_limit_mbps=18.0,
            launch_method='Catapult',
            recovery_method='SkyHook',
            sensors=('EO zoom', 'IR turret', 'Multi-imager'),
            notes='Boeing Insitu ScanEagle ISR platform',
        ),
        'nighteagle': PlatformDefinition(
            identifier='NightEagle',
            display_name='NightEagle IR',
            endurance_hours=18.0,
            payload_capacity_kg=3.4,
            bandwidth_limit_mbps=22.0,
            launch_method='Catapult',
            recovery_method='SkyHook',
            sensors=('EO zoom', 'IR wide',),
            notes='Night-optimized ScanEagle variant',
        ),
        'vtol45': PlatformDefinition(
            identifier='VTOL-45',
            display_name='VTOL Tactical 45',
            endurance_hours=0.75,
            payload_capacity_kg=2.5,
            bandwidth_limit_mbps=12.0,
            launch_method='Vertical take-off',
            recovery_method='Vertical landing',
            sensors=('EO', 'IR'),
            notes='Generic VTOL platform (45 min endurance)',
        ),
        'generic': PlatformDefinition(
            identifier='Generic-UAS',
            display_name='Generic UAS',
            endurance_hours=2.5,
            payload_capacity_kg=2.0,
            bandwidth_limit_mbps=8.0,
            launch_method='Runway',
            recovery_method='Runway',
            sensors=('EO',),
            notes='Default fallback profile',
        ),
    }


class PlatformRegistry:
    """Stores platform definitions and assignments."""

    def __init__(self, profiles: Optional[Mapping[str, PlatformDefinition]] = None) -> None:
        self._profiles: Dict[str, PlatformDefinition] = dict(
            (self._normalise(key), value)
            for key, value in (profiles.items() if profiles else _default_profiles().items())
        )
        self._assignments: MutableMapping[str, PlatformDefinition] = {}

    def available_profiles(self) -> Mapping[str, PlatformDefinition]:
        return dict(self._profiles)

    def get(self, name: str) -> Optional[PlatformDefinition]:
        return self._profiles.get(self._normalise(name))

    def register(self, name: str, definition: PlatformDefinition) -> PlatformDefinition:
        self._profiles[self._normalise(name)] = definition
        return definition

    def assign(
        self,
        asset_id: str,
        definition: PlatformDefinition,
    ) -> PlatformDefinition:
        self._assignments[asset_id] = definition
        return definition

    def get_assignment(self, asset_id: str) -> Optional[PlatformDefinition]:
        return self._assignments.get(asset_id)

    @staticmethod
    def apply_overrides(
        definition: PlatformDefinition,
        overrides: Mapping[str, str],
    ) -> PlatformDefinition:
        payload: Dict[str, object] = {}
        for key, value in overrides.items():
            key_lower = key.lower()
            if key_lower in {'endurance', 'endurance_hours'}:
                payload['endurance_hours'] = max(0.0, float(value))
            elif key_lower in {'payload', 'payload_capacity', 'payload_capacity_kg'}:
                payload['payload_capacity_kg'] = max(0.0, float(value))
            elif key_lower in {'bandwidth', 'bandwidth_limit', 'bandwidth_limit_mbps'}:
                payload['bandwidth_limit_mbps'] = max(0.0, float(value))
            elif key_lower in {'launch', 'launch_method'}:
                payload['launch_method'] = value
            elif key_lower in {'recovery', 'recovery_method'}:
                payload['recovery_method'] = value
            elif key_lower in {'sensors', 'sensor'}:
                payload['sensors'] = tuple(part.strip() for part in value.split('|') if part.strip())
            elif key_lower in {'notes', 'note'}:
                payload['notes'] = value
        return replace(definition, **payload) if payload else definition

    @staticmethod
    def _normalise(value: str) -> str:
        return value.strip().lower()


def format_assignment(asset_id: str, definition: PlatformDefinition) -> str:
    payload = definition.to_payload()
    payload_str = ','.join(f'{key}={value}' for key, value in payload.items())
    return f'{asset_id}|{payload_str}'

