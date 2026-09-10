"""Repeated acquisition identity, lifecycle and immutable finalization."""
from tests.test_pvt_endpoint import _enroll, _payload
from tests.test_screen_endpoint import _payload as screen_payload


def occasion(client, instrument='pvt', **changes):
    visit_id = client.get('/participants/P01/visits').json()[0]['id']
    body = dict(participant_id='P01', visit_id=visit_id, instrument=instrument,
                phase='baseline', order=1, condition='rest', origin='local')
    body.update(changes)
    response = client.post('/assessments/occasions', json=body)
    assert response.status_code == 201, response.text
    return response.json()


def attempt(client, occ, **changes):
    body = dict(execution_purpose='study')
    body.update(changes)
    r = client.post(f"/assessments/occasions/{occ['id']}/attempts", json=body)
    assert r.status_code == 201, r.text
    a = r.json()
    assert client.post(f"/assessments/attempts/{a['id']}/start").status_code == 200
    return a


def test_three_occasions_preserve_independent_raw_and_purpose(client):
    _enroll(client)
    ids = []
    for i in range(3):
        a = attempt(client, occasion(client, order=i + 1))
        identity = a['purpose_provenance_id']
        assert client.get(f'/purpose-provenance/{identity}').json()['current']['classification'] == 'explicit'
        r = client.post('/pvt', json=_payload(attempt_id=a['id'], kss_score=i + 1))
        assert r.status_code == 201, r.text
        assert r.json()['purpose_provenance_id'] == identity
        ids.append(a['id'])
    for i, aid in enumerate(ids):
        raw = client.get(f'/assessments/attempts/{aid}/raw').json()
        assert raw['record']['kss_score'] == i + 1
    assert len(client.get('/assessments/occasions?participant_id=P01').json()) == 3


def test_interruption_repeat_and_finalization_conflict(client):
    _enroll(client)
    occ = occasion(client)
    a = attempt(client, occ)
    assert client.post(f"/assessments/attempts/{a['id']}/interrupt", json={'category': 'operator_stop'}).status_code == 200
    r = client.post(f"/assessments/attempts/{a['id']}/repeat", json={'execution_purpose': 'study', 'reason': 'resume after interruption'})
    assert r.status_code == 201, r.text
    b = r.json()
    assert b['repeat_of'] == a['id'] and b['ordinal'] == 2
    client.post(f"/assessments/attempts/{b['id']}/start")
    payload = _payload(attempt_id=b['id'])
    first = client.post('/pvt', json=payload)
    assert first.status_code == 201, first.text
    assert client.post('/pvt', json=payload).json()['id'] == first.json()['id']
    assert client.post('/pvt', json={**payload, 'kss_score': 2, 'overwrite': True}).status_code == 409
    assert client.get(f"/assessments/attempts/{a['id']}").json()['acquisition_state'] == 'interrupted'


def test_repeated_screen_is_one_battery_and_legacy_cohort_refuses_ambiguity(client):
    _enroll(client)
    for i in range(2):
        a = attempt(client, occasion(client, 'screen', order=i + 1))
        r = client.post('/screen', json={'participant_id': 'P01', 'execution_purpose': 'study', 'attempt_id': a['id'], 'payload': screen_payload(300 + i)})
        assert r.status_code == 201, r.text
        assert client.get(f"/assessments/attempts/{a['id']}/raw").json()['record']['raw_trials_json']
    assert client.get('/screen').status_code == 409


def test_questionnaire_requires_exact_target_and_matching_context(client):
    _enroll(client)
    target = attempt(client, occasion(client))
    q = occasion(client, 'questionnaire')
    assert client.post(f"/assessments/occasions/{q['id']}/attempts", json={'execution_purpose': 'study'}).status_code == 422
    rating = attempt(client, q, target_attempt_id=target['id'])
    assert rating['target_attempt_id'] == target['id']
    assert client.post('/assessments/occasions', json={'participant_id': 'P01', 'instrument': 'screen', 'phase': 'baseline', 'order': 1, 'origin': 'local'}).status_code == 422


