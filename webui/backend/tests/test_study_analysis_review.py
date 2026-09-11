"""Reviewed historical associations and independently rebuilt HCF observations."""
import importlib.util
import io
import json
import zipfile
import pytest
from sqlmodel import Session
from app import study_analysis
from app.hcf_derivations import canonical, fingerprint
from app.models import ScreenResult, Visit, Participant
from app.assessment_adapters import attach_source
from app.assessment_models import AssessmentOccasion, AssessmentOccasionClassification
from app.purpose_service import classify_retrospectively
from app.study_bindings import browser_binding
from app.study_registry import create_draft, rehearse, freeze
from tests.test_screen_endpoint import _payload
from tests.test_study_registry import authored, seed
from matb_integration.screen.scoring import score_screen


def historical_screen_plan(db, selection='first_finished', hcf=True):
    payload = json.loads(authored(db).payload_json)
    payload['study']['enabled_instruments'] = ['screen']
    for index, occasion in enumerate(payload['study']['occasions']):
        occasion.update(instrument='screen', config=browser_binding('screen'), phase='pre',
                        visit_ordinal=1 if index < 2 else 2, order=index + 1 if index < 2 else 1)
    payload['analysis']['unit'] = 'visit'
    payload['analysis']['rules']['historical_unknowns'] = 'reviewed_classification_required'
    payload['analysis']['outcomes'] = [dict(key='hcf', metric='screen.hcf', units='F/F0',
        occasion_keys=['pre', 'post', 'recovery'], summary='mean')]
    payload['analysis']['eligibility_policy'].update(
        incomplete_denominator='finished', hcf_enabled=True, hcf_screen_keys=['pre', 'post'],
        hcf_attempt_selection=selection, configuration_pooling='explicit_review',
        pooling_review='Retain unknown historical configuration',
        pooling_attestation=dict(actor='Dr Historian', rationale='Retrospective descriptive fixture only', reference='review:historical'))
    if not hcf:
        payload['analysis']['eligibility_policy'].update(
            hcf_enabled=False, hcf_screen_keys=[], configuration_pooling='identical_only',
            pooling_review=None, pooling_attestation=None)
        payload['analysis']['outcomes'] = [
            dict(key='before', metric='screen.simple_rt', units='ms', occasion_keys=['pre'], summary='individual'),
            dict(key='after', metric='screen.simple_rt', units='ms', occasion_keys=['post', 'recovery'], summary='mean'),
            dict(key='pooled', metric='screen.simple_rt', units='ms', occasion_keys=['pre', 'post'], summary='mean'),
        ]
        payload['analysis']['contrasts'] = [dict(key='change', left_outcome='after', right_outcome='before', operation='difference')]
    draft = create_draft(db, payload)
    rehearsal = rehearse(db, draft.id)
    return freeze(db, draft.id, dict(actor='Dr Historian', reason='Retrospective analysis',
        sha256=draft.sha256, rehearsal_id=rehearsal.id))


def historical_screen(db, simple, participant="R01"):
    raw = _payload(simple=simple)
    source = ScreenResult(participant_id=participant, administered_at=raw['administered_at'],
        screen_version=2, raw_trials_json=canonical(raw), scores_json=canonical(score_screen(raw)))
    db.add(source)
    db.flush()
    attempt = attach_source(db, 'screenresult', source.model_dump(mode='json'), historical=True)
    attempt.acquisition_state = 'finished'
    db.add(attempt)
    db.flush()
    classify_retrospectively(db, attempt.purpose_provenance_id, purpose='study',
        reviewer='Dr Historian', reason='Reviewed originally unknown intent')
    return attempt


def classify(db, attempt, version, visit_id, order):
    row = AssessmentOccasionClassification(occasion_id=attempt.occasion_id, visit_id=visit_id,
        phase='pre', order=order, condition='baseline', version_ref=version.id,
        reviewer='Dr Historian', reason='Retrospective association; original context remains unknown')
    db.add(row)
    db.flush()
    return row


def reference_peers(db, version):
    from datetime import date
    attempts = []
    for participant, simple in [('R02', 400), ('R03', 600)]:
        db.add(Participant(id=participant, enrollment_date=date(2026, 9, 10)))
        db.flush()
        visit = Visit(participant_id=participant, visit_ordinal=1, scheduled_day=0)
        db.add(visit)
        db.flush()
        attempt = historical_screen(db, simple, participant)
        classify(db, attempt, version, visit.id, 1)
        attempts.append(attempt)
    return attempts


