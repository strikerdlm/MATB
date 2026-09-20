"""Offline, language-stratified semantic benchmark. No inference or network I/O."""
from collections import Counter, defaultdict
import math
import random
import re
from itertools import combinations
from .contracts import sha256

VERSION = '1.0.0'
BINARY = ('present', 'not_explicit')
CHOICES = ('expected_active', 'expected_inactive', 'conflicting', 'not_stated')
REFERENCE = {'present', 'explicit_absence', 'unmentioned', 'insufficient_evidence'}
QUESTIONS = ('reported_task_tradeoff', 'automation_belief', 'reported_instruction_difficulty')


def lexical_baseline(text, language):
    """Frozen deliberately simple comparator; uncertainty/negation cause abstention."""
    if language not in {'en', 'es'} or not isinstance(text, str) or len(text)>8000:
        raise ValueError('baseline input')
    text=text.casefold().replace('\u2019', "'")
    text=re.sub(r"n['’]t\b", ' not', text)
    out=dict(reported_task_tradeoff='unmentioned', automation_belief='not_stated',
        reported_instruction_difficulty='unmentioned')
    if re.search(r'\b(no|not|never|nunca|sin|tampoco|uncertain|unsure|recuerdo)\b',text):
        return out|{'reported_task_tradeoff':'insufficient_evidence','reported_instruction_difficulty':'insufficient_evidence'}
    if re.search(r'neglect|postpon|pospus|descuid|prioriti|prioric',text):
        out['reported_task_tradeoff']='present'
    if re.search(r'misunderstood|confus|incomprens',text):
        out['reported_instruction_difficulty']='present'
    active=bool(re.search(r'expected.*\bon\b|thought.*\bon\b|esperaba.*\bactiv[oa]\b',text))
    inactive=bool(re.search(r'expected.*\boff\b|thought.*\boff\b|esperaba.*\binactiv[oa]\b',text))
    out['automation_belief']='conflicting' if active and inactive else 'expected_active' if active else 'expected_inactive' if inactive else 'not_stated'
    return out


def normalize(label, question):
    if question=='automation_belief' or label in {'present','insufficient_evidence'}:
        return label
    return 'not_explicit'


def validate(rows):
    if not rows or len(rows)>10000:
        raise ValueError('benchmark row bounds')
    seen=set(); partitions={}; references={}; methods=defaultdict(set)
    required={'case_id','cluster_id','language','split','question_id','reference','rater_a','rater_b',
        'method','prediction','probabilities','annotation_seconds','correction_seconds','corrected','blinded'}
    for row in rows:
        if set(row)!=required or any(not isinstance(row[k],str) or not row[k].strip() or len(row[k])>200
                for k in ('case_id','cluster_id','method')):
            raise ValueError('benchmark schema')
        if row['language'] not in {'en','es'} or row['split'] not in {'development','test'} or row['question_id'] not in QUESTIONS:
            raise ValueError('benchmark arm')
        if row['blinded'] is not True or type(row['corrected']) is not bool:
            raise ValueError('independent reference required')
        cluster=row['cluster_id']
        if cluster in partitions and partitions[cluster]!=row['split']:
            raise ValueError('cluster partition leakage')
        partitions[cluster]=row['split']
        classes=CHOICES if row['question_id']=='automation_belief' else BINARY
        labels=set(CHOICES)|{'insufficient_evidence'} if row['question_id']=='automation_belief' else REFERENCE
        if any(row[k] not in labels for k in ('reference','rater_a','rater_b')) or row['prediction'] not in labels|set(classes):
            raise ValueError('unknown label')
        for key in ('annotation_seconds','correction_seconds'):
            n=row[key]
            if n is not None and (type(n) not in (int,float) or not math.isfinite(n) or n<0):
                raise ValueError('invalid duration')
        key=(row['case_id'],row['question_id'])
        reference=tuple(row[k] for k in ('cluster_id','language','split','reference','rater_a','rater_b'))
        if key in references and references[key]!=reference:
            raise ValueError('inconsistent paired reference')
        references[key]=reference
        identity=(*key,row['method'])
        if identity in seen: raise ValueError('duplicate measurement')
        seen.add(identity)
        methods[(row['language'],row['question_id'],row['method'])].add(row['case_id'])
        p=row['probabilities']
        if p is not None:
            if not isinstance(p,dict) or set(p)!=set(classes) or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1 for x in p.values()) or abs(sum(p.values())-1)>1e-6:
                raise ValueError('invalid distribution')
            selected=normalize(row['prediction'],row['question_id'])
            if selected in p and p[selected]<max(p.values()):
                raise ValueError('prediction distribution mismatch')
    # Comparators must evaluate the same cases within each language/question arm.
    paired={}
    for (language,question,_method),cases in methods.items():
        key=(language,question)
        if key in paired and paired[key]!=cases: raise ValueError('unpaired comparator cases')
        paired[key]=cases


def agreement(rows):
    count=len(rows)
    a=Counter(r['rater_a'] for r in rows);b=Counter(r['rater_b'] for r in rows)
    observed=sum(r['rater_a']==r['rater_b'] for r in rows)/count
    expected=sum(a[k]*b[k] for k in set(a)|set(b))/count**2
    return {'observed':observed,'kappa':(observed-expected)/(1-expected) if expected<1 else None}


