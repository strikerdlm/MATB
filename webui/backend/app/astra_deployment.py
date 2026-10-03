"""Materialize the documented ASTRA schedule through the existing study registry.

Activation is an explicit operator action. Nothing is frozen under an invented
researcher identity and no completed baseline, preparation or recording is seeded.
"""
import json
from fastapi import HTTPException
from sqlmodel import select
from app import study_registry as registry
from app.astra_roster import VISITS, require_active
from app.models import ParticipantRoster, Visit
from app.study_protocol import selected_protocol
from app.study_registry_models import StudyAssignment

STUDY_ID = "astra-matb-field-2026"
PRESET_ID = "astra-matb-field"
VERSION = "1.0.0"


def ensure_preset(runtime):
    from app.openmatb_schemas import ClonePresetRequest, UpdatePresetRequest
    presets = runtime.list_presets()
    current = next((p for p in presets if p.preset_id == PRESET_ID and p.version == VERSION), None)
    if current and current.status == "published":
        return current
    if not current:
        current = runtime.clone_preset("matb-fac-standard", VERSION, ClonePresetRequest(
            preset_id=PRESET_ID, version=VERSION, label_es="ASTRA · familiarización 5 min · bloques 15 min"))
    profiles = {key: value.model_copy(deep=True) for key, value in current.profiles.items()}
    profiles["PRACTICE"].duration_seconds = 300
    profiles["PRACTICE"].difficulty = 0.10
    runtime.update_preset(PRESET_ID, VERSION, UpdatePresetRequest(profiles=profiles))
    return runtime.publish_preset(PRESET_ID, VERSION)