@pytest.mark.parametrize('selection,expected_index', [('first_finished', 0), ('latest_finished', 1)])
def test_historical_resolved_visits_and_hcf_order_preserve_originals(engine, selection, expected_index):
    with Session(engine) as db:
        seed(db)
        second_visit = Visit(participant_id='R01', visit_ordinal=2, scheduled_day=8)
        db.add(second_visit)
        db.flush()
        version = historical_screen_plan(db, selection)
        # UUID lexical order deliberately opposes reviewed occasion order.
        attempts = sorted([historical_screen(db, 200), historical_screen(db, 500)], key=lambda a: a.id, reverse=True)
        for index, attempt in enumerate(attempts):
            classify(db, attempt, version, 1, index + 1)
        corrected = historical_screen(db, 350)
        classify(db, corrected, version, 1, 1)
        correction = classify(db, corrected, version, second_visit.id, 1)
        all_attempts = [*attempts, corrected]
        peers = reference_peers(db, version)
        originals = {a.occasion_id: db.get(AssessmentOccasion, a.occasion_id).model_dump(mode='json') for a in all_attempts}
        request = dict(version_id=version.id, attempts={a.occasion_id: a.id for a in [*all_attempts, *peers]},
                       actor='Dr Historian', reason='Visit and prespecified-order regression')
        execution = study_analysis.execute(db, request)
        snapshot = json.loads(execution.snapshot_json)
        rows = {r['attempt_id']: r for r in snapshot['rows']}
        assert rows[attempts[0].id]['visit_id'] == 1
        assert rows[corrected.id]['visit_id'] == second_visit.id
        assert rows[corrected.id]['resolved_association']['classification_id'] == correction.id
        assert [rows[a.id]['resolved_association']['order'] for a in attempts] == [1, 2]
        assert snapshot['hcf']['snapshot']['references'][0]['attempt_id'] == attempts[expected_index].id
        assert {key for key in json.loads(execution.result_json)['outcomes']['hcf']['values'] if key.startswith('R01:')} == {'R01:1', f'R01:{second_visit.id}'}
        for attempt in all_attempts:
            assert rows[attempt.id]['occasion'] == originals[attempt.occasion_id]
            assert rows[attempt.id]['occasion']['visit_id'] is None
            assert rows[attempt.id]['occasion']['order'] is None
            assert db.get(AssessmentOccasion, attempt.occasion_id).model_dump(mode='json') == originals[attempt.occasion_id]
        assert len(rows[corrected.id]['classification_history']) == 2


def test_exported_hcf_rebuilds_observations_despite_consistent_container_hashes(engine, tmp_path):
    from app.routers.study_analysis import export
    from app.study_analysis_rules import aggregate, render_figure
    with Session(engine) as db:
        seed(db)
        version = historical_screen_plan(db)
        attempt = historical_screen(db, 250)
        classify(db, attempt, version, 1, 1)
        peers = reference_peers(db, version)
        execution = study_analysis.execute(db, dict(version_id=version.id, attempts={a.occasion_id: a.id for a in [attempt, *peers]},
            actor='Dr Historian', reason='Raw HCF replay regression'))
        db.commit()
        root = tmp_path / 'hcf-bundle'
        original_export = export(execution.id, db).body
        (tmp_path / 'original-export.zip').write_bytes(original_export)
        with zipfile.ZipFile(io.BytesIO(original_export)) as archive:
            archive.extractall(root)
    spec = importlib.util.spec_from_file_location('hcf_offline_verify', root / 'verify.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    proof = verifier.verify(root)
    assert proof['status'] == 'reproduced'
    (tmp_path / 'original-replay-proof.json').write_text(canonical(proof))
    source = json.loads((root / 'input.json').read_text())
    original_hcf = canonical(source['hcf'])
    source['rows'][0]['values']['hcf'] += 0.2
    result = aggregate(source['plan'], source['rows'], source['plan']['eligibility_policy']['missing_handling'])
    result['figure'] = render_figure(result)
    execution = json.loads((root / 'execution.json').read_text())
    execution['data_sha256'] = fingerprint(source)
    replacements = {'input.json': canonical(source), 'result.json': canonical(result),
                    'execution.json': canonical(execution), 'figure.svg': result['figure']}
    checks = json.loads((root / 'checksums.json').read_text())
    import hashlib
    for name, data in replacements.items():
        (root / name).write_text(data)
        checks[name] = hashlib.sha256(data.encode()).hexdigest()
    (root / 'checksums.json').write_text(canonical(checks))
    assert canonical(source['hcf']) == original_hcf
    with pytest.raises(ValueError, match='observation'):
        verifier.verify(root)


def test_replay_preserves_pooling_purpose_and_contrast_exclusions(engine, tmp_path):
    from app.routers.study_analysis import export
    with Session(engine) as db:
        seed(db)
        second_visit = Visit(participant_id='R01', visit_ordinal=2, scheduled_day=8)
        db.add(second_visit)
        db.flush()
        version = historical_screen_plan(db, hcf=False)
        before, after, excluded = [historical_screen(db, value) for value in (200, 400, 700)]
        classify(db, before, version, 1, 1)
        classify(db, after, version, 1, 2)
        classify(db, excluded, version, second_visit.id, 1)
        classify_retrospectively(db, excluded.purpose_provenance_id, purpose='practice',
            reviewer='Dr Historian', reason='Corrected purpose; retain original history')
        execution = study_analysis.execute(db, dict(version_id=version.id,
            attempts={a.occasion_id: a.id for a in [before, after, excluded]},
            actor='Dr Historian', reason='Frozen exclusions remain excluded'))
        db.commit()
        result = json.loads(execution.result_json)
        assert result['outcomes']['pooled']['values'] == {}
        assert result['outcomes']['after']['values'] == {'R01:1': 400}
        assert result['outcomes']['after']['denominator'] == 2
        assert result['contrasts']['change']['observed'] == 0
        assert result['contrasts']['change']['missing'] == ['R01:1', f'R01:{second_visit.id}']
        root = tmp_path / 'excluded-bundle'
        original_export = export(execution.id, db).body
        (tmp_path / 'original-export.zip').write_bytes(original_export)
        with zipfile.ZipFile(io.BytesIO(original_export)) as archive:
            archive.extractall(root)
    spec = importlib.util.spec_from_file_location('excluded_offline_verify', root / 'verify.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    proof = verifier.verify(root)
    assert proof['status'] == 'reproduced'
    (tmp_path / 'original-replay-proof.json').write_text(canonical(proof))
