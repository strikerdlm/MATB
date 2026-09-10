"""Task2 review regressions: truthful causes, scoped journeys and rating receipts."""
from datetime import datetime, timedelta, timezone
import pytest
from sqlmodel import Session, select
from tests.test_assessments import occasion, attempt
from tests.test_pvt_endpoint import _enroll, _payload
from tests.test_screen_endpoint import _payload as screen_payload


@pytest.mark.parametrize('category', ['withdrawal', 'operator_stop', 'hardware_failure', 'software_failure', 'planned_interruption', 'unknown', 'participant_stop', 'technical_failure', 'lost_connection', 'other'])
def test_interruption_category_is_preserved_without_inferred_cause(client, category):
    _enroll(client)
    a = attempt(client, occasion(client))
    response = client.post(f"/assessments/attempts/{a['id']}/interrupt", json={'category': category})
    assert response.status_code == 200, response.text
    assert response.json()['interruption_category'] == category
    assert client.get(f"/assessments/attempts/{a['id']}").json()['interruption_category'] == category
    # Retrying a different interpretation must not overwrite the recorded cause.
    assert client.post(f"/assessments/attempts/{a['id']}/interrupt", json={'category': 'unknown' if category != 'unknown' else 'operator_stop'}).status_code == 409


def save_screen(client, visit_id=None):
    a = attempt(client, occasion(client, 'screen', **({'visit_id': visit_id} if visit_id else {})))
    assert client.post('/screen', json={'participant_id': 'P01', 'execution_purpose': 'study', 'attempt_id': a['id'], 'payload': screen_payload()}).status_code == 201
    return a


def repeated_h10(engine):
    from app.physiology_models import PolarCaptureRecord
    with Session(engine) as db:
        for index in range(2):
            db.add(PolarCaptureRecord(id=f'baseline-{index}', participant_id='P01', matb_session_kind='generic', matb_session_id='baseline:P01:V1', device_alias='H10', lifecycle='complete', artifact_state='finalized', execution_purpose='study', requested_settings_json='{}', controller_lease_hash='hash', started_at=datetime(2026, 9, 10, tzinfo=timezone.utc), ended_at=datetime(2026, 9, 10, tzinfo=timezone.utc) + timedelta(minutes=5)))
        db.commit()


def test_screen_journey_ignores_unrelated_pvt_and_h10_repeats(client, engine):
    _enroll(client)
    for _ in range(2):
        a = attempt(client, occasion(client))
        assert client.post('/pvt', json=_payload(attempt_id=a['id'])).status_code == 201
    repeated_h10(engine)
    screen = save_screen(client)
    response = client.get(f"/journey/P01/1?experiment=screen&attempt_id={screen['id']}")
    assert response.status_code == 200, response.text
    assert response.json()['attempt_id'] == screen['id']


def test_pvt_journey_ignores_unrelated_h10_repeats(client, engine):
    _enroll(client)
    a = attempt(client, occasion(client))
    client.post('/pvt', json=_payload(attempt_id=a['id']))
    repeated_h10(engine)
    assert client.get(f"/journey/P01/1?experiment=pvt&attempt_id={a['id']}").status_code == 200


def test_screen_journey_rejects_other_visit_and_limits_implicit_rows(client):
    _enroll(client)
    visit2 = client.get('/participants/P01/visits').json()[1]['id']
    screen = save_screen(client, visit2)
    response = client.get(f"/journey/P01/1?experiment=screen&attempt_id={screen['id']}")
    assert response.status_code == 404
    implicit = client.get('/journey/P01/1?experiment=screen').json()
    assert next(step for step in implicit['steps'] if step['id'] == 'complete')['complete'] is False
    assert client.get(f"/journey/P01/2?experiment=screen&attempt_id={screen['id']}").status_code == 200


def test_unknown_visit_screen_uses_labeled_compatibility_path(client):
    _enroll(client)
    row = client.post('/screen', json={'participant_id': 'P01', 'execution_purpose': 'study', 'payload': screen_payload()}).json()
    selected = client.get(f"/journey/P01/1?experiment=screen&attempt_id={row['attempt_id']}")
    assert selected.status_code == 404
    legacy = client.get('/journey/P01/1?experiment=screen&legacy_screen=true')
    assert legacy.status_code == 200
    assert legacy.json()['selection_mode'] == 'legacy_screen_visit_unknown'
    assert legacy.json()['assessment_visit_id'] is None


