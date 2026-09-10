"""Bounded executable selectors and units; generic historical labels are not executable."""
CATALOG = {
    'pvt.median_rt_ms': ('pvt', 'ms'), 'pvt.lapses': ('pvt', 'count'), 'pvt.kss': ('pvt', '1-9'),
    'screen.simple_rt': ('screen', 'ms'), 'screen.hcf': ('screen', 'F/F0'),
    'questionnaire.rtlx_mean_0_100': ('questionnaire', '0-100'), 'questionnaire.bedford': ('questionnaire', '1-10'),
    'openmatb.sysmon_hit_rate': ('openmatb', 'proportion'), 'openmatb.track_rmse_deviation': ('openmatb', 'normalized_cursor_distance'),
    'liftoff.primary.median_lap_time_s': ('liftoff', 's'), 'liftoff.primary.valid_laps': ('liftoff', 'count'),
    'suas.contacts.correct_fraction': ('suas', 'proportion'), 'suas.coverage.percent': ('suas', 'percent'),
    'physiology.mean_hr_bpm': ('physiology', 'bpm'),
}


def issues(study, plan):
    result=[]
    def add(path, message): result.append(dict(path=path,message=message))
    keys={o.key:o for o in study.occasions}
    for i,o in enumerate(plan.outcomes):
        entry=CATALOG.get(o.metric)
        if entry is None: add(f'analysis.outcomes.{i}.metric','Choose an exact supported descriptive metric; generic historical outcomes cannot execute.')
        elif o.units != entry[1]: add(f'analysis.outcomes.{i}.units',f'Freeze the declared instrument unit: {entry[1]}')
        elif any(k in keys and keys[k].instrument != entry[0] for k in o.occasion_keys): add(f'analysis.outcomes.{i}.metric','Metric does not match every designated instrument.')
        if o.metric=='screen.hcf' and (not plan.eligibility_policy or not plan.eligibility_policy.hcf_enabled): add(f'analysis.outcomes.{i}.metric','HCF outcome requires enabled, designated screen reference policy.')
        if entry and entry[0]=='suas':
            if not o.source_keys or o.source_summary not in ('mean','median','individual'): add(f'analysis.outcomes.{i}.source_keys','Prespecify exact mission block keys and within-session aggregation.')
            elif len(o.source_keys)>1 and o.source_summary=='individual': add(f'analysis.outcomes.{i}.source_summary','Multiple mission blocks require a declared mean or median.')
        elif entry and entry[0]=='physiology':
            if len(o.source_keys)!=1: add(f'analysis.outcomes.{i}.source_keys','Prespecify one exact phase marker label; its existing 300-second window and validity rules apply.')
        elif o.source_keys: add(f'analysis.outcomes.{i}.source_keys','This instrument does not accept block/phase selectors.')
        if len(o.source_keys)!=len(set(o.source_keys)): add(f'analysis.outcomes.{i}.source_keys','Source keys must be unique.')
        if plan.unit != 'attempt' and o.summary=='individual' and len(o.occasion_keys)>1:
            add(f'analysis.outcomes.{i}.summary','Multiple occasions per unit require a declared mean or median.')
    for i,c in enumerate(plan.contrasts):
        outcomes={o.key:o for o in plan.outcomes}
        left,right=outcomes.get(c.left_outcome),outcomes.get(c.right_outcome)
        if left and right and left.units!=right.units: add(f'analysis.contrasts.{i}','Differences require identical units.')
    return result
