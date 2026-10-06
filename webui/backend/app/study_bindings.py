"""Exact executable configuration allowlist; never import optional runtime modules."""
import hashlib
import os
from pathlib import Path
from sqlalchemy import inspect, text

# Revision hashes pin browser instructions, controls, geometry and scoring source together.
_ROOT = Path(__file__).resolve().parents[3]
_BROWSER_FILES = {
    'pvt': ['webui/frontend/src/components/pvt/PvtRunner.tsx', 'webui/frontend/src/lib/pvt.ts', 'webui/frontend/src/app/pvt/page.tsx'],
    'screen': ['webui/frontend/src/components/screen/TaskRunner.tsx', 'webui/frontend/src/lib/screen.ts', 'webui/frontend/src/app/screen/page.tsx'],
}


def browser_binding(instrument):
    paths = [*_BROWSER_FILES[instrument], 'webui/backend/app/study_preparation.py', 'webui/backend/app/study_policies.py', 'webui/backend/app/routers/study_preparation.py', 'webui/frontend/src/components/study/StudyReturn.tsx', 'webui/frontend/src/components/study/StudyParticipant.tsx', 'webui/frontend/src/lib/assigned-attempt.ts', 'webui/frontend/src/lib/i18n.tsx', 'webui/frontend/src/components/instructions/InstructionAudio.tsx', f'webui/backend/app/routers/{instrument}.py', f'matb_integration/{instrument}.py']
    paths += ['webui/frontend/src/components/crew/CrewBrowserRunner.tsx', 'webui/backend/app/crew_workflow.py']
    # Include all stimulus implementation and scoring files, preserving actual source bytes.
    files = {p for folder in [f'webui/frontend/src/components/{instrument}', f'matb_integration/{instrument}']
             for p in (_ROOT / folder).rglob('*') if p.is_file() and p.suffix in {'.py', '.ts', '.tsx'} and '.test.' not in p.name}
    if instrument == 'pvt': paths += ['matb_integration/pvt_scoring.py']
    if instrument == 'screen': paths += ['matb_integration/log_converter.py', 'matb_integration/suhir/hcf.py']
    files.update(_ROOT / p for p in paths if (_ROOT / p).exists())
    audio_prefixes = ['pvt', 'kss'] if instrument == 'pvt' else ['screen']
    files.update(p for prefix in audio_prefixes for p in (_ROOT / 'webui/frontend/public/audio/instructions').glob(prefix + '-*.mp3'))
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda p: p.relative_to(_ROOT).as_posix()):
        digest.update(path.relative_to(_ROOT).as_posix().encode()); digest.update(b'\0'); digest.update(path.read_bytes())
    return {'binding_id': f'{instrument}-browser-v1', 'sha256': digest.hexdigest(),
            'input_mapping': 'space' if instrument == 'pvt' else 'screen-default',
            'scoring': f'{instrument}-current', 'fast_mode': False}


def scenario_directory():
    value = Path(os.getenv('MATB_SIMULATION_SCENARIO_DIR', 'scenarios/suas'))
    return value if value.is_absolute() else _ROOT / value


