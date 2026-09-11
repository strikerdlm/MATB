"""Raw calculator and isolated no-index wheel closure tests for declared instruments."""
import base64
import json
import pytest
from matb_integration.analysis.study_calculators import calculate


def test_native_raw_reconciliation_keeps_original_eligibility(tmp_path):
    from matb_integration.evidence.reference import synthetic_capture
    from matb_integration.evidence.contracts import DERIVATION_VERSION
    artifacts=synthetic_capture(tmp_path/'capture')
    source=dict(instrument='openmatb',raw=dict(artifacts={k:base64.b64encode(v).decode() for k,v in artifacts.items()},derivation_version=DERIVATION_VERSION))
    result=calculate(source,dict(metric='openmatb.sysmon_hit_rate'))
    assert result['source_eligible'] and result['value'] is not None
    assert result['metric']['metric']=='sysmon_hit_rate'


def test_liftoff_original_visible_results_and_canonical_telemetry():
    pytest.importorskip('matb_integration.liftoff')
    record=dict(schema_version='liftoff-telemetry-v1',session_id='00000000-0000-4000-8000-000000000001',sequence=1,received_monotonic_ns=1,received_utc='2026-09-10T00:00:00Z',simulator_time=0,position_native=[0,0,0],attitude_native=[0,0,0,1],velocity_native=[0,0,0],angular_rate_native=[0,0,0],processed_input=[0,0,0,0],battery_voltage=12,charge_percent=100,motor_rpm=[0,0,0,0])
    source=dict(instrument='liftoff',protocol_valid=False,raw=dict(telemetry=[record],visible_results=dict(valid_lap_times_s=[10.,12.,14.],invalid_laps=1,observer_restart_count=0)))
    assert calculate(source,dict(metric='liftoff.primary.median_lap_time_s'))['value']==12
    assert calculate(source,dict(metric='liftoff.primary.valid_laps'))['value']==3
    assert not calculate(source,dict(metric='liftoff.primary.valid_laps'))['protocol_valid']


def test_mission_explicit_block_selection_never_picks_available_block():
    pytest.importorskip('matb_integration.suas')
    record=dict(session_id='session',block_id='LOW',sequence=1,simulation_time_ms=0,wall_time_utc='2026-09-10T00:00:00Z',state_version=1,kind='lifecycle',payload={'state':'started','active_aircraft':1})
    source=dict(instrument='suas',protocol_valid=True,raw=dict(streams={'events.jsonl':dict(records=[record],manifest={'coverage_target_ppm':800000,'contact_effectiveness_target_ppm':800000,'asset_preservation_target_ppm':800000,'timeliness_target_ppm':800000})}))
    outcome=dict(metric='suas.coverage.percent',source_keys=['LOW'],source_summary='individual')
    assert calculate(source,outcome)['value']==0
    with pytest.raises(KeyError): calculate(source,{**outcome,'source_keys':['HIGH']})


def test_physiology_raw_rr_replays_existing_phase_gates():
    pa=pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq
    table=pa.table(dict(beat_monotonic_ns=[i*1_000_000_000 for i in range(300)],rr_ms=[1000.]*300,contact_supported=[True]*300,contact_detected=[True]*300,gap_before=[False]*300,connection_epoch=[1]*300))
    sink=pa.BufferOutputStream();pq.write_table(table,sink)
    source=dict(instrument='physiology',raw=dict(rr_parquet=base64.b64encode(sink.getvalue().to_pybytes()).decode(),markers=[dict(label='baseline',sequence=1,host_monotonic_ns=0)]))
    outcome=dict(metric='physiology.mean_hr_bpm',source_keys=['baseline'])
    result=calculate(source,outcome)
    assert result['value']==60 and result['protocol_valid']
    source['raw']['markers'].append(dict(label='baseline',sequence=2,host_monotonic_ns=1))
    with pytest.raises(ValueError,match='ambiguous'): calculate(source,outcome)


def test_selected_calculator_wheels_install_offline_and_import_only_packaged_source(tmp_path):
    import os
    import subprocess
    import sys
    import venv
    from pathlib import Path
    from app.study_analysis_bundle import implementation_artifacts
    pytest.importorskip("matb_integration.liftoff");pytest.importorskip("matb_integration.suas");pytest.importorskip("pyarrow")
    files,identity=implementation_artifacts({'pvt','screen','openmatb','questionnaire','liftoff','suas','physiology'})
    root=tmp_path/'offline';root.mkdir()
    for name,data in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    venv.EnvBuilder(with_pip=True,system_site_packages=False).create(root/'venv')
    python=root/('venv/Scripts/python.exe' if os.name=='nt' else 'venv/bin/python');env={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME','VIRTUAL_ENV'}}
    result=subprocess.run([str(python),'-I','-m','pip','install','--no-index','--find-links',str(root/'wheels'),'-r',str(root/'requirements.lock')],env=env,cwd=root,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    script="""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path('source').resolve()))
from matb_integration.pvt_scoring import PvtAssessmentIn,_metrics
from matb_integration.screen.scoring import score_screen
from matb_integration.evidence.reconcile import reconcile
from matb_integration.liftoff.metrics import compute_metrics,VisibleResults
from matb_integration.suas.metrics.mission import derive_block_metrics
from matb_integration.physiology.analysis import analyze_rr_window
from matb_integration.analysis.study_calculators import calculate
assert calculate(dict(instrument='liftoff',raw=dict(telemetry=[],visible_results=dict(valid_lap_times_s=[10.,14.],invalid_laps=0,observer_restart_count=0))),dict(metric='liftoff.primary.median_lap_time_s'))['value']==12
assert analyze_rr_window([1000.]*300)['mean_instantaneous_hr_bpm']==60
paths={name:module.__file__ for name,module in sys.modules.items() if name.startswith('matb_integration') and getattr(module,'__file__',None)}
assert paths and all(Path(path).is_relative_to(Path('source').resolve()) for path in paths.values())
assert not any('/tmp/matb-predictability-testdeps' in path for path in sys.path)
print(json.dumps(dict(status='offline_source_isolated',imports=paths)))
"""
    run=subprocess.run([str(python),'-I','-c',script],env=env,cwd=root,capture_output=True,text=True)
    assert run.returncode==0,run.stdout+run.stderr
    (root/'isolation-proof.json').write_text(run.stdout)
    print('OFFLINE_KIT',root,'dependencies',json.dumps(identity['dependencies'],sort_keys=True))