@pytest.mark.parametrize('association', ['declaration', 'migration'])
def test_legacy_polar_exact_selection_uses_recorded_baseline_without_assigning_visit(client, engine, association):
    from app.physiology_models import PolarCaptureRecord
    from app.assessment_models import AssessmentOccasion
    from app.assessment_adapters import source_attempt
    from app.assessment_migration import migrate_assessments
    from app.purpose_service import declare_acquisition, migrate_purpose_provenance, provenance_view
    _enroll(client)
    _enroll(client, 'P02')
    specs = [('baseline-A', 'P01', 'baseline:P01:V1', 300),
             ('baseline-B', 'P01', 'baseline:P01:V1', 180),
             ('wrong-baseline', 'P01', 'baseline:P01:V2', 300),
             ('wrong-participant', 'P02', 'baseline:P01:V1', 300)]
    with Session(engine) as db:
        for identity, participant, baseline, duration in specs:
            source = PolarCaptureRecord(id=identity, participant_id=participant,
                matb_session_kind='generic', matb_session_id=baseline, device_alias='H10',
                lifecycle='prepared', execution_purpose='study', requested_settings_json=' {"original": true} ',
                controller_lease_hash='hash')
            if association == 'declaration':
                declare_acquisition(db, source, purpose='study')
            else:
                db.add(source)
            source.started_at = datetime(2026, 9, 10, tzinfo=timezone.utc)
            source.ended_at = source.started_at + timedelta(seconds=duration)
            source.lifecycle = 'complete'
            source.artifact_state = 'finalized'
            db.add(source)
        db.commit()
    if association == 'migration':
        migrate_purpose_provenance(engine)
        migrate_assessments(engine)
    with Session(engine) as db:
        attempts = {identity: source_attempt(db, 'polar_capture', identity).id for identity, *_ in specs}
        before = {}
        for identity, *_ in specs:
            linked = source_attempt(db, 'polar_capture', identity)
            context = db.get(AssessmentOccasion, linked.occasion_id)
            assert context.visit_id is None and context.phase is None
            assert context.origin == ('legacy_compat' if association == 'declaration' else 'legacy')
            before[identity] = (context.model_dump(), db.get(PolarCaptureRecord, identity).model_dump(),
                                provenance_view(db, linked.purpose_provenance_id))
    assert client.get('/journey/P01/1?experiment=physiology').status_code == 409
    for identity, complete in [('baseline-A', True), ('baseline-B', False)]:
        aid = attempts[identity]
        # Strict assignment selection remains strict until compatibility is chosen.
        assert client.get(f'/journey/P01/1?experiment=physiology&attempt_id={aid}').status_code == 404
        response = client.get(f'/journey/P01/1?experiment=physiology&attempt_id={aid}&legacy_polar=true')
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['selection_mode'] == 'legacy_polar_recorded_baseline'
        assert body['assessment_visit_id'] is None
        assert body['attempt_id'] == aid
        assert next(step for step in body['steps'] if step['id'] == 'complete')['complete'] is complete
        mission = client.get(f'/journey/P01/1?experiment=suas&polar_attempt_id={aid}&legacy_polar=true')
        assert mission.status_code == 200, mission.text
        assert mission.json()['polar_selection_mode'] == 'legacy_polar_recorded_baseline'
        assert mission.json()['polar_assessment_visit_id'] is None
        assert mission.json()['polar_attempt_id'] == aid
        assert next(step for step in mission.json()['steps'] if step['id'] == 'polar')['complete'] is complete
    for identity in ['wrong-baseline', 'wrong-participant']:
        for query in ['experiment=physiology&attempt_id=', 'experiment=suas&polar_attempt_id=']:
            assert client.get(f'/journey/P01/1?{query}{attempts[identity]}&legacy_polar=true').status_code == 404
    with Session(engine) as db:
        for identity, *_ in specs:
            linked = source_attempt(db, 'polar_capture', identity)
            assert (db.get(AssessmentOccasion, linked.occasion_id).model_dump(),
                    db.get(PolarCaptureRecord, identity).model_dump(),
                    provenance_view(db, linked.purpose_provenance_id)) == before[identity]


def test_polar_compatibility_flag_cannot_override_an_assigned_visit(client, engine):
    from app.physiology_models import PolarCaptureRecord
    from app.purpose_service import declare_acquisition
    _enroll(client)
    visit2 = client.get('/participants/P01/visits').json()[1]['id']
    selected = attempt(client, occasion(client, 'physiology', visit_id=visit2))
    with Session(engine) as db:
        source = PolarCaptureRecord(id='assigned-other-visit', participant_id='P01',
            matb_session_kind='generic', matb_session_id='baseline:P01:V1', device_alias='H10',
            lifecycle='prepared', execution_purpose='study', requested_settings_json='{}', controller_lease_hash='hash')
        declare_acquisition(db, source, purpose='study', attempt_id=selected['id'])
        source.artifact_state = 'finalized'
        source.lifecycle = 'complete'
        source.started_at = datetime(2026, 9, 10, tzinfo=timezone.utc)
        source.ended_at = source.started_at + timedelta(seconds=300)
        db.add(source)
        db.commit()
    for query in ['experiment=physiology&attempt_id=', 'experiment=suas&polar_attempt_id=']:
        assert client.get(f"/journey/P01/1?{query}{selected['id']}&legacy_polar=true").status_code == 404