def binding_options(db):
    from .components import is_component_active
    result = {key: [browser_binding(key)] for key in ('pvt', 'screen')}
    tables = set(inspect(db.connection()).get_table_names())
    native = {}
    for key, table, identity in [('presets', 'openmatb_preset_set', 'preset_id'),
                                  ('instructions', 'openmatb_instruction_protocol', 'protocol_id'),
                                  ('visuals', 'openmatb_visual_profile', 'profile_id')]:
        native[key] = [dict(row) for row in db.execute(text(f'SELECT {identity} AS id, version, sha256 FROM {table} WHERE status=\'published\'')).mappings()] if table in tables else []
    if is_component_active('matb-openmatb'): result['openmatb'] = native
    from importlib.util import find_spec
    if is_component_active('matb-physiology') and find_spec('app.physiology_schemas'):
        from app.physiology_schemas import CaptureSettings
        result['physiology'] = [dict(binding_id='polar-h10-pmd-v1', input_mapping='rr-ecg-acc', settings=CaptureSettings().model_dump(), scoring='raw-streams')]
    if is_component_active('matb-liftoff') and find_spec('app.liftoff_schemas'):
        from app.liftoff_schemas import LiftoffConfiguration
        result['liftoff_schema'] = LiftoffConfiguration.model_json_schema()
    from importlib.util import find_spec
    if is_component_active('matb-suas') and find_spec('matb_integration.suas') and find_spec('app.simulation_schemas'):
        from matb_integration.suas.scenarios.loader import load_scenario
        result['suas'] = [{'id': p.stem, 'sha256': load_scenario(p).sha256} for p in sorted(scenario_directory().glob('*.yaml'))]
    return result


def binding_issues(db, occasion):
    instrument, config = occasion.instrument, occasion.config
    from .components import is_component_active
    component = {'suas':'matb-suas','liftoff':'matb-liftoff','physiology':'matb-physiology','openmatb':'matb-openmatb','questionnaire':'matb-openmatb'}.get(instrument)
    if component and not is_component_active(component): return [f'Instrument component {component} is unavailable or disabled.']
    if instrument in _BROWSER_FILES:
        return [] if config == browser_binding(instrument) else ['Select the installed browser instruction/control/scoring binding.']
    if instrument == 'suas':
        try:
            from app.simulation_schemas import PresentationConfig
            expected_keys = {'binding_id', 'scenario', 'presentation', 'input_mapping', 'scoring', 'practice_included'}
            if set(config) != expected_keys or config.get('binding_id') != 'suas-protocol-v1' or config.get('input_mapping') != 'suas-default' or config.get('scoring') != 'suas-current' or config.get('practice_included') is not True:
                return ['Select the supported mission protocol including its declared practice block.']
            if config['scenario'] not in binding_options(db).get('suas', []): return ['Unknown mission scenario ID/hash.']
            if config['presentation'] is not None:
                from .simulation_presentation_bindings import bind_presentation
                from matb_integration.suas.scenarios.loader import load_scenario
                loaded=load_scenario(scenario_directory() / (config['scenario']['id'] + '.yaml'))
                bind_presentation({}, PresentationConfig.model_validate(config['presentation']), loaded)
            if any(len(value.split('_')) != 3 or set(value.split('_')) != {'LOW','MEDIUM','HIGH'} for value in occasion.condition_by_arm.values()): return ['Mission arm condition must specify a permutation such as LOW_MEDIUM_HIGH.']
            return []
        except (ImportError, ValueError, OSError) as exc: return [f'Unsupported mission presentation configuration: {exc}']
    if instrument == 'physiology':
        try:
            from app.physiology_schemas import CaptureSettings
            expected = dict(binding_id='polar-h10-pmd-v1', input_mapping='rr-ecg-acc', settings=CaptureSettings.model_validate(config.get('settings', {})).model_dump(), scoring='raw-streams')
            return [] if config == expected else ['Select the supported Polar H10 RR/ECG/ACC mapping and exact settings.']
        except (ImportError, ValueError): return ['Unsupported or unavailable Polar H10 settings.']
    if instrument == 'liftoff':
        try:
            from app.liftoff_schemas import LiftoffConfiguration
            expected = dict(binding_id='liftoff-telemetry-all-v1', input_mapping='liftoff-telemetry-all-v1', configuration=LiftoffConfiguration.model_validate(config.get('configuration', {})).model_dump(), scoring='liftoff-current')
            return [] if config == expected else ['Select the supported Liftoff telemetry mapping and complete configuration.']
        except (ImportError, ValueError): return ['Unsupported or incomplete Liftoff configuration.']
    if instrument == 'questionnaire':
        return [] if config == {'binding_id': 'MATB-FAC-WORKLOAD-1.0', 'input_mapping': 'browser-ratings', 'scoring': 'rtlx-mean-bedford'} and occasion.target_key else ['Native workload questionnaire requires the exact task target and supported scoring binding.']
    if instrument == 'openmatb':
        expected = {'preset', 'instructions', 'visual', 'input_mapping', 'scenario_generator', 'scoring'}
        if set(config) != expected or config.get('input_mapping') != 'openmatb-default' or config.get('scenario_generator') != 'published-preset-v1' or config.get('scoring') != 'openmatb-current':
            return ['Select supported native preset, instructions, visual, controls and generator bindings.']
        options = binding_options(db)['openmatb']
        for key, group in [('preset', 'presets'), ('instructions', 'instructions'), ('visual', 'visuals')]:
            if config[key] not in options[group]: return [f'Unknown or unpublished {key} ID/version/hash.']
        locale = db.execute(text('SELECT locale FROM openmatb_instruction_protocol WHERE protocol_id=:id AND version=:version'), config['instructions']).scalar_one()
        if locale != occasion.locale: return ['Instruction locale must match the frozen occasion language.']
        if not set(occasion.condition_by_arm.values()) <= {'LOW', 'MEDIUM', 'HIGH'}: return ['Native condition must be LOW, MEDIUM or HIGH.']
        return []
    return ['This instrument has no executable frozen binding yet; remove it or select an available binding.']


