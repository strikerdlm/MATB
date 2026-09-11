"""Software-only preflight: no timed event executes before explicit release."""
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest


def test_preflight_holds_every_scheduler_entry_and_allows_abort():
    from core.scheduler import Scheduler
    scheduler = object.__new__(Scheduler)
    scheduler.preflight_held = True
    scheduler.control_bridge = MagicMock()
    scheduler.control_bridge.drain.return_value = [{'command':'resume'}]
    scheduler.scenario_time = 0
    plugin = MagicMock()
    scheduler.execute_plugins_methods([plugin], ["start", "show", "resume"])
    plugin.start.assert_not_called()
    plugin.show.assert_not_called()
    plugin.resume.assert_not_called()
    scheduler.update(100)
    scheduler._operator_resume()
    scheduler.resume_scenario()
    assert scheduler.preflight_held
    scheduler.control_bridge.emit.assert_called_with('command_rejected', command='resume', reason='preflight_admission_required')
    scheduler.exit = MagicMock()
    scheduler.control_bridge.drain.return_value = [{'command':'abort'}]
    scheduler._poll_control_bridge(0)
    scheduler.exit.assert_called_once_with(completion='aborted')


def test_snapshot_uses_enabled_tasks_and_resolved_keys_and_rejects_dynamic_mapping():
    from core.preflight import snapshot
    from core.event import Event
    scheduler = SimpleNamespace(plugins={'sysmon':SimpleNamespace(parameters={'lights':{'1':{'key':'F5'}},'scales':{}})},
        joystick=None, scenario_time=0, events=[Event(1,0,'sysmon','start'),Event(2,0,'sysmon',['lights-1-key','JOY_BTN_1'])])
    data = snapshot(scheduler)
    assert data['enabled_tasks'] == ['sysmon']
    assert data['mapping']['sysmon']['lights']['1']['key'] == 'JOY_BTN_1'
    assert data['issues'] == ['required_controller_unavailable']
    scheduler.events.append(Event(3,1,'sysmon',['lights-1-key','F6']))
    assert 'dynamic_response_mapping' in snapshot(scheduler)['issues']


def test_preflight_time_is_not_an_acquired_frame_gap(monkeypatch):
    from core.scheduler import Scheduler
    from core.logger import Logger
    from core import scheduler as module
    logger = object.__new__(Logger)
    logger._last_update_monotonic_ns = None
    logger._last_scenario_time = None
    accumulator = MagicMock()
    logger._timing_accumulator = MagicMock(return_value=accumulator)
    monkeypatch.setattr(module, 'get_logger', lambda: logger)
    times = iter([900_000_000_000, 900_100_000_000, 902_100_000_000])
    monkeypatch.setattr('core.logger.perf_counter_ns', lambda: next(times))
    scheduler = object.__new__(Scheduler)
    scheduler.preflight_held = True
    scheduler.scenario_time = 0
    scheduler.pause_scenario_time = False
    scheduler.experiment_clock = MagicMock()
    scheduler.update_timers(900)
    assert scheduler.scenario_time == 0
    assert logger._last_update_monotonic_ns is None
    scheduler.preflight_held = False
    scheduler.update_timers(.1)
    accumulator.add.assert_not_called()
    scheduler.update_timers(.1)
    scheduler.update_timers(2)
    assert scheduler.scenario_time == pytest.approx(2.2)
    # Real post-admission stalls remain measurable; the 900-second hold never enters QC.
    intervals = [call.args[0] for call in accumulator.add.call_args_list]
    assert intervals == pytest.approx([100,100,2000,2000])


def test_scientific_started_is_recorded_only_at_admitted_release(tmp_path):
    import io, json
    from uuid import UUID
    from tests.test_logger import _make_logger
    path = tmp_path / 'prepared.csv'; path.write_text('')
    logger = _make_logger(path=path, events_path=tmp_path/'prepared.events.jsonl', events_file=io.StringIO(),
        _scientific_session_uuid=UUID('12345678-1234-5678-1234-567812345678'))
    logger.configure_scientific_context(scenario_sha256='a'*64,profile_id='fixture',source_commit='b'*40,
        component_version='test',scenario_manifest_evidence={'status':'verified'},preparation_hold=True)
    stream = path.with_suffix('.scientific.events.jsonl')
    def phases(): return [json.loads(line)['event_type'] for line in stream.read_text().splitlines()]
    assert 'block.prepared' in phases() and 'block.started' not in phases()
    logger.admit_preflight()
    assert phases().count('block.started') == 1
    logger.admit_preflight()
    assert phases().count('block.started') == 1
    logger.finalize_evidence('aborted')


def test_only_exact_release_admits_the_held_scheduler(monkeypatch):
    from core.scheduler import Scheduler
    from core.preflight import snapshot
    from core.event import Event
    from core.window import Window
    from core import scheduler as module
    scheduler=object.__new__(Scheduler)
    plugin=MagicMock();plugin.parameters={'lights':{'1':{'key':'F5'}},'scales':{}}
    scheduler.plugins={'sysmon':plugin};scheduler.events=[Event(1,0,'sysmon','start')]
    scheduler.joystick=None;scheduler.scenario_time=0;scheduler.preflight_held=True
    scheduler.preflight_snapshot=snapshot(scheduler);scheduler.control_bridge=MagicMock()
    scheduler.control_bridge.drain.return_value=[{'command':'release_preflight','snapshot_sha256':'wrong'}]
    logger=MagicMock();monkeypatch.setattr(module,'get_logger',lambda:logger)
    monkeypatch.setattr(Window,'MainWindow',MagicMock())
    scheduler._poll_control_bridge(0)
    assert scheduler.preflight_held
    logger.admit_preflight.assert_not_called()
    scheduler.execute_plugins_methods([plugin],'start');plugin.start.assert_not_called()
    scheduler.control_bridge.drain.return_value=[{'command':'release_preflight','snapshot_sha256':scheduler.preflight_snapshot['sha256']}]
    scheduler._poll_control_bridge(0)
    assert not scheduler.preflight_held and scheduler.scenario_time==0
    logger.admit_preflight.assert_called_once()
    scheduler.execute_plugins_methods([plugin],'start');plugin.start.assert_called_once()


def test_controller_snapshot_rejects_missing_required_axis_and_button():
    from core.preflight import snapshot
    from core.event import Event
    device=SimpleNamespace(device=SimpleNamespace(name='software joystick fixture'),buttons=[False],x=0.,y=None)
    scheduler=SimpleNamespace(plugins={'track':SimpleNamespace(parameters={'inverseaxis':False,'joystickforce':1}),
        'sysmon':SimpleNamespace(parameters={'lights':{'1':{'key':'JOY_BTN_2'}},'scales':{}})},
        joystick=SimpleNamespace(device=device),events=[Event(1,0,'track','start'),Event(2,0,'sysmon','start')])
    value=snapshot(scheduler)
    assert value['controller']['axes']==['x']
    assert set(value['issues'])=={'required_controller_axes_unavailable','required_controller_button_unavailable'}
