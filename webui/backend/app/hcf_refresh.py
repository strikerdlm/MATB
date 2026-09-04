"""Cohort HCF store + DepdfFit refresh (spec section 4).

Calibration (g0/p0/tau0) is F-independent; only the hcf_value/hcf_source
columns change. Called on every screen ingest and used by the fit trigger."""

from __future__ import annotations

import json

from sqlmodel import Session, select

from app.models import ArchivedAssessment, DepdfFit, ScreenResult


def build_hcf_store(session: Session):
    """{participant_id: HCFEstimate} from stored screens; {} below the gate."""
    from matb_integration.screen.hcf_mapping import SCREEN_VERSION, compute_cohort_hcf

    rows = session.exec(select(ScreenResult).where(ScreenResult.execution_purpose == "study", ScreenResult.screen_version == SCREEN_VERSION)).all()
    scores = {r.participant_id: json.loads(r.scores_json) for r in rows}
    return compute_cohort_hcf(scores)


def refresh_fit_hcf(session: Session) -> int:
    """Update hcf_value/hcf_source on every DepdfFit from the current cohort
    store. Participants without a screen estimate revert to F0. Returns the
    number of rows changed."""
    from matb_integration.suhir.hcf import F0_DEFAULT

    store = build_hcf_store(session)
    changed = 0
    for fit in session.exec(select(DepdfFit)).all():
        est = store.get(fit.participant_id)
        value = est.value if est else F0_DEFAULT
        source = "screen" if est else "F0_default"
        if fit.hcf_value != value or fit.hcf_source != source:
            session.add(ArchivedAssessment(experiment_id="hcf_fit", participant_id=fit.participant_id,
                        original_id=fit.id, snapshot_json=fit.model_dump_json(),
                        reason="screen_v2_cohort_refresh"))
            fit.hcf_value, fit.hcf_source = value, source
            session.add(fit)
            changed += 1
    session.commit()
    return changed
