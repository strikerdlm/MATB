import pytest


def rows():
    return [dict(case_id=str(i),cluster_id=str(i//2),language='en',split='test',
        question_id='reported_task_tradeoff',reference=label,rater_a=label,rater_b=label,
        method='manual',prediction=label,probabilities={'present':float(label=='present'),'not_explicit':float(label!='present')},
        annotation_seconds=10.0,correction_seconds=2.0,corrected=False,blinded=True)
        for i,label in enumerate(['present','unmentioned','explicit_absence','present'])]


def test_clustered_evaluation_keeps_absence_distinction_and_languages():
    from matb_integration.inference.evaluation import evaluate
    report=evaluate(rows(),bootstrap=100,seed=19)
    arm=report['arms'][0]
    assert arm['macro_f1']==1 and arm['brier']==0 and arm['log_loss']==0
    assert arm['agreement']['kappa']==1
    assert arm['reference_counts']['unmentioned']==1
    assert arm['reference_counts']['explicit_absence']==1
    assert arm['cluster_count']==2 and arm['macro_f1_ci95']==[1,1]
    assert arm['mean_annotation_seconds']==10
    assert evaluate(rows(),bootstrap=100,seed=19)==report


def test_abstention_is_coverage_not_success():
    from matb_integration.inference.evaluation import evaluate
    data=rows();data[0]['prediction']='insufficient_evidence';data[0]['probabilities']=None
    arm=evaluate(data,bootstrap=100)['arms'][0]
    assert arm['coverage']==0.75 and arm['abstentions']==1
    assert arm['macro_f1']<1


@pytest.mark.parametrize('change',[{'split':'development'}, {'blinded':False}, {'probabilities':{'present':float('nan')}}, {'annotation_seconds':-1}])
def test_invalid_or_leaking_input_rejected(change):
    from matb_integration.inference.evaluation import evaluate
    data=rows();data[0].update(change)
    with pytest.raises(ValueError):evaluate(data,bootstrap=100)


def test_lexical_baseline_is_language_bound_and_conservative():
    from matb_integration.inference.evaluation import lexical_baseline
    assert lexical_baseline('I focused on tanks and neglected tracking.','en')['reported_task_tradeoff']=='present'
    assert lexical_baseline('No recuerdo el estado.','es')['automation_belief']=='not_stated'
    assert lexical_baseline('The display had four panels.','en')['reported_instruction_difficulty']=='unmentioned'


def test_paired_comparisons_and_missing_timing_are_explicit():
    from matb_integration.inference.evaluation import evaluate
    data=rows()
    other=[r|{'method':'assisted','annotation_seconds':None} for r in data]
    result=evaluate(data+other,bootstrap=100)
    assert result['comparisons'][0]['delta_macro_f1']==0
    assert result['comparisons'][0]['delta_macro_f1_ci95']==[0,0]
    assert result['arms'][0]['mean_annotation_seconds'] is None


@pytest.mark.parametrize('text,language,question',[
    ("I wasn't confused by the instructions.",'en','reported_instruction_difficulty'),
    ("I didn't neglect tracking.",'en','reported_task_tradeoff'),
    ('I didn’t neglect tracking.','en','reported_task_tradeoff'),
    ('Prioricé las bombas sin descuidar el seguimiento.','es','reported_task_tradeoff')])
def test_lexical_negation_abstains(text,language,question):
    from matb_integration.inference.evaluation import lexical_baseline
    assert lexical_baseline(text,language)[question]=='insufficient_evidence'
