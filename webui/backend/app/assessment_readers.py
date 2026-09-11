"""Compatibility readers reject ambiguous repeated observations."""
from fastapi import HTTPException


def reject_ambiguous(rows, *, key='participant_id'):
    seen = set()
    for row in rows:
        value = getattr(row, key)
        if value in seen:
            raise HTTPException(409, {'code': 'explicit_assessment_selection_required',
                                     'message': 'Select occasion/attempt IDs; repeated observations cannot be collapsed into legacy cells.'})
        seen.add(value)
    return rows


def select_one(rows, attempt_id=None):
    if attempt_id is not None:
        selected = [r for r in rows if getattr(r, 'attempt_id', None) == attempt_id]
        if not selected:
            raise HTTPException(404, 'selected attempt not found in this context')
        return selected[0]
    if len(rows) > 1:
        raise HTTPException(409, {'code': 'explicit_assessment_selection_required', 'attempt_ids': [getattr(r, 'attempt_id', None) for r in rows]})
    return rows[0] if rows else None


def exclude_known_nonstudy(db, rows):
    from .purpose_service import provenance_view
    result = []
    for row in rows:
        if row.purpose_provenance_id:
            current = provenance_view(db, row.purpose_provenance_id)['current']
            if current and current['purpose'] != 'study':
                continue
        result.append(row)
    return result


def select_source_rows(db, rows, table, attempt_id=None):
    from .assessment_models import AssessmentSourceLink
    from sqlmodel import select
    if attempt_id:
        links = db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.attempt_id == attempt_id,
            AssessmentSourceLink.source_table == table, AssessmentSourceLink.role == 'acquisition')).all()
        ids = {link.source_id for link in links}
        selected = [row for row in rows if str(row.id) in ids]
        if not selected:
            raise HTTPException(404, 'selected attempt not found in this context')
        return selected
    if len(rows) > 1:
        raise HTTPException(409, {'code': 'explicit_assessment_selection_required', 'source_ids': [str(row.id) for row in rows]})
    return rows
