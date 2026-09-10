"""Purpose declarations distinguish recorded values from supported intent."""
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, select

@pytest.mark.parametrize('module,name', [
    ('app.routers.pvt', 'PvtAssessmentIn'),
    ('app.openmatb_schemas', 'CreateOpenMatbSession'),
    ('app.liftoff_schemas', 'CreateLiftoffSession'),
    ('app.physiology_schemas', 'CreateCaptureRequest'),
    ('app.simulation_schemas', 'CreateSimulationSession'),
    ('app.simulation_schemas', 'CreateTechnicalSimulationSession'),
])
def test_new_contract_requires_purpose(module, name):
    from importlib import import_module
    assert getattr(import_module(module), name).model_fields['execution_purpose'].is_required()

def test_screen_http_contract_requires_purpose():
    from app.main import app
    schema = app.openapi()
    body = schema['paths']['/screen']['post']['requestBody']['content']['application/json']['schema']
    assert 'execution_purpose' in schema['components']['schemas'][body['$ref'].split('/')[-1]]['required']

def test_fast_study_rejected():
    from app.routers.pvt import PvtAssessmentIn
    with pytest.raises(ValidationError, match='fast_mode requires practice'):
        PvtAssessmentIn(participant_id='P01', visit_ordinal=1, kss_score=3,
            administered_at='now', duration_ms=100, trials=[], fast_mode=True, execution_purpose='study')

def test_historical_migration_and_immutable_history(tmp_path):
    from app.purpose_service import migrate_purpose_provenance, classify_retrospectively, provenance_view
    engine = create_engine(f'sqlite:///{tmp_path / "purpose.db"}')
    with engine.begin() as c:
        c.execute(text('CREATE TABLE screenresult (id INTEGER PRIMARY KEY, execution_purpose TEXT, raw_trials_json TEXT)'))
        c.execute(text("INSERT INTO screenresult VALUES (1, 'study', '{\"fast_mode\": true}')"))
    migrate_purpose_provenance(engine)
    with engine.connect() as c:
        identity = c.execute(text('SELECT purpose_provenance_id FROM screenresult')).scalar_one()
        assert c.execute(text('SELECT execution_purpose FROM screenresult')).scalar_one() == 'study'
    with Session(engine) as db:
        initial = provenance_view(db, identity)
        assert initial['history'][0]['classification'] == 'unknown'
        assert initial['history'][0]['purpose'] == 'study'
        assert initial['history'][1]['actor'] == 'system:migration'
        classify_retrospectively(db, identity, purpose='practice', reviewer='Dr Reviewer', reason='Training log reviewed', supporting_references=['log:1'])
        db.commit()
        before = provenance_view(db, identity)
    migrate_purpose_provenance(engine)
    with Session(engine) as db:
        assert provenance_view(db, identity) == before
    with engine.begin() as c:
        with pytest.raises(Exception, match='append-only'):
            c.execute(text('UPDATE purpose_classification SET reason=\'changed\''))
    with engine.begin() as c:
        c.execute(text('DELETE FROM screenresult'))
        c.execute(text("INSERT INTO screenresult (id, execution_purpose, raw_trials_json) VALUES (1, 'study', '{}')"))
    migrate_purpose_provenance(engine)
    with engine.connect() as c:
        assert c.execute(text('SELECT purpose_provenance_id FROM screenresult')).scalar_one() != identity
    with Session(engine) as db:
        assert provenance_view(db, identity) == before

def test_declaration_is_atomic_and_reviewer_required(tmp_path):
    from app.models import PracticeResult
    from app.purpose_service import declare_acquisition, classify_retrospectively, provenance_view
    from app.purpose_models import PurposeProvenance
    engine = create_engine(f'sqlite:///{tmp_path / "atomic.db"}')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        row = PracticeResult(experiment_id='pvt', payload_json='{}', result_json='{}')
        declare_acquisition(db, row, purpose='practice')
        identity = row.purpose_provenance_id
        assert provenance_view(db, identity)['current']['classification'] == 'explicit'
        db.rollback()
        assert db.get(PurposeProvenance, identity) is None
        assert db.exec(select(PracticeResult)).all() == []
        for reviewer, reason in [('', 'reason'), ('Reviewer', ' ')]:
            with pytest.raises(ValueError):
                classify_retrospectively(db, identity, purpose='study', reviewer=reviewer, reason=reason)

@pytest.mark.parametrize('path', ['/pvt', '/screen', '/openmatb/sessions', '/liftoff/sessions',
    '/physiology/polar-h10/v1/captures', '/simulation/sessions', '/simulation/technical-sessions'])
def test_omitted_purpose_http_rejection(client, path):
    from app.main import app
    from app.routers import openmatb, liftoff, physiology, simulation
    from tests.test_liftoff_endpoints import create_payload
    from tests.test_screen_endpoint import _payload as screen_payload
    from tests.test_pvt_endpoint import _payload as pvt_payload
    bodies = {
        '/pvt': pvt_payload(), '/screen': {'participant_id': 'P01', 'payload': screen_payload()},
        '/openmatb/sessions': {'participant_id': 'P01', 'visit_ordinal': 1},
        '/liftoff/sessions': create_payload(),
        '/physiology/polar-h10/v1/captures': {'participant_pseudonym': 'P01', 'matb_session_kind': 'generic', 'matb_session_id': 'test'},
        '/simulation/sessions': {'participant_id': 'P01', 'visit_ordinal': 1, 'scenario_id': 'reference_area_search', 'locale': 'en'},
        '/simulation/technical-sessions': {'block_id': 'LOW', 'scenario_id': 'reference_area_search', 'locale': 'en'},
    }
    body = bodies[path]
    body.pop('execution_purpose', None)
    dependencies = [openmatb.manager, liftoff.get_liftoff_manager, physiology.manager, simulation.get_simulation_manager]
    old = dict(app.dependency_overrides)
    try:
        for dependency in dependencies:
            app.dependency_overrides[dependency] = lambda: object()
        response = client.post(path, json=body)
        assert response.status_code == 422, response.text
        assert response.json()['detail']['context']['fields'] == ['body.execution_purpose']
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(old)


