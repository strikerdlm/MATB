"""Unit tests for the platform registry helper."""

from __future__ import annotations

from plugins.platformregistry import PlatformDefinition, PlatformRegistry


def test_registry_assigns_and_overrides_profiles() -> None:
    registry = PlatformRegistry()
    definition = registry.get('scaneagle')
    assert definition is not None

    overrides = {'endurance_hours': '12', 'payload_capacity_kg': '4.5', 'sensors': 'EO|IR'}
    overridden = PlatformRegistry.apply_overrides(definition, overrides)
    assert overridden.endurance_hours == 12
    assert overridden.payload_capacity_kg == 4.5
    assert overridden.sensors == ('EO', 'IR')

    registry.assign('UAV1', overridden)
    stored = registry.get_assignment('UAV1')
    assert stored == overridden


def test_registry_registers_custom_profile() -> None:
    registry = PlatformRegistry()
    custom = PlatformDefinition(
        identifier='LongRunner',
        display_name='Long Runner',
        endurance_hours=30.0,
        payload_capacity_kg=5.0,
        bandwidth_limit_mbps=25.0,
        launch_method='Runway',
        recovery_method='Runway',
        sensors=('EO', 'SAR'),
    )
    registry.register('longrunner', custom)
    fetched = registry.get('LongRunner')
    assert fetched is not None
    assert fetched.identifier == 'LongRunner'

