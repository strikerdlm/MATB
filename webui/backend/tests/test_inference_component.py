from app.components import _selected_optional_components


def test_auto_and_core_do_not_activate_semantic_provider(monkeypatch):
    monkeypatch.delenv('MATB_ENABLE_SEMANTIC_REVIEW', raising=False)
    monkeypatch.setenv('JEV_AI_API_KEY','synthetic')
    assert 'matb-semantic-review' not in dict(_selected_optional_components('auto'))
    assert _selected_optional_components('core') == ()


def test_explicit_guard_required_even_for_named_component(monkeypatch):
    import pytest
    monkeypatch.delenv('MATB_ENABLE_SEMANTIC_REVIEW', raising=False)
    with pytest.raises(ValueError):
        _selected_optional_components('matb-semantic-review')
    monkeypatch.setenv('MATB_ENABLE_SEMANTIC_REVIEW','1')
    assert 'matb-semantic-review' in dict(_selected_optional_components('matb-semantic-review'))
