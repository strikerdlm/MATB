"""Unit tests for military aviation plugins (UAS and HPA modules)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Mock gettext for testing
import builtins
if not hasattr(builtins, '_'):
    builtins._ = lambda x: x  # type: ignore

# Mock pyglet and related modules before importing core
_MOCK_MODULES = [
    'pyglet',
    'pyglet.graphics',
    'pyglet.gl',
    'pyglet.window',
    'pyglet.text',
    'pyglet.image',
    'pyglet.sprite',
    'pyglet.shapes',
    'pyglet.media',
    'pyglet.clock',
    'pyglet.app',
    'pyglet.font',
    'pyglet.resource',
    'pyglet.canvas',
    'pyglet.event',
    'pyglet.input',
    'pyglet.math',
]

for mod_name in _MOCK_MODULES:
    if mod_name not in sys.modules:
        mock_module = MagicMock()
        # Add OrderedGroup for constants.py
        if mod_name == 'pyglet.graphics':
            mock_module.OrderedGroup = MagicMock
        # Add get_display for window.py
        if mod_name == 'pyglet.canvas':
            mock_module.get_display = MagicMock(return_value=MagicMock())
        sys.modules[mod_name] = mock_module


def _load_plugin(name: str) -> ModuleType:
    """Load a plugin module by name."""
    module_path = Path(__file__).resolve().parents[1] / 'plugins' / f'{name}.py'
    spec = importlib.util.spec_from_file_location(f'plugins_{name}', module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load plugin module: {name}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MockLogger:
    """Mock logger for capturing performance records."""

    def __init__(self) -> None:
        self.records: List[Dict[str, Any]] = []
        self.parameters: List[Dict[str, Any]] = []
        self.aois: List[Dict[str, Any]] = []

    def record_parameter(self, alias: str, key: str, value: Any) -> None:
        self.parameters.append({'alias': alias, 'key': key, 'value': value})

    def log_performance(self, alias: str, name: str, value: Any) -> None:
        self.records.append({'alias': alias, 'name': name, 'value': value})

    def record_aoi(self, container: Any, name: str) -> None:
        self.aois.append({'container': container, 'name': name})


class MockContainer:
    """Mock container for widget placement."""

    def reduce_and_translate(self, **kwargs: Any) -> 'MockContainer':
        return MockContainer()


class MockWindow:
    """Mock window for plugin testing."""

    MainWindow: Optional['MockWindow'] = None
    keyboard: Dict[str, bool] = {}
    modal_dialog: Optional[Any] = None

    def get_container(self, placement: str) -> MockContainer:
        return MockContainer()


# Set up mock window
MockWindow.MainWindow = MockWindow()


# =============================================================================
# UAS Module Tests
# =============================================================================

class TestMissionDirector:
    """Tests for the Mission Director plugin."""

    def setup_method(self) -> None:
        self.module = _load_plugin('missiondirector')
        self.Missiondirector = self.module.Missiondirector

    def test_initialisation(self) -> None:
        plugin = self.Missiondirector()
        assert plugin.alias == 'missiondirector'
        assert plugin.parameters['maxuavs'] == 4
        assert 'uavlabels' in plugin.parameters

    def test_uav_state_initialisation(self) -> None:
        plugin = self.Missiondirector()
        plugin.logger = MockLogger()
        plugin._initialise_uavs()
        assert len(plugin.uav_state) == 4
        assert 'UAV1' in plugin.uav_state
        assert plugin.uav_state['UAV1']['mission'] == 'Idle'

    def test_assign_command(self) -> None:
        plugin = self.Missiondirector()
        plugin.logger = MockLogger()
        plugin.scenario_time = 10.0
        plugin._initialise_uavs()
        plugin.assign('UAV1,Surveillance,300')
        assert plugin.uav_state['UAV1']['mission'] == 'Surveillance'
        assert plugin.uav_state['UAV1']['duration'] == 300

    def test_complete_command(self) -> None:
        plugin = self.Missiondirector()
        plugin.logger = MockLogger()
        plugin.scenario_time = 10.0
        plugin._initialise_uavs()
        plugin.assign('UAV1,Surveillance,300')
        plugin.complete('UAV1')
        assert plugin.uav_state['UAV1']['mission'] == 'Idle'

    def test_automation_toggle(self) -> None:
        plugin = self.Missiondirector()
        plugin.logger = MockLogger()
        plugin._initialise_uavs()
        plugin.automation('UAV1,AUTO')
        assert plugin.uav_state['UAV1']['mode'] == 'Auto'
        plugin.automation('UAV1,MANUAL')
        assert plugin.uav_state['UAV1']['mode'] == 'Manual'

    def test_conflict_alert(self) -> None:
        plugin = self.Missiondirector()
        plugin.logger = MockLogger()
        plugin._initialise_uavs()
        plugin.conflict('UAV1,geofence')
        assert 'geofence' in plugin.uav_state['UAV1']['alert']

    def test_endurance_tracking_triggers_alert(self) -> None:
        plugin = self.Missiondirector()
        plugin.logger = MockLogger()
        plugin.scenario_time = 0.0
        plugin._initialise_uavs()
        plugin.endurance('UAV1,30,10')
        plugin.scenario_time = 15.0
        plugin._update_endurance_alerts()
        assert plugin.uav_state['UAV1']['endurance_alerted'] is False
        plugin.scenario_time = 25.0
        plugin._update_endurance_alerts()
        assert plugin.uav_state['UAV1']['endurance_alerted'] is True
        assert any(r['name'] == 'mission_endurance_low' for r in plugin.logger.records)

    def test_handover_logging(self) -> None:
        plugin = self.Missiondirector()
        plugin.logger = MockLogger()
        plugin._initialise_uavs()
        plugin.handover('UAV1,GCS2,start')
        plugin.handover('UAV1,GCS2,complete')
        names = [record['name'] for record in plugin.logger.records]
        assert 'mission_handover_initiate' in names
        assert 'mission_handover_complete' in names


class TestSenseAndAvoid:
    """Tests for the Sense and Avoid plugin."""

    def setup_method(self) -> None:
        self.module = _load_plugin('senseandavoid')
        self.Senseandavoid = self.module.Senseandavoid
        self.Intruder = self.module.Intruder

    def test_intruder_remaining_time(self) -> None:
        intruder = self.Intruder(
            identifier='INT1',
            bearing='090',
            range_nm=2.0,
            altitude_ft=300,
            time_to_conflict=30.0,
            created_at=10.0,
        )
        assert intruder.remaining(20.0) == 20.0
        assert intruder.remaining(40.0) == 0.0

    def test_spawn_intruder(self) -> None:
        plugin = self.Senseandavoid()
        plugin.logger = MockLogger()
        plugin.scenario_time = 10.0
        plugin.spawn('INT1,090,2.5,300,45')
        assert 'INT1' in plugin.intruders
        assert plugin.intruders['INT1'].range_nm == 2.5

    def test_resolve_intruder(self) -> None:
        plugin = self.Senseandavoid()
        plugin.logger = MockLogger()
        plugin.scenario_time = 10.0
        plugin.spawn('INT1,090,2.5,300,45')
        plugin.scenario_time = 20.0
        plugin.resolve('INT1,Turn right 20')
        assert plugin.intruders['INT1'].status == 'RESOLVED'
        assert plugin.intruders['INT1'].action == 'Turn right 20'

    def test_clear_intruder(self) -> None:
        plugin = self.Senseandavoid()
        plugin.logger = MockLogger()
        plugin.scenario_time = 10.0
        plugin.spawn('INT1,090,2.5,300,45')
        plugin.clear('INT1')
        assert 'INT1' not in plugin.intruders

    def test_geofence_breach_and_recover(self) -> None:
        plugin = self.Senseandavoid()
        plugin.logger = MockLogger()
        plugin.geofence('0|0,1|0,1|1,0|1')
        plugin.position('UAV1,0.2,0.2')
        plugin.position('UAV1,1.2,1.2')
        assert any(r['name'] == 'geofence_breach' for r in plugin.logger.records)
        plugin.position('UAV1,0.5,0.5')
        assert any(r['name'] == 'geofence_recover' for r in plugin.logger.records)


class TestPayloadManager:
    """Tests for the Payload Manager plugin."""

    def setup_method(self) -> None:
        self.module = _load_plugin('payloadmanager')
        self.Payloadmanager = self.module.Payloadmanager

    def test_sensor_initialisation(self) -> None:
        plugin = self.Payloadmanager()
        plugin.logger = MockLogger()
        plugin._initialise_sensors()
        assert len(plugin.sensors) == 4
        assert 'CamA' in plugin.sensors

    def test_activate_sensor(self) -> None:
        plugin = self.Payloadmanager()
        plugin.logger = MockLogger()
        plugin._initialise_sensors()
        plugin.activate('CamA,Target-Alpha,15')
        assert plugin.sensors['CamA'].status == 'ACTIVE'
        assert plugin.sensors['CamA'].target == 'Target-Alpha'
        assert plugin.sensors['CamA'].bandwidth == 15.0

    def test_standby_sensor(self) -> None:
        plugin = self.Payloadmanager()
        plugin.logger = MockLogger()
        plugin._initialise_sensors()
        plugin.activate('CamA,Target-Alpha,15')
        plugin.standby('CamA')
        assert plugin.sensors['CamA'].status == 'IDLE'
        assert plugin.sensors['CamA'].bandwidth == 0.0


class TestDatalink:
    """Tests for the Datalink plugin."""

    def setup_method(self) -> None:
        self.module = _load_plugin('datalink')
        self.Datalink = self.module.Datalink

    def test_message_queueing(self) -> None:
        plugin = self.Datalink()
        plugin.logger = MockLogger()
        plugin.scenario_time = 10.0
        plugin.message('MSG1,ATC,PRIO,Hold short RWY 28,25')
        assert len(plugin.messages) == 1
        assert plugin.messages[0].msg_id == 'MSG1'
        assert plugin.messages[0].channel == 'ATC'

    def test_forceack_message(self) -> None:
        plugin = self.Datalink()
        plugin.logger = MockLogger()
        plugin.scenario_time = 10.0
        plugin.message('MSG1,ATC,PRIO,Hold short,25')
        plugin.scenario_time = 15.0
        plugin.forceack('MSG1')
        assert len(plugin.messages) == 0


# =============================================================================
# HPA Module Tests
# =============================================================================

class TestEnergyManager:
    """Tests for the Energy Manager plugin."""

    def setup_method(self) -> None:
        self.module = _load_plugin('energymanager')
        self.Energymanager = self.module.Energymanager

    def test_event_scheduling(self) -> None:
        plugin = self.Energymanager()
        plugin.logger = MockLogger()
        plugin.scenario_time = 10.0
        plugin.events = []
        plugin.event('ENTRY,3.5,30')
        assert len(plugin.events) == 1
        assert plugin.events[0].name == 'ENTRY'
        assert plugin.events[0].target_g == 3.5

    def test_overg_logging(self) -> None:
        plugin = self.Energymanager()
        plugin.logger = MockLogger()
        plugin.overg('7.0')
        assert any(r['name'] == 'energy_overg' for r in plugin.logger.records)

    def test_event_delay_and_start(self) -> None:
        plugin = self.Energymanager()
        plugin.logger = MockLogger()
        plugin.events = []
        plugin.scenario_time = 0.0
        plugin.event('ENTRY,4.0,10,5')
        plugin.paused = False
        plugin.compute_next_plugin_state()
        assert plugin.events[0].started_at is None
        plugin.scenario_time = 6.0
        plugin.compute_next_plugin_state()
        assert plugin.events[0].started_at == 6.0

    def test_g_onset_warning_emitted(self) -> None:
        plugin = self.Energymanager()
        plugin.logger = MockLogger()
        plugin.events = []
        plugin.scenario_time = 0.0
        plugin.event('ENTRY,6.0,12,5')
        plugin.parameters['gwarningthreshold'] = 5.5
        plugin.parameters['gwarningleadtime'] = 4.0
        plugin.paused = False
        plugin.compute_next_plugin_state()
        assert not any(r['name'] == 'g_onset_warning' for r in plugin.logger.records)
        plugin.scenario_time = 2.0
        plugin.compute_next_plugin_state()
        assert any(r['name'] == 'g_onset_warning' for r in plugin.logger.records)

    def test_warning_command_updates_parameters(self) -> None:
        plugin = self.Energymanager()
        plugin.logger = MockLogger()
        plugin.warning('6.5,3')
        assert plugin.parameters['gwarningthreshold'] == 6.5
        assert plugin.parameters['gwarningleadtime'] == 3.0
        assert any(r['name'] == 'energy_warning_config' for r in plugin.logger.records)


class TestThreatboard:
    """Tests for the Threat Board plugin."""

    def setup_method(self) -> None:
        self.module = _load_plugin('threatboard')
        self.Threatboard = self.module.Threatboard

    def test_spawn_threat(self) -> None:
        plugin = self.Threatboard()
        plugin.logger = MockLogger()
        plugin.scenario_time = 10.0
        plugin.threats = []
        plugin.spawn('TH1,035,14,R73,45')
        assert len(plugin.threats) == 1
        assert plugin.threats[0].threat_id == 'TH1'
        assert plugin.threats[0].weapon_hint == 'R73'

    def test_engage_threat(self) -> None:
        plugin = self.Threatboard()
        plugin.logger = MockLogger()
        plugin.scenario_time = 10.0
        plugin.threats = []
        plugin.spawn('TH1,035,14,R73,45')
        plugin.engage('TH1,FOX3')
        assert plugin.threats[0].status == 'ENGAGED'
        assert plugin.threats[0].assigned_weapon == 'FOX3'

    def test_resolve_threat(self) -> None:
        plugin = self.Threatboard()
        plugin.logger = MockLogger()
        plugin.scenario_time = 10.0
        plugin.threats = []
        plugin.spawn('TH1,035,14,R73,45')
        plugin.scenario_time = 20.0
        plugin.resolve('TH1,SPLASH')
        assert plugin.threats[0].status == 'RESOLVED'

    def test_countermeasure_deployment_logs(self) -> None:
        plugin = self.Threatboard()
        plugin.logger = MockLogger()
        plugin.scenario_time = 0.0
        plugin.spawn('TH1,035,14,R73,45')
        plugin.countermeasure('chaff,2')
        names = [record['name'] for record in plugin.logger.records]
        assert 'countermeasure_deploy' in names

    def test_countermeasure_low_alert(self) -> None:
        plugin = self.Threatboard()
        plugin.logger = MockLogger()
        plugin.countermeasure_stock['chaff'] = 1
        plugin.countermeasure_stock['flare'] = 1
        plugin.parameters['chaffcapacity'] = 5
        plugin.parameters['flarecapacity'] = 5
        plugin.threats = []
        plugin._update_overdue()
        assert any(record['name'] == 'countermeasure_low' for record in plugin.logger.records)


class TestWeaponsInventory:
    """Tests for the Weapons Inventory plugin."""

    def setup_method(self) -> None:
        self.module = _load_plugin('weaponsinventory')
        self.Weaponsinventory = self.module.Weaponsinventory

    def test_load_initialises_stock(self) -> None:
        plugin = self.Weaponsinventory()
        plugin.logger = MockLogger()
        plugin.load('AIM9,4')
        assert 'AIM9' in plugin.stocks
        assert plugin.stocks['AIM9'].remaining == 4

    def test_expend_and_empty_logging(self) -> None:
        plugin = self.Weaponsinventory()
        plugin.logger = MockLogger()
        plugin.load('AIM9,2')
        plugin.expend('AIM9,1')
        assert plugin.stocks['AIM9'].remaining == 1
        plugin.expend('AIM9,1')
        assert any(r['name'] == 'weapon_empty' for r in plugin.logger.records)

    def test_reload_adds_rounds(self) -> None:
        plugin = self.Weaponsinventory()
        plugin.logger = MockLogger()
        plugin.load('AIM9,4')
        plugin.expend('AIM9,3')
        plugin.reload('AIM9,2')
        assert plugin.stocks['AIM9'].remaining == 3


class TestAudioAlerts:
    """Tests for the Audio Alerts plugin."""

    def setup_method(self) -> None:
        self.module = _load_plugin('audioalerts')
        self.Audioalerts = self.module.Audioalerts

    def test_register_and_widget_state(self) -> None:
        plugin = self.Audioalerts()
        plugin.logger = MockLogger()
        plugin.register('warning,dummy.wav')
        assert 'warning' in plugin.registry
        assert plugin.registry['warning'].name == 'dummy.wav'

    def test_play_without_pyglet_logs_error(self) -> None:
        plugin = self.Audioalerts()
        plugin.logger = MockLogger()
        plugin.register('warning,dummy.wav')
        self.module.pyglet = None  # type: ignore[attr-defined]
        plugin.play('warning')
        assert any(record['name'] == 'audio_error' for record in plugin.logger.records)
class TestEmergencyStack:
    """Tests for the Emergency Stack plugin."""

    def setup_method(self) -> None:
        self.module = _load_plugin('emergencystack')
        self.Emergencystack = self.module.Emergencystack

    def test_trigger_emergency(self) -> None:
        plugin = self.Emergencystack()
        plugin.logger = MockLogger()
        plugin.scenario_time = 10.0
        plugin.events = []
        plugin.trigger('HYD1,HYD PRESS LOW,Switch pumps|Check breakers')
        assert len(plugin.events) == 1
        assert plugin.events[0].ident == 'HYD1'
        assert len(plugin.events[0].checklist) == 2

    def test_stepdone(self) -> None:
        plugin = self.Emergencystack()
        plugin.logger = MockLogger()
        plugin.scenario_time = 10.0
        plugin.events = []
        plugin.trigger('HYD1,HYD PRESS LOW,Switch pumps|Check breakers')
        plugin.stepdone('HYD1,0')
        assert plugin.events[0].checklist[0].done is True

    def test_resolve_emergency(self) -> None:
        plugin = self.Emergencystack()
        plugin.logger = MockLogger()
        plugin.scenario_time = 10.0
        plugin.events = []
        plugin.trigger('HYD1,HYD PRESS LOW,Switch pumps|Check breakers')
        plugin.scenario_time = 20.0
        plugin.resolve('HYD1')
        assert plugin.events[0].resolved_at == 20.0


# =============================================================================
# Cross-Cutting Tests
# =============================================================================

class TestFailureInjector:
    """Tests for the Failure Injector plugin."""

    def setup_method(self) -> None:
        self.module = _load_plugin('failureinjector')
        self.Failureinjector = self.module.Failureinjector

    def test_schedule_event(self) -> None:
        plugin = self.Failureinjector()
        plugin.logger = MockLogger()
        plugin.scenario_time = 10.0
        plugin.events = []
        plugin.schedule('emergencystack,trigger,HYD1|HYD PRESS LOW,15')
        assert len(plugin.events) == 1
        assert plugin.events[0].target == 'emergencystack'
        assert plugin.events[0].method == 'trigger'
        assert plugin.events[0].fire_at == 25.0


class TestAutomationHooks:
    """Tests for the Automation Hooks plugin."""

    def setup_method(self) -> None:
        self.module = _load_plugin('automationhooks')
        self.Automationhooks = self.module.Automationhooks

    def test_rule_registration(self) -> None:
        plugin = self.Automationhooks()
        plugin.logger = MockLogger()
        plugin.rules = []
        plugin.rule('payloadmanager,payload_overbandwidth,0,AUTO')
        assert len(plugin.rules) == 1
        assert plugin.rules[0] == ('payloadmanager', 'payload_overbandwidth', 0.0, 'AUTO')


class TestCompositeScore:
    """Tests for the Composite Score plugin."""

    def setup_method(self) -> None:
        self.module = _load_plugin('compositescore')
        self.Compositescore = self.module.Compositescore

    def test_weight_setting(self) -> None:
        plugin = self.Compositescore()
        plugin.logger = MockLogger()
        plugin._initialise_metrics()
        plugin.weights('track=0.4,sysmon=0.3,communications=0.2,resman=0.1')
        total = sum(m.weight for m in plugin.task_metrics.values())
        assert abs(total - 1.0) < 0.01

    def test_baseline_collection(self) -> None:
        plugin = self.Compositescore()
        plugin.logger = MockLogger()
        plugin._initialise_metrics()
        plugin.baseline('start')
        assert plugin._baseline_active is True
        plugin.baseline('stop')
        assert plugin._baseline_active is False


class TestAutotraining:
    """Tests for the Automated Training plugin."""

    def setup_method(self) -> None:
        self.module = _load_plugin('autotraining')
        self.Autotraining = self.module.Autotraining

    def test_phase_initialisation(self) -> None:
        plugin = self.Autotraining()
        plugin.logger = MockLogger()
        plugin._initialise_phases()
        assert len(plugin.phases) == 5
        phase_names = [p.name for p in plugin.phases]
        assert 'tracking' in phase_names
        assert 'combined' in phase_names

    def test_phase_advance(self) -> None:
        plugin = self.Autotraining()
        plugin.logger = MockLogger()
        plugin._initialise_phases()
        plugin.current_phase_index = -1
        plugin.scenario_time = 0.0
        plugin._start_next_phase()
        assert plugin.current_phase_index == 0
        assert plugin.phases[0].started_at == 0.0


# =============================================================================
# Scenario Template Tests
# =============================================================================

class TestScenarioTemplates:
    """Tests for scenario template generation."""

    def setup_method(self) -> None:
        self.module_path = Path(__file__).resolve().parents[1] / 'tools' / 'scenario_templates.py'
        spec = importlib.util.spec_from_file_location('scenario_templates', self.module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError('Unable to load scenario_templates module')
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        spec.loader.exec_module(self.module)

    def test_difficulty_profile_scaling(self) -> None:
        profile_easy = self.module.DifficultyProfile.from_level(1)
        profile_hard = self.module.DifficultyProfile.from_level(10)
        assert profile_easy.event_interval > profile_hard.event_interval
        assert profile_easy.deadline_factor > profile_hard.deadline_factor
        assert profile_easy.failure_rate < profile_hard.failure_rate

    def test_uas_scenario_generation(self) -> None:
        profile = self.module.DifficultyProfile.from_level(5)
        events = self.module.generate_uas_bvlos(300, profile)
        assert any('missiondirector;start' in e for e in events)
        assert any('senseandavoid;start' in e for e in events)
        assert any('missiondirector;stop' in e for e in events)

    def test_hpa_scenario_generation(self) -> None:
        profile = self.module.DifficultyProfile.from_level(5)
        events = self.module.generate_hpa_overlay(180, profile)
        assert any('energymanager;start' in e for e in events)
        assert any('threatboard;start' in e for e in events)
        assert any('energymanager;stop' in e for e in events)

    def test_training_scenario_generation(self) -> None:
        profile = self.module.DifficultyProfile.from_level(5)
        events = self.module.generate_training(420, profile)
        assert any('autotraining;start' in e for e in events)
        assert any('autotraining;phase;tracking' in e for e in events)


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])

