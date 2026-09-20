import os
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def clear_credentials(monkeypatch):
    for key in ('OPENAI_API_KEY','openai_api_key','JEV_AI_API_KEY','jev_ai_api_key','JEV_API_KEY','jev_api_key','MATB_LOCAL_ENV_FILE'):
        monkeypatch.delenv(key,raising=False)


def test_lowercase_keys_and_no_environment_mutation(tmp_path):
    from matb_integration.local_credentials import get_api_key
    (tmp_path/'.env.local').write_text('openai_api_key="synthetic-openai"\njev_api_key=synthetic-jev # reviewed\nMATB_JEV_MODE=post_session_remote\n',encoding='utf-8')
    before=dict(os.environ)
    assert get_api_key('openai',repository_root=tmp_path)=='synthetic-openai'
    assert get_api_key('jev',repository_root=tmp_path)=='synthetic-jev'
    assert dict(os.environ)==before


def test_environment_and_explicit_file_precedence(tmp_path,monkeypatch):
    from matb_integration.local_credentials import get_api_key
    explicit=tmp_path/'other.env';explicit.write_text('JEV_API_KEY=explicit',encoding='utf-8')
    (tmp_path/'.env.local').write_text('JEV_AI_API_KEY=local',encoding='utf-8')
    monkeypatch.setenv('MATB_LOCAL_ENV_FILE',str(explicit))
    assert get_api_key('jev',repository_root=tmp_path)=='explicit'
    monkeypatch.setenv('JEV_AI_API_KEY','process')
    assert get_api_key('jev',repository_root=tmp_path)=='process'


def test_linked_worktree_uses_main_checkout_file(tmp_path):
    from matb_integration.local_credentials import get_api_key
    main=tmp_path/'main';work=tmp_path/'work'
    metadata=main/'.git'/'worktrees'/'work';metadata.mkdir(parents=True);work.mkdir()
    (work/'.git').write_text(f'gitdir: {metadata.as_posix()}\n',encoding='utf-8')
    (metadata/'commondir').write_text('../..',encoding='utf-8')
    (main/'.env.local').write_text('jev_api_key=shared-synthetic',encoding='utf-8')
    assert get_api_key('jev',repository_root=work)=='shared-synthetic'
    (work/'.env.local').write_text('jev_api_key=isolated-synthetic',encoding='utf-8')
    assert get_api_key('jev',repository_root=work)=='isolated-synthetic'


def test_no_expansion_or_unbounded_file_reads(tmp_path):
    from matb_integration.local_credentials import get_api_key
    path=tmp_path/'.env.local'
    path.write_text("export OPENAI_API_KEY='literal-$HOME'\n",encoding='utf-8-sig')
    assert get_api_key('openai',repository_root=tmp_path)=='literal-$HOME'
    path.write_text('x'*65537,encoding='utf-8')
    assert get_api_key('openai',repository_root=tmp_path) is None
    with pytest.raises(ValueError):get_api_key('other',repository_root=tmp_path)


def test_jev_disabled_does_not_read_credentials(monkeypatch):
    import asyncio
    from matb_integration.inference.client import JevProvider
    import matb_integration.local_credentials as credentials
    monkeypatch.setenv('MATB_ENABLE_SEMANTIC_REVIEW','1');monkeypatch.setenv('MATB_JEV_MODE','off')
    monkeypatch.setattr(credentials,'get_api_key',lambda *a,**k:pytest.fail('disabled mode read credentials'))
    assert asyncio.run(JevProvider().evaluate({})).outcome=='not_sent'


def test_jev_file_key_only_reaches_mock_authorization(tmp_path,monkeypatch):
    import asyncio
    import httpx
    from matb_integration.inference.client import JevProvider
    path=tmp_path/'.env.local';path.write_text('jev_api_key=synthetic-file-key',encoding='utf-8')
    monkeypatch.setenv('MATB_LOCAL_ENV_FILE',str(path))
    monkeypatch.setenv('MATB_ENABLE_SEMANTIC_REVIEW','1');monkeypatch.setenv('MATB_JEV_MODE','post_session_remote')
    def handle(request):
        assert request.headers['authorization']=='Bearer synthetic-file-key'
        return httpx.Response(200,content=b'{}')
    result=asyncio.run(JevProvider(transport=httpx.MockTransport(handle)).evaluate({'model':'jev-1.13.0'}))
    assert result.outcome=='received'
    assert 'synthetic-file-key' not in result.model_dump_json()


def test_audio_generator_uses_shared_lowercase_lookup(tmp_path,monkeypatch):
    import runpy
    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules,'openai',SimpleNamespace(OpenAI=lambda **kw:pytest.fail('network client created')))
    path=tmp_path/'.env.local';path.write_text('openai_api_key=synthetic-audio',encoding='utf-8')
    monkeypatch.setenv('MATB_LOCAL_ENV_FILE',str(path))
    script=Path(__file__).resolve().parents[1]/'scripts/generate_participant_instruction_audio.py'
    namespace=runpy.run_path(str(script))
    assert namespace['load_api_key']()=='synthetic-audio'