def test_replacement_retains_original_history_and_protected_review(client, engine):
    import json
    from app.models import ArchivedAssessment
    from tests.test_pvt_endpoint import _payload, _enroll
    _enroll(client)
    first = client.post('/pvt', json=_payload()).json()
    identity = first['purpose_provenance_id']
    original = client.get(f'/purpose-provenance/{identity}').json()
    assert original['current']['classification'] == 'explicit'
    assert client.post(f'/purpose-provenance/{identity}/classifications', json={
        'purpose': 'practice', 'reviewer': 'Reviewer', 'reason': 'log reviewed', 'classification': 'explicit'}).status_code == 422
    assert client.post(f'/purpose-provenance/{identity}/classifications', json={
        'purpose': 'practice', 'reviewer': ' ', 'reason': 'log reviewed'}).status_code == 422
    assert client.post(f'/purpose-provenance/{identity}/classifications', json={
        'purpose': 'practice', 'reviewer': 'Reviewer', 'reason': 'log reviewed'}, headers={'Origin': 'https://untrusted.example'}).status_code == 403
    reviewed = client.post(f'/purpose-provenance/{identity}/classifications', json={
        'purpose': 'practice', 'reviewer': 'Reviewer', 'reason': 'log reviewed', 'supporting_references': ['log:1']}).json()
    assert reviewed['history'][0] == original['history'][0]
    assert reviewed['current']['classification'] == 'retrospective'
    second = client.post('/pvt', json=_payload(overwrite=True, kss_score=2)).json()
    assert second['purpose_provenance_id'] != identity
    assert client.get(f'/purpose-provenance/{identity}').json() == reviewed
    with Session(engine) as db:
        archived = db.exec(select(ArchivedAssessment)).one()
        assert archived.purpose_provenance_id == identity
        assert json.loads(archived.snapshot_json)['purpose_provenance_id'] == identity


def test_screen_fast_conflict_is_rejected(client):
    from tests.test_screen_endpoint import _enroll, _payload
    _enroll(client, 'P01')
    response = client.post('/screen', json={'participant_id': 'P01',
        'execution_purpose': 'study', 'payload': {**_payload(), 'fast_mode': True}})
    assert response.status_code == 422

@pytest.mark.parametrize('name,purpose', [('CreateSimulationSession', 'practice'), ('CreateTechnicalSimulationSession', 'study')])
def test_mission_purpose_conflict(name, purpose):
    from app import simulation_schemas
    payload = dict(execution_purpose=purpose, scenario_id='reference_area_search', locale='en')
    payload.update(dict(participant_id='P01', visit_ordinal=1) if name == 'CreateSimulationSession' else dict(block_id='LOW'))
    with pytest.raises(ValidationError) as error:
        getattr(simulation_schemas, name)(**payload)
    assert [item['loc'] for item in error.value.errors()] == [('execution_purpose',)]


def test_historical_practice_and_archive_preserve_dates_and_raw_values(tmp_path):
    from app.purpose_service import migrate_purpose_provenance, provenance_view
    engine = create_engine(f'sqlite:///{tmp_path / "history.db"}')
    with engine.begin() as c:
        c.execute(text('CREATE TABLE practiceresult (id INTEGER PRIMARY KEY, execution_purpose TEXT, created_at DATETIME, payload_json TEXT)'))
        c.execute(text("INSERT INTO practiceresult VALUES (1, 'practice', '2001-01-01 00:00:00', '{}')"))
        c.execute(text('CREATE TABLE archived_assessment (id INTEGER PRIMARY KEY, snapshot_json TEXT)'))
        c.execute(text('INSERT INTO archived_assessment VALUES (1, :snapshot)'), {'snapshot': '{"execution_purpose":"practice","raw_trials_json":"original"}'})
    migrate_purpose_provenance(engine)
    migrate_purpose_provenance(engine)
    with Session(engine) as db:
        rows = db.connection().execute(text('SELECT * FROM practiceresult')).mappings().all()
        assert rows[0]['created_at'] == '2001-01-01 00:00:00'
        assert rows[0]['payload_json'] == '{}'
        practice = provenance_view(db, rows[0]['purpose_provenance_id'])
        assert len(practice['history']) == 1
        assert practice['current']['classification'] == 'unknown'
        assert practice['current']['purpose'] == 'practice'
        assert not practice['current']['recorded_at'].startswith('2001-')
        archived = db.connection().execute(text('SELECT * FROM archived_assessment')).mappings().one()
        assert archived['snapshot_json'] == '{"execution_purpose":"practice","raw_trials_json":"original"}'
        assert provenance_view(db, archived['purpose_provenance_id'])['recorded_purpose'] == 'practice'

@pytest.mark.parametrize('fast_mode', ['true', 1, {}, []])
def test_screen_non_boolean_fast_mode_cannot_skip_study_protocol(client, fast_mode):
    from tests.test_screen_endpoint import _enroll, _payload
    _enroll(client, 'P01')
    response = client.post('/screen', json={'participant_id': 'P01',
        'execution_purpose': 'study', 'payload': {**_payload(), 'fast_mode': fast_mode}})
    assert response.status_code == 422
