"""Offline recomputation of a frozen descriptive export, without database or network."""
import hashlib
import json
import sys
from pathlib import Path


def verify(root):
    root=Path(root).resolve()
    checks=json.loads((root/'checksums.json').read_text())
    for name,digest in checks.items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('Artifact checksum mismatch: '+name)
    sys.path.insert(0,str(root/'source'))
    from matb_integration.analysis.study_calculators import calculate
    from matb_integration.screen.hcf_mapping import compute_cohort_hcf
    from replay_rules import aggregate, render_figure
    source=json.loads((root/'input.json').read_text()); expected=json.loads((root/'result.json').read_text())
    def fingerprint(value):
        return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()).hexdigest()
    execution=json.loads((root/'execution.json').read_text()); selection=json.loads((root/'selection.json').read_text())
    if fingerprint(source)!=execution['data_sha256']: raise ValueError('Data fingerprint mismatch.')
    if fingerprint(source['plan'])!=execution['plan_sha256'] or fingerprint(source['plan'])!=source['version']['analysis_sha256']: raise ValueError('Plan fingerprint mismatch.')
    if fingerprint(source['study'])!=source['version']['study_sha256']: raise ValueError('Study fingerprint mismatch.')
    if fingerprint(source['implementation'])!=execution['implementation_sha256']: raise ValueError('Implementation fingerprint mismatch.')
    if fingerprint(dict(snapshot=json.loads(selection['snapshot_json']),request=json.loads(selection['request_json'])))!=selection['id'] or selection['id']!=source['frozen_input_id']: raise ValueError('Frozen selection fingerprint mismatch.')
    for name,digest in source['implementation']['files'].items():
        if checks.get(name)!=digest: raise ValueError('Pinned implementation artifact mismatch: '+name)
    import importlib.metadata
    for package,version in source['implementation']['dependencies'].items():
        if importlib.metadata.version(package)!=version: raise ValueError('Dependency version mismatch: '+package)
    outcomes={o['key']:o for o in source['plan']['outcomes']}
    for row in source['rows']:
        if row['source'] is None: continue
        for key,recorded in row['calculations'].items():
            spec=outcomes.get(key) or dict(metric='screen.simple_rt')
            actual=calculate(row['source'],spec)
            if actual!=recorded: raise ValueError('Raw calculator mismatch: '+row['attempt_id']+'/'+key)
            if key in row['values'] and actual['value']!=row['values'][key]: raise ValueError('Selected observation mismatch.')
    if source['hcf']:
        from matb_integration.screen.scoring import score_screen
        refs=source['hcf']['snapshot']['references']; rows={r['attempt_id']:r for r in source['rows']}
        recomputed={r['participant_id']:score_screen(rows[r['attempt_id']]['source']['raw']) for r in refs}
        estimates=compute_cohort_hcf(recomputed)
        from dataclasses import asdict
        if {pid:asdict(estimate) for pid,estimate in estimates.items()}!=source['hcf']['snapshot']['values']: raise ValueError('HCF recomputation mismatch.')
        if fingerprint(source['hcf']['snapshot'])!=source['hcf']['id'] or fingerprint(refs)!=source['hcf']['snapshot']['cohort_sha256']: raise ValueError('HCF identity mismatch.')
    result=aggregate(source['plan'],source['rows'],source['plan']['eligibility_policy']['missing_handling'])
    for contrast in source['plan']['contrasts']:
        item=result['contrasts'][contrast['key']]
        failed={group.rsplit(':',1)[0] for group,report in source['comparisons']['contrast:'+contrast['key']]['groups'].items() if not report['passed']}
        for unit in failed: item['values'].pop(unit,None)
        item['observed']=len(item['values'])
        if failed:
            item['excluded_configuration_units']=sorted(failed)
            item['missing']=sorted(set(item['missing'])|failed)
    result['figure']=render_figure(result)
    if result!=expected: raise ValueError('Descriptive aggregation/figure mismatch.')
    return dict(status='reproduced',raw_attempts=sum(r['source'] is not None for r in source['rows']),automatic_model=None)


if __name__=='__main__':
    print(json.dumps(verify(sys.argv[1] if len(sys.argv)>1 else '.')))
