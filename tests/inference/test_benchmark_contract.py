import json
from pathlib import Path


def test_synthetic_benchmark_separates_language_and_unmentioned_evidence():
    root=Path(__file__).resolve().parents[2]/'research'/'jev'
    rows=[json.loads(line) for line in (root/'synthetic_cases.jsonl').read_text(encoding='utf-8').splitlines()]
    assert {row['language'] for row in rows}=={'en','es'}
    assert all(row['source_kind']=='synthetic' for row in rows)
    assert {'negation','mixed_tasks','not_stated','contradiction','prompt_injection'} <= {row['case'] for row in rows}
    absent=next(row for row in rows if row['case']=='negation')
    unmentioned=next(row for row in rows if row['case']=='not_stated')
    assert absent['evidence_status']=='explicit_absence'
    assert unmentioned['evidence_status']=='unmentioned'
