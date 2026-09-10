"""Legacy exploratory HCF compatibility; immutable stored fits never refresh."""

from __future__ import annotations

import json

from sqlmodel import Session, select

from app.models import ScreenResult


def build_hcf_store(session: Session):
    """{participant_id: HCFEstimate} from stored screens; {} below the gate."""
    from matb_integration.screen.hcf_mapping import SCREEN_VERSION, compute_cohort_hcf

    rows = session.exec(select(ScreenResult).where(ScreenResult.execution_purpose == "study", ScreenResult.screen_version == SCREEN_VERSION)).all()
    from app.assessment_readers import reject_ambiguous, exclude_known_nonstudy
    rows = exclude_known_nonstudy(session, rows)
    reject_ambiguous(rows)
    scores = {r.participant_id: json.loads(r.scores_json) for r in rows}
    return compute_cohort_hcf(scores)


def refresh_fit_hcf(session: Session) -> int:
    """Advance only the exploratory pointer. Existing fits/figures retain their HCF."""
    from fastapi import HTTPException
    from app.assessment_readers import reject_ambiguous, exclude_known_nonstudy
    from app.hcf_derivations import derive, screen_reference
    from app.study_analysis_models import HcfExploratoryPointer
    rows = exclude_known_nonstudy(session, session.exec(select(ScreenResult).where(
        ScreenResult.execution_purpose == "study", ScreenResult.screen_version == 2)).all())
    try: reject_ambiguous(rows)
    except HTTPException as exc:
        if exc.status_code != 409: raise
        return 0
    derived = derive(session, [screen_reference(r) for r in rows])
    pointer = session.get(HcfExploratoryPointer, 'legacy-unambiguous')
    changed = pointer is None or pointer.derivation_id != derived.id
    if pointer is None: pointer = HcfExploratoryPointer(derivation_id=derived.id)
    else: pointer.derivation_id = derived.id
    session.add(pointer); session.commit()
    return int(changed)
