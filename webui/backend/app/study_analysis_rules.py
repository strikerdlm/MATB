"""Pure descriptive selection and reporting; no inferential engine imports."""
from statistics import fmean, median


def named(actor):
    return bool(actor and actor.strip() and not actor.startswith(('system:', 'local:')))


def purpose_criterion(provenance, retrospective_allowed):
    history = (provenance or {}).get('history', [])
    current = (provenance or {}).get('current') or {}
    initial = history[0] if history else {}
    prospective = initial.get('classification') == 'explicit' and initial.get('purpose') == 'study'
    historical = (initial.get('classification') == 'unknown' and retrospective_allowed
                  and current.get('classification') == 'retrospective' and named(current.get('actor'))
                  and bool(current.get('reason')))
    return dict(passed=current.get('purpose') == 'study' and (prospective or historical),
                prospective_declaration=prospective, historical_inclusion=bool(historical), evidence=provenance,
                reason='Requires original study declaration, or genuine historical unknown with named review and plan permission.')


def select_attempt(attempts, selection, explicit):
    ordered = sorted(attempts, key=lambda a: (a['ordinal'], a['id']))
    if selection == 'explicit':
        if explicit is None: return None
        chosen = next((a for a in ordered if a['id'] == explicit), None)
        if chosen is None: raise ValueError('Explicit attempt is outside the designated occasion.')
        return chosen
    if explicit is not None: raise ValueError('Explicit selection cannot override frozen first/latest policy.')
    finished = [a for a in ordered if a['acquisition_state'] == 'finished']
    return (finished[0] if selection == 'first_finished' else finished[-1]) if finished else None


def compare_configurations(configs, policy, review):
    def unknown(value):
        if value is None: return True
        if isinstance(value, dict): return not value or any(unknown(v) for v in value.values())
        if isinstance(value, list): return any(unknown(v) for v in value)
        return False
    complete = bool(configs) and not any(unknown(c) for c in configs)
    identical = complete and all(c == configs[0] for c in configs)
    reviewed = (policy == 'explicit_review' and isinstance(review, dict) and named(review.get('actor'))
                and bool(review.get('rationale', '').strip()) and bool(review.get('reference', '').strip()))
    return dict(passed=bool(identical or reviewed), identical=identical, known=complete,
                configurations=configs, review=review, equivalence_claim=False,
                reason='Identity comparison only; no psychometric or perceptual equivalence established.')


def aggregate(plan, rows, missing_handling):
    def unit(row):
        if plan['unit'] == 'participant': return row['participant_id']
        if plan['unit'] == 'visit': return f"{row['participant_id']}:{row['visit_id']}"
        return row['attempt_id'] or f"missing:{row.get('occasion_id', row['occasion_key'])}:{row['participant_id']}"
    outcomes = {}
    units_by_outcome = {}
    for spec in plan['outcomes']:
        relevant = [r for r in rows if r['occasion_key'] in spec['occasion_keys'] and r['denominator']]
        units = sorted({unit(r) for r in relevant})
        units_by_outcome[spec['key']] = units
        values = {}
        for key in units:
            observations = [r['values'][spec['key']] for r in relevant if unit(r) == key and spec['key'] in r['values']]
            if not observations: continue
            if spec['summary'] == 'individual':
                # One raw value per declared analysis unit; never silently choose a repeat/occasion.
                if len(observations) != 1: raise ValueError('Individual summary requires exactly one observation per analysis unit.')
                value = observations[0]
            else: value = fmean(observations) if spec['summary'] == 'mean' else median(observations)
            values[key] = value
        outcomes[spec['key']] = dict(values=values, denominator=len(units), observed=len(values), missing=sorted(set(units)-values.keys()), units=spec.get('units'))
    if missing_handling == 'complete_case':
        complete = set.intersection(*(set(o['values']) for o in outcomes.values())) if outcomes else set()
        for spec in plan['outcomes']:
            for row in rows:
                if row['denominator'] and row['occasion_key'] in spec['occasion_keys'] and spec['key'] not in row['values']:
                    complete.discard(unit(row))
        for key, outcome in outcomes.items():
            outcome['values'] = {k:v for k,v in outcome['values'].items() if k in complete}
            outcome['observed'] = len(outcome['values'])
            outcome['missing'] = sorted(set(units_by_outcome[key])-outcome['values'].keys())
    contrasts = {}
    for spec in plan['contrasts']:
        left, right = outcomes[spec['left_outcome']], outcomes[spec['right_outcome']]
        common = left['values'].keys() & right['values'].keys()
        denominator = set(units_by_outcome[spec['left_outcome']]) | set(units_by_outcome[spec['right_outcome']])
        contrasts[spec['key']] = dict(values={k:left['values'][k]-right['values'][k] for k in sorted(common)},
            denominator=len(denominator), observed=len(common), missing=sorted(denominator-common), units=left['units'])
    return dict(outcomes=outcomes, contrasts=contrasts, automatic_model=None, inferential_tests=[])


def analysis_unit(plan, row):
    if plan['unit']=='participant': return row['participant_id']
    if plan['unit']=='visit': return f"{row['participant_id']}:{row['visit_id']}"
    return row['attempt_id'] or 'missing:'+row['occasion_id']


def pooling_groups(plan, rows, policy, *, contrast=False):
    """Only observations actually combined within one unit/instrument require pooling."""
    groups={}
    for row in rows:
        key=analysis_unit(plan,row)+(':'+row['instrument'] if contrast else '')
        groups.setdefault(key,[]).append(row)
    reports={}
    for key,group in sorted(groups.items()):
        report=compare_configurations([r['configuration'] for r in group],policy['configuration_pooling'],policy.get('pooling_attestation'))
        report['pooling_required']=len(group)>1
        if len(group)<=1:
            report['passed']=True
            report['reason']='A single observation is not pooled; unknown configuration remains unknown and is not an equality claim.'
        report['occasion_ids']=[r['occasion_id'] for r in group]
        reports[key]=report
    return dict(passed=all(r['passed'] for r in reports.values()),groups=reports,scope='declared_analysis_unit_and_instrument' if contrast else 'declared_analysis_unit',equivalence_claim=False)


def render_figure(result):
    from html import escape
    lines=[]
    for key,item in result['outcomes'].items():
        lines.append(f'{key}: {item["observed"]}/{item["denominator"]} observed ({item.get("units") or "unspecified"})')
        for unit,value in item['values'].items(): lines.append(f'  {unit}: {value:.6g}')
    height=60+22*len(lines)
    return '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="'+str(height)+'" viewBox="0 0 900 '+str(height)+'"><rect width="100%" height="100%" fill="white"/><g fill="black" font-family="monospace" font-size="14"><text x="20" y="25">Frozen descriptive observations; no inferential fit</text>'+''.join(f'<text x="20" y="{50+i*22}">{escape(line)}</text>' for i,line in enumerate(lines))+'</g></svg>'
