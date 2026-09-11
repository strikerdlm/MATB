"""Append-only exploratory HCF with explicit, one-per-participant reference screens."""
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from app.study_analysis_models import HcfDerivation


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def fingerprint(value): return hashlib.sha256(canonical(value).encode()).hexdigest()


def derive(db, references, *, plan_id=None):
    from matb_integration.screen import hcf_mapping
    if len({r['participant_id'] for r in references}) != len(references):
        raise ValueError('HCF requires exactly one designated screen attempt per participant.')
    references = sorted(references, key=lambda r: r['participant_id'])
    store = hcf_mapping.compute_cohort_hcf({r['participant_id']:r['scores'] for r in references})
    snapshot = dict(schema_version='hcf-derivation-v1', status='exploratory', plan_id=plan_id,
        reference_cohort='identified' if all(r.get('attempt_id') for r in references) else 'legacy_sources_only',
        references=references, cohort_sha256=fingerprint(references),
        mapping=dict(screen_version=hcf_mapping.SCREEN_VERSION, k=hcf_mapping.K, clamp=list(hcf_mapping.CLAMP),
            minimum_cohort=hcf_mapping.MIN_COHORT, minimum_metric_n=hcf_mapping.MIN_METRIC_N,
            implementation_sha256=hashlib.sha256(Path(hcf_mapping.__file__).read_bytes()).hexdigest()),
        values={pid:asdict(value) for pid,value in sorted(store.items())})
    identity = fingerprint(snapshot)
    if db.get(HcfDerivation, identity) is None:
        db.add(HcfDerivation(id=identity, snapshot_json=canonical(snapshot))); db.flush()
    return db.get(HcfDerivation, identity)


def screen_reference(row):
    return dict(participant_id=row.participant_id, screen_id=str(row.id), attempt_id=row.attempt_id,
        purpose_provenance_id=row.purpose_provenance_id, raw_sha256=hashlib.sha256(row.raw_trials_json.encode()).hexdigest(),
        scoring_sha256=hashlib.sha256(row.scores_json.encode()).hexdigest(), scores=json.loads(row.scores_json))