def payload(db, *, include_polar=False, baseline_minutes=5):
    if baseline_minutes not in (5, 10):
        raise HTTPException(422, 'El basal Polar debe ser de 5 o 10 minutos.')
    from app.study_bindings import binding_options
    from matb_integration.scenario_builder import block_order_for_participant
    options = binding_options(db).get("openmatb")
    if not options:
        raise HTTPException(409, "Active el componente OpenMATB en esta estación.")
    def binding(group, identity):
        found = next((p for p in options[group] if p['id'] == identity and p['version'] == VERSION), None)
        if not found:
            raise HTTPException(409, f"Configuración publicada no disponible: {identity}.")
        return found
    config = dict(preset=binding('presets', PRESET_ID), instructions=binding('instructions', 'matb-fac-es-419'),
                  visual=binding('visuals', 'matb-fac-modern'), input_mapping='openmatb-default',
                  scenario_generator='published-preset-v1', scoring='openmatb-current')
    orders = {f"ORDER-{i}": [level.value.upper() for level in block_order_for_participant(f'P{i:02d}')]
              for i in range(1, 7)}
    occasions, preparation, recovery = [], [], []
    for visit in VISITS:
        for block in range(3):
            key = f"v{visit.ordinal - 1}_block{block + 1}"
            rating = key + '_ratings'
            if block:
                recovery.append(dict(key=f"v{visit.ordinal - 1}_rest{block}",
                    anchor_key=f"v{visit.ordinal - 1}_block{block}_ratings", before_key=key, duration_seconds=180))
            occasions.append(dict(key=key, visit_ordinal=visit.ordinal, instrument='openmatb', phase=f'block{block + 1}',
                order=block * 2 + 1, condition_by_arm={arm: order[block] for arm, order in orders.items()}, locale='es-419',
                config=config, prerequisite_keys=[f"v{visit.ordinal - 1}_block{block}_ratings"] if block else []))
            occasions.append(dict(key=rating, visit_ordinal=visit.ordinal, instrument='questionnaire', phase='post_block',
                order=block * 2 + 2, condition_by_arm={arm: order[block] for arm, order in orders.items()}, locale='es-419',
                config=dict(binding_id='MATB-FAC-WORKLOAD-1.0', input_mapping='browser-ratings', scoring='rtlx-mean-bedford'),
                prerequisite_keys=[key], target_key=key))
            for occasion_key, native in ((key, True), (rating, False)):
                preparation.append(dict(occasion_key=occasion_key, placement='prescribed_later',
                    demonstration_required=False, acknowledgement_required=native, comprehension=[], practice=[],
                    rationale='Reconocer los controles y el indicativo del entorno nativo real antes de cada bloque; la familiarización V0 se registra por separado.'))
    native_keys = [o['key'] for o in occasions if o['instrument'] == 'openmatb']
    rating_keys = [o['key'] for o in occasions if o['instrument'] == 'questionnaire']
    result = dict(study=dict(study_id=STUDY_ID, title='ASTRA · MATB V0–V7', template_family=selected_protocol().protocol_id,
        synthetic=False, enabled_instruments=['openmatb', 'questionnaire'],
        visits=[dict(ordinal=v.ordinal, code=v.code, scheduled_day=v.scheduled_day) for v in VISITS],
        arms=list(orders), assignment_method='explicit_researcher_selection', occasions=occasions, recovery_intervals=recovery,
        preparation_policy=preparation,
        repeat_policy=dict(permitted_causes=['hardware_failure','software_failure','technical_failure','lost_connection','operator_stop'],
            max_attempts=3, selection='explicit', rationale='Repetición técnica explícita, conservando todos los intentos y la causa; seleccionar evidencia en revisión.'),
        interruption_policy=dict(available_outcomes='retain_available', rationale='Conservar datos disponibles, causa y estado; no completar datos faltantes.'),
        rules=dict(preparation='Manual ASTRA §4.7.6 y guía corregida v2 2026-09-29: 90 min reservados; reposo pre-tarea 5 min documentado externamente; familiarización V0 de 300 s a dificultad 0.10, recordatorio V1–V7 y reconocimiento del entorno en cada bloque.',
                   repeat='Hasta tres intentos por falla técnica; selección explícita y conservación de originales. Esta política operativa se revisa al activar.',
                   interruption='Conservar toda interrupción y los datos disponibles; no inferir finalización, adquisición HRV ni consentimiento.')),
        analysis=dict(unit='attempt', outcomes=[
            dict(key='sysmon', metric='openmatb.sysmon_hit_rate', units='proportion', occasion_keys=native_keys, summary='individual'),
            dict(key='tracking', metric='openmatb.track_rmse_deviation', units='normalized_cursor_distance', occasion_keys=native_keys, summary='individual'),
            dict(key='rtlx', metric='questionnaire.rtlx_mean_0_100', units='0-100', occasion_keys=rating_keys, summary='individual')],
            contrasts=[], rules=dict(exclusions='No imputar resultados ausentes; revisar intentos y calidad antes del análisis.',
                denominators='Conservar todos los intentos asignados y sus motivos de ausencia.', qualification='Informar estado de evidencia y preparación; sin inferir validez clínica.',
                pooling='Separar configuraciones; no promediar personas ni misiones automáticamente.', historical_unknowns='exclude'),
            eligibility_policy=dict(repeat_selection='explicit', incomplete_denominator='assigned', missing_handling='exclude_outcome',
                source_requirement='report_status', physical_requirement='report_status', human_calibration_requirement='report_status',
                participant_preparation_requirement='report_status', protocol_requirement='report_status', configuration_pooling='identical_only',
                pooling_review=None, hcf_enabled=False, hcf_screen_keys=[], hcf_attempt_selection='explicit',
                rationale='Registro descriptivo por intento con estados de evidencia explícitos; revisión humana antes de seleccionar resultados.')))
    if include_polar:
        polar = binding_options(db).get('physiology')
        if not polar:
            raise HTTPException(409, 'Active el componente Polar H10 en esta estación antes de incluirlo en el protocolo.')
        result['study']['enabled_instruments'].append('physiology')
        for occasion in occasions[:]:
            # Keep the exact native/rating keys and counterbalanced order.
            occasion['order'] = occasion['order'] * 2 + 2
            if occasion['instrument'] != 'openmatb':
                continue
            occasion['collection_group'] = occasion['key'] + '_polar'
            companion = dict(key=occasion['key'] + '_polar', visit_ordinal=occasion['visit_ordinal'],
                instrument='physiology', phase='TASK_PRE' if occasion['phase'] == 'block1' else 'TASK',
                order=occasion['order'] + 1, condition_by_arm=occasion['condition_by_arm'], locale='es-419',
                config=polar[0], collection_group=occasion['collection_group'], accompanying_key=occasion['key'],
                prerequisite_keys=occasion['prerequisite_keys'])
            occasions.append(companion)
        occasions.append(dict(key='v0_pre_rest', visit_ordinal=1, instrument='physiology', phase='PRE_REST_SEATED',
            order=1, condition_by_arm={arm: f'PRE_REST_SEATED_{baseline_minutes}MIN' for arm in orders}, locale='es-419', config=polar[0], prerequisite_keys=[]))
        for occasion in occasions:
            if occasion['instrument'] == 'physiology':
                preparation.append(dict(occasion_key=occasion['key'], placement='prescribed_later',
                    demonstration_required=False, acknowledgement_required=False, comprehension=[], practice=[],
                    rationale=f'El operador comprueba identidad, banda y señal; PRE sentado: adaptación ≥5 min y registro {baseline_minutes} min. TASK_PRE: reposo contextual 5 min antes del primer bloque.'))
        result['study']['rules']['preparation'] += f' Polar opcional asignado: PRE_REST_SEATED de {baseline_minutes} min tras ≥5 min de adaptación en V0, separado de TASK_PRE de 5 min. Una captura vinculada por bloque, con originales y marcas de tiempo; confirmar sensores físicamente por persona.'
        if baseline_minutes == 5:
            result['study']['rules']['preparation'] += ' Modalidad abreviada solicitada el 2 octubre de 2026: omite el segundo segmento de respaldo de 5 min previsto por el manual ASTRA v2.8; conservar fecha real y desviación del calendario basal.'
    return result