def test_migration_preserves_ids_raw_archives_rerun_and_rollback(tmp_path):
    import json
    import pytest
    from sqlalchemy import text, inspect
    from sqlmodel import create_engine
    from app.assessment_migration import migrate_assessments
    engine = create_engine(f'sqlite:///{tmp_path / "legacy.db"}')
    with engine.begin() as c:
        c.execute(text('CREATE TABLE participant (id TEXT PRIMARY KEY)'))
        c.execute(text("INSERT INTO participant VALUES ('P01')"))
        c.execute(text('CREATE TABLE visit (id INTEGER PRIMARY KEY, participant_id TEXT)'))
        c.execute(text("INSERT INTO visit VALUES (7, 'P01')"))
        c.execute(text('CREATE TABLE pvt_assessment (id INTEGER PRIMARY KEY, participant_id TEXT, visit_id INTEGER UNIQUE, raw_trials_json TEXT, purpose_provenance_id TEXT, execution_purpose TEXT)'))
        c.execute(text("INSERT INTO pvt_assessment VALUES (42, 'P01', 7, ' [1,  2] ', 'original-purpose', 'study')"))
        c.execute(text('CREATE TABLE screenresult (id INTEGER PRIMARY KEY, participant_id TEXT UNIQUE, raw_trials_json TEXT, purpose_provenance_id TEXT, execution_purpose TEXT)'))
        c.execute(text("INSERT INTO screenresult VALUES (9, 'P01', ' { } ', 'screen-purpose', 'study')"))
        c.execute(text('CREATE TABLE archived_assessment (id INTEGER PRIMARY KEY, participant_id TEXT, experiment_id TEXT, original_id INTEGER, snapshot_json TEXT, purpose_provenance_id TEXT)'))
        c.execute(text("INSERT INTO archived_assessment VALUES (5, 'P01', 'pvt', 42, :raw, 'archive-purpose')"), {'raw': '{"id":42,"raw_trials_json":"[99]"}'})
        c.execute(text('CREATE TABLE block (id INTEGER PRIMARY KEY, visit_id INTEGER, workload_level TEXT, UNIQUE(visit_id, workload_level))'))
    original = None
    with engine.connect() as c:
        original = list(c.execute(text("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name")))
    from sqlalchemy import event
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO assessment_source_link'):
            raise RuntimeError('injected failure')
    event.listen(engine, 'before_cursor_execute', fail)
    with pytest.raises(RuntimeError, match='injected failure'):
        migrate_assessments(engine)
    event.remove(engine, 'before_cursor_execute', fail)
    with engine.connect() as c:
        assert list(c.execute(text("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"))) == original
    migrate_assessments(engine)
    with engine.connect() as c:
        before = list(c.execute(text('SELECT * FROM assessment_source_link ORDER BY id')))
        assert c.execute(text('SELECT id, raw_trials_json, purpose_provenance_id FROM pvt_assessment')).one() == (42, ' [1,  2] ', 'original-purpose')
        assert c.execute(text('SELECT visit_id, phase FROM assessment_occasion WHERE instrument=\'screen\'')).one() == (None, None)
        assert c.execute(text('SELECT snapshot_json FROM archived_assessment')).scalar_one() == '{"id":42,"raw_trials_json":"[99]"}'
        assert c.execute(text("SELECT sql FROM sqlite_master WHERE name='block'")).scalar_one() == dict(original)['block']
    migrate_assessments(engine)
    with engine.connect() as c:
        assert list(c.execute(text('SELECT * FROM assessment_source_link ORDER BY id'))) == before
        c.execute(text("INSERT INTO pvt_assessment (id, participant_id, visit_id, raw_trials_json) VALUES (43, 'P01', 7, '[3]')"))


def test_new_legacy_adapter_has_stable_source_link_and_raw(client):
    _enroll(client)
    result = client.post('/pvt', json=_payload()).json()
    link = client.get(f"/assessments/sources/pvt_assessment/{result['id']}")
    assert link.status_code == 200, link.text
    assert link.json()['purpose_provenance_id'] == result['purpose_provenance_id']
    assert client.get(f"/assessments/attempts/{link.json()['id']}/raw").json()['record']['id'] == result['id']


def test_journey_rejects_ambiguous_pvt_instead_of_first(client):
    _enroll(client)
    for i in range(2):
        a = attempt(client, occasion(client, order=i + 1))
        client.post('/pvt', json=_payload(attempt_id=a['id']))
    # All raw attempts count toward selection ambiguity, even invalid repeats.
    assert client.get('/journey/P01/1?experiment=pvt').status_code == 409


def test_refresh_ambiguous_repeat_does_not_modify_fit_or_fail_startup(client, engine):
    from app.hcf_refresh import refresh_fit_hcf
    from sqlmodel import Session
    _enroll(client)
    for i in range(2):
        a = attempt(client, occasion(client, 'screen', order=i + 1))
        assert client.post('/screen', json={'participant_id': 'P01', 'execution_purpose': 'study', 'attempt_id': a['id'], 'payload': screen_payload(300 + i)}).status_code == 201
    with Session(engine) as db:
        assert refresh_fit_hcf(db) == 0


