"""Reusable helpers for platform profiles."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

DEFAULT_PROFILE: Dict[str, Any] = {
    'id': 'custom',
    'name': 'Custom Platform',
    'endurance_sec': 7200,
    'warning_buffer_sec': 600,
    'payload_capacity_kg': 3.0,
    'datalink_mbps': 40.0,
    'launch_method': 'runway',
    'recovery_method': 'runway',
    'sensors': ('EO', 'IR'),
    'notes': '',
}

PLATFORM_LIBRARY: Dict[str, Dict[str, Any]] = {
    'scaneagle': {
        'name': 'ScanEagle',
        'endurance_sec': 24 * 3600,
        'warning_buffer_sec': 900,
        'payload_capacity_kg': 3.4,
        'datalink_mbps': 45.0,
        'launch_method': 'Catapult',
        'recovery_method': 'Skyhook',
        'sensors': ('EO Zoom', 'IR', 'Multi-Imager'),
        'notes': 'Group 2 UAS with modular payload bay.',
    },
    'nighteagle': {
        'name': 'NightEagle',
        'endurance_sec': 18 * 3600,
        'warning_buffer_sec': 600,
        'payload_capacity_kg': 3.2,
        'datalink_mbps': 40.0,
        'launch_method': 'Catapult',
        'recovery_method': 'Skyhook',
        'sensors': ('IR', 'Low-Light EO'),
        'notes': 'Night-optimised ScanEagle variant with dedicated IR payload.',
    },
}

_KEY_ALIASES: Dict[str, str] = {
    'endurance': 'endurance_sec',
    'endurance_seconds': 'endurance_sec',
    'endurance_sec': 'endurance_sec',
    'endurance_s': 'endurance_sec',
    'warning': 'warning_buffer_sec',
    'warning_buffer': 'warning_buffer_sec',
    'payload': 'payload_capacity_kg',
    'payloadkg': 'payload_capacity_kg',
    'payload_capacity': 'payload_capacity_kg',
    'payload_capacity_kg': 'payload_capacity_kg',
    'datalink': 'datalink_mbps',
    'bandwidth': 'datalink_mbps',
    'link': 'datalink_mbps',
    'capacity': 'datalink_mbps',
    'launch': 'launch_method',
    'recovery': 'recovery_method',
    'notes': 'notes',
    'sensors': 'sensors',
}


def canonical_platform_id(value: str) -> str:
    """Normalise platform identifiers."""
    return value.strip().lower()


def list_supported_platforms() -> Tuple[str, ...]:
    """Expose known platform identifiers."""
    return tuple(sorted(PLATFORM_LIBRARY.keys()))


def build_profile(platform_id: str, overrides: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Return a concrete profile dictionary with overrides applied."""
    canonical = canonical_platform_id(platform_id)
    template = deepcopy(PLATFORM_LIBRARY.get(canonical, DEFAULT_PROFILE))
    template['id'] = canonical
    template.setdefault('name', platform_id.title())
    template.setdefault('warning_buffer_sec', max(600, int(template['endurance_sec'] * 0.1)))
    template.setdefault('sensors', tuple(template.get('sensors', ())))
    merged = dict(template)

    if overrides:
        for key, value in overrides.items():
            if key not in template:
                merged[key] = value
                continue
            if key == 'sensors':
                merged[key] = _coerce_sensors(value)
            elif key in ('endurance_sec', 'warning_buffer_sec'):
                merged[key] = max(0, int(value))
            elif key in ('payload_capacity_kg', 'datalink_mbps'):
                merged[key] = max(0.0, float(value))
            else:
                merged[key] = value

    merged['sensors'] = _coerce_sensors(merged.get('sensors', ()))
    merged['endurance_hours'] = round(merged['endurance_sec'] / 3600, 2)
    merged['warning_buffer_sec'] = max(60, int(merged.get('warning_buffer_sec', 600)))
    return merged


def parse_override_block(block: str) -> Dict[str, Any]:
    """Parse ``key=value`` entries separated by ``|``."""
    overrides: Dict[str, Any] = {}
    if not block:
        return overrides
    entries = [token.strip() for token in block.split('|') if token.strip()]
    for entry in entries:
        if '=' not in entry:
            continue
        key, raw_value = entry.split('=', 1)
        canonical = _canonical_override_key(key.strip())
        if canonical is None:
            continue
        converted = _convert_override_value(canonical, raw_value.strip())
        if converted is not None:
            overrides[canonical] = converted
    return overrides


def _canonical_override_key(key: str) -> Optional[str]:
    lowered = key.lower()
    if lowered in _KEY_ALIASES:
        return _KEY_ALIASES[lowered]
    return None


def _convert_override_value(key: str, value: str) -> Any:
    if key == 'endurance_sec' or key == 'warning_buffer_sec':
        return _parse_duration_seconds(value)
    if key in ('payload_capacity_kg', 'datalink_mbps'):
        try:
            return float(value)
        except ValueError:
            return None
    if key == 'sensors':
        return _coerce_sensors(value)
    return value


def _parse_duration_seconds(value: str) -> int:
    token = value.strip().lower()
    multiplier = 1.0
    if token.endswith('h'):
        multiplier = 3600.0
        token = token[:-1]
    elif token.endswith('m'):
        multiplier = 60.0
        token = token[:-1]
    elif token.endswith('s'):
        multiplier = 1.0
        token = token[:-1]
    try:
        numeric = float(token)
    except ValueError:
        return 0
    return max(0, int(numeric * multiplier))


def _coerce_sensors(value: Any) -> Tuple[str, ...]:
    if isinstance(value, str):
        tokens = [token.strip() for token in value.replace('/', ',').split(',')]
    elif isinstance(value, Sequence):
        tokens = [str(token).strip() for token in value]
    else:
        tokens = []
    return tuple(token for token in tokens if token)