def status(db):
    identity = registry.active_version(db)
    version = registry.get_version(db, identity) if identity else None
    return dict(active=bool(version and version.study_id == STUDY_ID), version_id=identity,
                title=json.loads(version.study_json)['title'] if version else None,
                includes_polar=bool(version and 'physiology' in json.loads(version.study_json)['enabled_instruments']))


def configure(db, runtime, actor, *, include_polar=False, baseline_minutes=5):
    registry.named(actor)
    existing = status(db)
    if existing['active']:
        if include_polar and not existing['includes_polar']:
            raise HTTPException(409, 'El protocolo activo no incluye Polar. Cree una revisión en Configuración del estudio; la versión congelada se conserva.')
        return existing
    if existing['version_id']:
        raise HTTPException(409, 'Esta base ya tiene otro estudio activo. Conserve su configuración y use una base de estación ASTRA separada.')
    ensure_preset(runtime)
    draft = registry.create_draft(db, payload(db, include_polar=include_polar, baseline_minutes=baseline_minutes))
    rehearsal = registry.rehearse(db, draft.id)
    version = registry.freeze(db, draft.id, dict(actor=actor, reason='Activación explícita del protocolo de aplicación ASTRA y sus políticas operativas/descriptivas.',
        sha256=draft.sha256, rehearsal_id=rehearsal.id))
    registry.activate(db, version.id, actor=actor, reason='Aplicación MATB ASTRA V0–V7')
    db.commit()
    return status(db)


def assign_visit(db, participant_id, visit_ordinal):
    require_active(db, participant_id)
    person = db.get(ParticipantRoster, participant_id)
    if not person or person.mission not in {'ASTRA-1', 'ASTRA-2'}:
        raise HTTPException(404, 'Tripulante ASTRA no encontrado.')
    visit = db.exec(select(Visit).where(Visit.participant_id == participant_id, Visit.visit_ordinal == visit_ordinal)).first()
    if not visit:
        raise HTTPException(404, 'Visita no encontrada.')
    existing = [a for a in db.exec(select(StudyAssignment).where(StudyAssignment.visit_id == visit.id)).all() if registry.assignment_is_current(db, a)]
    if existing:
        return existing[0]
    current = status(db)
    if not current['active']:
        raise HTTPException(409, 'Active el protocolo ASTRA una vez antes de aplicar las visitas.')
    version = registry.get_version(db, current['version_id'])
    # Same immutable numeric identity across missions and all visits.
    arm = f"ORDER-{(int(participant_id[1:]) - 1) % 6 + 1}"
    row = registry.assign(db, version.id, participant_id, visit.id, arm, actor=version.actor)
    db.commit()
    return row
