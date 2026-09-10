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
