"""Native preparation snapshots use the actual retained process and original CSV identity."""
import json
from fastapi import HTTPException
from sqlmodel import select
from .study_registry_models import StudyNativePreflight


def require_held_launch(context):
    """Prior competence never admits a newly generated, unrecognized native runtime."""
    if not context:
        return
    requirement = next(p for p in context['preparation_policy'] if p['occasion_key'] == context['occasion_key'])
    if any(requirement[key] for key in ('demonstration_required', 'acknowledgement_required', 'comprehension', 'practice')):
        raise HTTPException(409, dict(code='study_native_preflight_required',
            message='Prepare and recognize this exact native runtime from the assigned participant flow before release. / Prepare y reconozca este entorno nativo exacto desde el flujo asignado antes de iniciarlo.',
            assignment_url=f"/study/participant?assignment={context['assignment_id']}"))


def retain_snapshot(db, suite, handle):
    from .assessment_adapters import source_attempt
    from .study_registry import canonical
    try: attempt = source_attempt(db, 'openmatb_suite_session', suite.id)
    except HTTPException: return
    if db.get(StudyNativePreflight, suite.id): return
    db.add(StudyNativePreflight(session_id=suite.id, attempt_id=attempt.id,
        block_instance_id=handle.block_instance_id, snapshot_json=canonical(handle.preflight_snapshot), session_csv=str(handle.session_csv)))
    db.flush()


def stable_mapping(snapshot):
    from copy import deepcopy
    value = deepcopy(snapshot)
    value.pop('sha256', None)
    if 'communications' in value.get('mapping', {}): value['mapping']['communications'].pop('owncallsign', None)
    return value


def validate_release(db, suite, handle):
    row = db.get(StudyNativePreflight, suite.id)
    if (not row or row.session_csv != str(handle.session_csv) or row.block_instance_id != handle.block_instance_id
            or json.loads(row.snapshot_json) != handle.preflight_snapshot or handle.preflight_snapshot['issues']):
        raise HTTPException(409, 'Resolve the required controller and reopen native preflight; the retained runtime must match its snapshot.')
    from .assessment_adapters import source_attempt
    from .study_admission import for_occasion
    from .study_preparation import require_preparation
    task = source_attempt(db, 'openmatb_suite_session', suite.id)
    context = for_occasion(db, task.occasion_id)
    require_preparation(db, context, native_session_id=suite.id)
    from .study_registry_models import StudyPreparation, StudyPreparationEvent
    requirement = next(p for p in context['preparation_policy'] if p['occasion_key'] == context['occasion_key'])
    if any([requirement['demonstration_required'], requirement['acknowledgement_required'], requirement['comprehension'], requirement['practice']]):
        events = db.exec(select(StudyPreparationEvent).join(StudyPreparation).where(
            StudyPreparation.assignment_id == context['assignment_id'], StudyPreparation.occasion_key == context['occasion_key'],
            StudyPreparationEvent.stage == 'native_presentation', StudyPreparationEvent.passed == True)).all()
        if not any(json.loads(e.payload_json)['session_id'] == suite.id for e in events):
            raise HTTPException(409, 'Complete recognition for this exact native runtime before release.')


def snapshot_for_attempt(db, attempt_id):
    return db.exec(select(StudyNativePreflight).where(StudyNativePreflight.attempt_id == attempt_id)).first()


def presentation(snapshot, locale):
    en = locale == 'en'
    items = []
    for task in snapshot['enabled_tasks']:
        mapping = snapshot['mapping'][task]
        if task == 'sysmon':
            for group, controls in mapping.items():
                for key, value in controls.items():
                    label = {'lights':('Light' if en else 'Luz'), 'scales':('Gauge' if en else 'Indicador')}[group]
                    items.append(dict(id=f'{task}-{group}-{key}', task=task, text=f"{label} {key}: {value['key']}", question=f"{label} {key}: " + ('response key?' if en else '¿tecla de respuesta?'), answer=value['key']))
        elif task == 'track':
            items.append(dict(id='track', task=task, text=('Use the joystick x/y axes. ' if en else 'Use los ejes x/y del joystick. ') + ('Inverted axes: ' if en else 'Ejes invertidos: ') + str(mapping['inverseaxis']) + ('. Gain: ' if en else '. Ganancia: ') + str(mapping['joystickforce']), question='Controller?' if en else '¿Controlador?', answer='JOYSTICK'))
        elif task == 'communications':
            labels = {'selectradioup':('Select previous radio','Seleccionar radio anterior'), 'selectradiodown':('Select next radio','Seleccionar radio siguiente'),
                      'tunefrequencyup':('Increase frequency','Aumentar frecuencia'), 'tunefrequencydown':('Decrease frequency','Disminuir frecuencia'),
                      'validateresponse':('Validate tuning','Confirmar sintonización')}
            for key, value in mapping['keys'].items():
                label = labels.get(key, (key,key))[0 if en else 1]
                items.append(dict(id=f'comm-{key}', task=task, text=f'{label}: {value}', question=f'{label}: ' + ('key?' if en else '¿tecla?'), answer=value))
            items.append(dict(id='callsign', task=task, text=('Your callsign: ' if en else 'Su indicativo: ') + mapping['owncallsign'], question='Your callsign?' if en else '¿Su indicativo?', answer=mapping['owncallsign']))
        elif task == 'resman':
            for key, value in mapping.items():
                items.append(dict(id=f'pump-{key}', task=task, text=f"{'Pump' if en else 'Bomba'} {key}: {value}", question=f"{'Pump' if en else 'Bomba'} {key}: " + ('key?' if en else '¿tecla?'), answer=value))
    return dict(items=items, enabled_tasks=snapshot['enabled_tasks'], runtime_snapshot=snapshot)
