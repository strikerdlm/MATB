import pytest
from pydantic import ValidationError


def test_pack_has_exact_questions_and_immutable_criteria():
    from matb_integration.inference.question_packs import load_question_pack
    pack = load_question_pack('matb-debrief-v1')
    assert set(pack.questions) == {'reported_task_tradeoff', 'automation_belief', 'reported_instruction_difficulty'}
    with pytest.raises(TypeError):
        pack.questions['automation_belief']['criteria']['expected_active'] = 'changed'


@pytest.mark.parametrize('pack_id', ['../secrets', '/tmp/a.json', 'unknown'])
def test_pack_paths_are_not_browser_configuration(pack_id):
    from matb_integration.inference.question_packs import load_question_pack
    with pytest.raises(ValueError):
        load_question_pack(pack_id)


def test_empty_criteria_and_wrong_question_ids_rejected():
    from matb_integration.inference.question_packs import load_question_pack
    from matb_integration.inference.contracts import QuestionPackV1
    data = load_question_pack('matb-debrief-v1').model_dump()
    data['questions']['automation_belief']['criteria'] = {}
    with pytest.raises(ValidationError):
        QuestionPackV1(**data)


def test_nested_mapping_cannot_mutate_pack():
    from types import MappingProxyType
    from matb_integration.inference.question_packs import load_question_pack
    from matb_integration.inference.contracts import QuestionPackV1
    data = load_question_pack('matb-debrief-v1').model_dump()
    question = data['questions']['reported_task_tradeoff']
    original = question['instructions']
    data['questions']['reported_task_tradeoff'] = MappingProxyType(question)
    pack = QuestionPackV1(**data)
    question['instructions'] = 'changed'
    assert pack.questions['reported_task_tradeoff']['instructions'] == original
    data['questions'] = {'wrong': {'type': 'noul', 'instructions': 'Question'}}
    with pytest.raises(ValidationError):
        QuestionPackV1(**data)