def test_known_practice_classification_excluded_from_legacy_screen_cohort(client):
    _enroll(client)
    row = client.post('/screen', json={'participant_id': 'P01', 'execution_purpose': 'study', 'payload': screen_payload()}).json()
    assert client.post(f"/purpose-provenance/{row['purpose_provenance_id']}/classifications", json={'purpose': 'practice', 'reviewer': 'Researcher', 'reason': 'practice confirmed'}).status_code == 201
    assert client.get('/screen').json()['screens'] == []


def test_raw_save_can_follow_explicit_acquisition_finish(client):
    _enroll(client)
    a = attempt(client, occasion(client))
    finished = client.post(f"/assessments/attempts/{a['id']}/finish")
    assert finished.status_code == 200
    assert finished.json()['receipt']['raw_saving'] == 'unknown'
    assert client.post('/pvt', json=_payload(attempt_id=a['id'])).status_code == 201


def test_questionnaire_cannot_target_another_visit(client):
    _enroll(client)
    target = attempt(client, occasion(client))
    second_visit = client.get('/participants/P01/visits').json()[1]['id']
    q = occasion(client, 'questionnaire', visit_id=second_visit)
    assert client.post(f"/assessments/occasions/{q['id']}/attempts", json={'execution_purpose': 'study', 'target_attempt_id': target['id']}).status_code == 422


def test_historical_occasion_review_appends_without_inventing_original_visit(client, engine):
    from app.assessment_models import AssessmentOccasion
    from sqlmodel import Session
    _enroll(client)
    with Session(engine) as db:
        old = AssessmentOccasion(participant_id='P01', instrument='screen', origin='legacy')
        db.add(old); db.commit(); db.refresh(old); identity = old.id
    visit = client.get('/participants/P01/visits').json()[0]['id']
    response = client.post(f'/assessments/occasions/{identity}/classifications', json={'visit_id': visit, 'phase': 'pre', 'order': 1, 'reviewer': 'Researcher', 'reason': 'Source log reviewed', 'supporting_references': ['log:77']})
    assert response.status_code == 201, response.text
    assert response.json()['history'][0]['reviewer'] == 'Researcher'
    assert client.get(f'/assessments/occasions/{identity}').json()['visit_id'] is None
    assert client.get(f'/assessments/occasions/{identity}').json()['phase'] is None
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    import pytest
    with Session(engine) as db:
        with pytest.raises(IntegrityError):
            db.execute(text('UPDATE assessment_occasion_classification SET phase=\'guessed\''))


def test_optional_source_binds_predeclared_attempt_without_redeclaring_purpose(client, engine):
    from app.physiology_models import PolarCaptureRecord
    from app.purpose_service import declare_acquisition, provenance_view
    from sqlmodel import Session
    _enroll(client)
    a = attempt(client, occasion(client, 'physiology', collection_group_id='collection-A'))
    with Session(engine) as db:
        source = PolarCaptureRecord(id='capture-A', participant_id='P01', matb_session_kind='generic', matb_session_id='generic-A', device_alias='H10', lifecycle='prepared', execution_purpose='study', requested_settings_json='{}', controller_lease_hash='secret-hash')
        identity = declare_acquisition(db, source, purpose='study', attempt_id=a['id'])
        db.commit()
        assert identity == a['purpose_provenance_id']
        assert len(provenance_view(db, identity)['history']) == 1
    linked = client.get('/assessments/sources/polar_capture/capture-A').json()
    assert linked['id'] == a['id']
    assert linked['receipt']['raw_saving'] == 'none'


def test_migrated_unknown_screen_cannot_be_repeated_as_new_study_without_assignment(client, engine):
    from app.assessment_models import AssessmentOccasion, AssessmentAttempt
    from sqlmodel import Session
    _enroll(client)
    with Session(engine) as db:
        old = AssessmentOccasion(participant_id='P01', instrument='screen', origin='legacy')
        db.add(old); db.flush()
        a = AssessmentAttempt(occasion_id=old.id, ordinal=1, execution_purpose='study', acquisition_state='unknown')
        db.add(a); db.commit(); db.refresh(a); identity = a.id
    response = client.post(f'/assessments/attempts/{identity}/repeat', json={'execution_purpose': 'study', 'reason': 'repeat requested'})
    assert response.status_code == 422
