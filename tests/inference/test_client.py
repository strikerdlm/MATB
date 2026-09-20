import asyncio
import httpx
import pytest


def test_off_with_key_makes_no_request(monkeypatch):
    from matb_integration.inference.client import JevProvider
    monkeypatch.setenv('JEV_AI_API_KEY','synthetic-key')
    monkeypatch.setenv('MATB_JEV_MODE','off')
    def deny(request):
        pytest.fail('disabled provider transmitted')
    attempt = asyncio.run(JevProvider(transport=httpx.MockTransport(deny)).evaluate({}))
    assert attempt.outcome == 'not_sent'


@pytest.mark.parametrize('behavior, expected', [('success','received'),('timeout','outcome_unknown'),('oversize','oversize'),('unexpected','outcome_unknown')])
def test_single_attempt_and_bounded_response(monkeypatch, behavior, expected):
    from matb_integration.inference.client import JevProvider
    monkeypatch.setenv('MATB_ENABLE_SEMANTIC_REVIEW','1')
    monkeypatch.setenv('MATB_JEV_MODE','post_session_remote')
    monkeypatch.setenv('JEV_AI_API_KEY','synthetic-key')
    calls=[]
    def handle(request):
        calls.append(request)
        assert str(request.url) == 'https://jev-ai.pro/api/v1/systemone'
        if behavior == 'timeout': raise httpx.ReadTimeout('sensitive text')
        if behavior == 'unexpected': raise RuntimeError('sensitive provider diagnostic')
        return httpx.Response(200, content=b'x'*70000 if behavior=='oversize' else b'{}')
    result = asyncio.run(JevProvider(transport=httpx.MockTransport(handle)).evaluate({'model':'jev-1.13.0'}))
    assert result.outcome == expected
    assert len(calls) == 1
    assert len(result.raw_response) <= 65536
    assert 'synthetic-key' not in result.model_dump_json()


@pytest.mark.parametrize('setting',['MATB_JEV_PROVIDER','MATB_JEV_MODEL'])
def test_unsupported_configuration_cannot_silently_fall_back(monkeypatch,setting):
    from matb_integration.inference.client import JevProvider
    monkeypatch.setenv('MATB_ENABLE_SEMANTIC_REVIEW','1')
    monkeypatch.setenv('MATB_JEV_MODE','post_session_remote')
    monkeypatch.setenv('JEV_AI_API_KEY','synthetic-key')
    monkeypatch.setenv(setting,'unsupported')
    calls=[]
    def handle(request):
        calls.append(request)
        return httpx.Response(200,content=b'{}')
    result=asyncio.run(JevProvider(transport=httpx.MockTransport(handle)).evaluate({'model':'jev-1.13.0'}))
    assert result.outcome=='not_sent'
    assert calls==[]


def test_total_deadline_terminates_local_transport(monkeypatch):
    from matb_integration.inference.client import JevProvider
    monkeypatch.setenv('MATB_ENABLE_SEMANTIC_REVIEW','1')
    monkeypatch.setenv('MATB_JEV_MODE','post_session_remote')
    monkeypatch.setenv('JEV_AI_API_KEY','synthetic-key')
    async def exercise():
        stopped=asyncio.Event()
        async def slow(request):
            try:await asyncio.sleep(30)
            finally:stopped.set()
            return httpx.Response(200,content=b'{}')
        result=await asyncio.wait_for(JevProvider(transport=httpx.MockTransport(slow)).evaluate({'model':'jev-1.13.0'}),15)
        assert result.outcome=='outcome_unknown'
        assert result.error_code=='timeout'
        assert stopped.is_set()
    asyncio.run(exercise())