def metrics(rows, question):
    classes=CHOICES if question=='automation_belief' else BINARY
    eligible=[r for r in rows if r['reference']!='insufficient_evidence']
    counts=Counter((normalize(r['reference'],question),normalize(r['prediction'],question)) for r in eligible)
    scores=[];recall={}
    for label in classes:
        tp=counts[label,label]
        actual=sum(n for (a,_),n in counts.items() if a==label)
        predicted=sum(n for (_,b),n in counts.items() if b==label)
        recall[label]=tp/actual if actual else None
        if actual+predicted: scores.append(2*tp/(actual+predicted))
    abstentions=sum(r['prediction']=='insufficient_evidence' for r in eligible)
    calibrated=[r for r in eligible if r['probabilities'] is not None and r['prediction']!='insufficient_evidence']
    brier=[];loss=[];bins=[[] for _ in range(10)]
    for r in calibrated:
        p=r['probabilities'];label=normalize(r['reference'],question)
        brier.append(sum((p[c]-(c==label))**2 for c in classes))
        loss.append(-math.log(max(p[label],1e-15)))
        confidence=max(p.values());correct=normalize(r['prediction'],question)==label
        bins[min(9,int(confidence*10))].append((confidence,correct))
    calibration=[{'lower':i/10,'upper':(i+1)/10,'count':len(bucket),
        'mean_confidence':sum(x[0] for x in bucket)/len(bucket) if bucket else None,
        'accuracy':sum(x[1] for x in bucket)/len(bucket) if bucket else None} for i,bucket in enumerate(bins)]
    return {'macro_f1':sum(scores)/len(scores) if scores else None,'class_recall':recall,
        'confusion':{a:{b:counts[a,b] for b in (*classes,'insufficient_evidence')} for a in classes},
        'reference_counts':dict(Counter(r['reference'] for r in rows)),
        'eligible_count':len(eligible),'abstentions':abstentions,'coverage':(len(eligible)-abstentions)/len(eligible) if eligible else None,
        'calibrated_count':len(calibrated),'brier':sum(brier)/len(brier) if brier else None,
        'log_loss':sum(loss)/len(loss) if loss else None,'calibration':calibration}


def evaluate(rows, *, bootstrap=1000, seed=19):
    validate(rows)
    if type(bootstrap) is not int or not 100<=bootstrap<=5000 or type(seed) is not int:
        raise ValueError('bootstrap configuration')
    groups=defaultdict(list)
    for r in rows:
        if r['split']=='test':groups[(r['language'],r['question_id'],r['method'])].append(r)
    if not groups:raise ValueError('held-out test data required')
    arms=[];replicates={}
    def interval95(values, cluster_count):
        selected=sorted(v for v in values if v is not None)
        return [selected[int((len(selected)-1)*q)] for q in (0.025,0.975)] if selected and cluster_count>=2 else None
    for (language,question,method),data in sorted(groups.items()):
        result=metrics(data,question)
        clusters=defaultdict(list)
        for r in data:clusters[r['cluster_id']].append(r)
        rng=random.Random(seed);keys=sorted(clusters);estimates=[]
        uncertainty=defaultdict(list)
        for _ in range(bootstrap):
            sampled=[r for k in rng.choices(keys,k=len(keys)) for r in clusters[k]]
            measured=metrics(sampled,question)
            estimates.append(measured['macro_f1'])
            for name in ('macro_f1','coverage','brier','log_loss'):
                uncertainty[name].append(measured[name])
            uncertainty['kappa'].append(agreement(sampled)['kappa'])
            for name in ('annotation_seconds','correction_seconds'):
                measured_times=[r[name] for r in sampled if r[name] is not None]
                uncertainty['mean_'+name].append(sum(measured_times)/len(measured_times) if measured_times else None)
        replicates[(language,question,method)]=estimates
        interval=interval95(estimates,len(keys))
        times={}
        for field in ('annotation_seconds','correction_seconds'):
            observed=[r[field] for r in data if r[field] is not None]
            times['mean_'+field]=sum(observed)/len(observed) if observed else None
            times[field+'_count']=len(observed)
        arms.append(result|times|{'language':language,'question_id':question,'method':method,
            'cluster_count':len(keys),'case_count':len(data),'macro_f1_ci95':interval,
            'agreement':agreement(data),'correction_fraction':sum(r['corrected'] for r in data)/len(data),
            'intervals95':{name:interval95(values,len(keys)) for name,values in uncertainty.items()}})
    comparisons=[]
    for a,b in combinations(arms,2):
        if (a['language'],a['question_id'])!=(b['language'],b['question_id']):continue
        key=(a['language'],a['question_id'])
        delta=[y-x if x is not None and y is not None else None for x,y in zip(
            replicates[(*key,a['method'])],replicates[(*key,b['method'])])]
        comparisons.append({'language':key[0],'question_id':key[1],'method_a':a['method'],'method_b':b['method'],
            'delta_macro_f1':b['macro_f1']-a['macro_f1'] if a['macro_f1'] is not None and b['macro_f1'] is not None else None,
            'delta_macro_f1_ci95':interval95(delta,a['cluster_count'])})
    return {'schema_version':VERSION,'input_hash':sha256(rows),'bootstrap_replicates':bootstrap,
        'seed':seed,'interval_method':'participant-cluster percentile bootstrap',
        'brier_definition':'sum of squared class errors (binary range 0 to 2)',
        'claim':'descriptive semantic coding only; synthetic data cannot validate humans','arms':arms,'comparisons':comparisons}