def implementation_binding(instrument):
    """Server-resolved installed implementation identity, included in the draft attestation hash."""
    if instrument in _BROWSER_FILES: return browser_binding(instrument)['sha256']
    roots = {
        'openmatb': ['openmatb', 'matb_integration/evidence', 'webui/backend/app/study_policies.py', 'webui/backend/app/routers/study_preparation.py', 'matb_integration/scenario_builder.py', 'matb_integration/openmatb_visual_profiles.py', 'matb_integration/log_converter.py', 'matb_integration/metrics_schema.py', 'matb_integration/metrics_spec.json', 'webui/backend/app/openmatb_runtime.py', 'webui/backend/app/study_native.py', 'webui/backend/app/study_preparation.py', 'webui/backend/app/study_native_practice.py', 'webui/backend/app/study_preflight.py', 'webui/frontend/src/components/study/StudyParticipant.tsx'],
        'questionnaire': ['webui/frontend/src/components/openmatb/AssignedWorkloadQuestionnaire.tsx', 'webui/backend/app/study_native.py', 'webui/frontend/src/components/openmatb/WorkloadQuestionnaire.tsx', 'webui/frontend/src/lib/i18n.tsx', 'webui/backend/app/openmatb_runtime.py'],
        'liftoff': ['matb_integration/liftoff', 'webui/backend/app/liftoff_runtime.py', 'webui/backend/app/liftoff_schemas.py'],
        'suas': ['matb_integration/suas', 'webui/frontend/src/components/mission', 'webui/frontend/src/lib/simulation', 'webui/backend/app/simulation_runtime.py'],
        'physiology': ['matb_integration/physiology', 'webui/backend/app/physiology_runtime.py', 'webui/backend/app/physiology_schemas.py'],
    }.get(instrument, [])
    roots += ['webui/backend/app/crew_workflow.py', 'webui/frontend/src/components/crew/CrewSelector.tsx'] if instrument in {'openmatb', 'suas'} else []
    files = set()
    for relative in roots:
        root = _ROOT / relative
        files.update([root] if root.is_file() else (p for p in root.rglob('*') if p.is_file() and p.suffix in {'.py','.json','.ts','.tsx'} and '.test.' not in p.name))
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda p:p.relative_to(_ROOT).as_posix()):
        digest.update(path.relative_to(_ROOT).as_posix().encode()); digest.update(b'\0'); digest.update(path.read_bytes())
    return digest.hexdigest()
