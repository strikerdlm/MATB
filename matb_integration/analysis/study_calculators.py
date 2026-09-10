"""Raw-input descriptive adapters. Optional imports execute only for selected instruments."""
import base64
import io
import json
from statistics import fmean, median


def calculate(source, outcome):
    instrument=source['instrument']; raw=source['raw']; metric=outcome['metric']
    if instrument=='pvt':
        from matb_integration.pvt_scoring import PvtAssessmentIn, _metrics
        body=PvtAssessmentIn.model_validate(raw)
        metrics=_metrics(body.trials,duration_ms=body.duration_ms)
        return dict(value=body.kss_score if metric=='pvt.kss' else metrics[metric.split('.',1)[1]],
                    protocol_valid=not body.validity_reasons(), validity_reasons=body.validity_reasons())
    if instrument=='screen':
        from matb_integration.screen.scoring import score_screen
        scores=score_screen(raw)
        result=scores['simple_rt']
        return dict(value=result.get('median_ms') if result.get('valid') else None,protocol_valid=bool(result.get('valid')),scores=scores)
    if instrument=='questionnaire':
        return dict(value=sum(raw['nasa_tlx'].values())/6 if metric.endswith('rtlx_mean_0_100') else raw['bedford'],
                    protocol_valid=True, interpretation='Bedford translation remains exploratory, not locally validated.')
    if instrument=='openmatb':
        from matb_integration.evidence.reconcile import reconcile
        artifacts={k:base64.b64decode(v,validate=True) for k,v in raw['artifacts'].items()}
        result=reconcile(artifacts,derivation_version=raw['derivation_version'])
        selected=next(m for m in result['metrics'] if m['metric']==metric.split('.',1)[1])
        return dict(value=selected['value'],protocol_valid=result['status']=='succeeded',source_eligible=selected['confirmatory_eligible'],
                    reconciliation_fingerprint=result['fingerprint'],metric=selected)
    if instrument=='liftoff':
        from matb_integration.liftoff.metrics import VisibleResults, compute_metrics
        from matb_integration.liftoff.records import TelemetryRecord
        from matb_integration.liftoff.protocol import LiftoffPacket
        records=[]
        for record in raw['telemetry']:
            packet=LiftoffPacket(motor_count=4, **{k:tuple(v) if isinstance(v,list) else v for k,v in record.items() if k not in {'session_id','sequence','received_monotonic_ns','received_utc','schema_version'}})
            records.append(TelemetryRecord(**{k:record[k] for k in ('session_id','sequence','received_monotonic_ns','received_utc')},packet=packet))
        result=compute_metrics(records,VisibleResults(**raw['visible_results']))
        return dict(value=result['primary'][metric.split('.')[-1]],protocol_valid=source.get('protocol_valid',False),metrics=result)
    if instrument=='suas':
        from matb_integration.suas.metrics.mission import derive_block_metrics
        from matb_integration.suas.recording.records import SessionRecord
        from matb_integration.suas.recording.replay import effective_records
        from matb_integration.suas.metrics.debrief import _resequence
        blocks={}
        for stream in raw['streams'].values():
            effective=effective_records([SessionRecord(**r) for r in stream['records']])
            for key in {r.block_id for r in effective}:
                if key in blocks: raise ValueError('Ambiguous mission block across source streams.')
                blocks[key]=dict(records=[r for r in effective if r.block_id==key],manifest=stream['manifest'])
        values=[]; results={}
        for key in outcome['source_keys']:
            block=blocks[key]
            results[key]=derive_block_metrics(_resequence(block['records']),block['manifest']).to_dict()
            value=results[key]
            for part in metric.split('.')[1:]: value=value[part]
            values.append(value)
        value=None if any(v is None for v in values) else (values[0] if outcome['source_summary']=='individual' else fmean(values) if outcome['source_summary']=='mean' else median(values))
        return dict(value=value,protocol_valid=source.get('protocol_valid',False),metrics=results)
    if instrument=='physiology':
        import pyarrow.parquet as pq
        from matb_integration.physiology.analysis import analyze_rr_window
        rr=pq.read_table(io.BytesIO(base64.b64decode(raw['rr_parquet'],validate=True))).to_pydict()
        markers=sorted(raw['markers'],key=lambda m:(m['host_monotonic_ns'],m['sequence']))
        matching=[(i,m) for i,m in enumerate(markers) if m['label']==outcome['source_keys'][0]]
        if len(matching)!=1: raise ValueError('Phase marker is missing or ambiguous.')
        i,marker=matching[0]; end=marker['host_monotonic_ns']+300_000_000_000
        if i+1<len(markers): end=min(end,markers[i+1]['host_monotonic_ns'])
        indices=[j for j,t in enumerate(rr['beat_monotonic_ns']) if marker['host_monotonic_ns']<=t<end]
        metrics=analyze_rr_window([float(rr['rr_ms'][j]) for j in indices],
            continuity=[b==a+1 and rr['connection_epoch'][a]==rr['connection_epoch'][b] and not bool(rr['gap_before'][b]) for a,b in zip(indices,indices[1:])],
            external_valid=[not bool(rr['contact_supported'][j]) or rr['contact_detected'][j] is True for j in indices],minimum_duration_s=300.0,minimum_sqi=0.8)
        return dict(value=metrics.get('mean_instantaneous_hr_bpm'),protocol_valid=metrics['valid'],metrics=metrics,
                    phase_window=dict(marker=marker,end_monotonic_ns=end))
    raise ValueError('Unsupported instrument calculator.')
