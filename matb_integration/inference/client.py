"""Optional single-attempt HTTPS transport. No import-time HTTP dependency."""
import asyncio
import os
import time
from uuid import uuid4
from .contracts import ProviderAttempt, canonical_bytes


class JevProvider:
    def __init__(self, *, transport=None):
        self.transport = transport

    async def evaluate(self, payload: dict) -> ProviderAttempt:
        started = str(time.time_ns())
        identity = str(uuid4())
        def result(outcome, **values):
            return ProviderAttempt(attempt_id=identity, started_at_ns=started,
                finished_at_ns=str(time.time_ns()), outcome=outcome, **values)
        if os.getenv('MATB_ENABLE_SEMANTIC_REVIEW') != '1' or os.getenv('MATB_JEV_MODE', 'off') != 'post_session_remote':
            return result('not_sent', error_code='disabled')
        if (os.getenv('MATB_JEV_PROVIDER','jev_ai_pro')!='jev_ai_pro' or
                os.getenv('MATB_JEV_MODEL','jev-1.13.0')!='jev-1.13.0' or payload.get('model')!='jev-1.13.0'):
            return result('not_sent',error_code='disabled')
        key = os.getenv('JEV_AI_API_KEY')
        if not key:
            return result('not_sent', error_code='missing_key')
        raw = canonical_bytes(payload)
        if len(raw) > 32768:
            return result('not_sent', error_code='oversize')
        import httpx
        response_bytes = bytearray()
        status = None
        headers = {}
        try:
            async with asyncio.timeout(10):
                async with httpx.AsyncClient(transport=self.transport, trust_env=False,
                        follow_redirects=False, timeout=httpx.Timeout(8, connect=3)) as client:
                    async with client.stream('POST', 'https://jev-ai.pro/api/v1/systemone',
                            content=raw, headers={'Authorization': 'Bearer '+key,
                            'Content-Type': 'application/json', 'Accept-Encoding': 'identity'}) as response:
                        status = response.status_code
                        headers = {name: response.headers[name][:200] for name in
                            ('retry-after', 'x-jev-billing', 'x-jev-credits-charged', 'x-jev-credits-remaining')
                            if name in response.headers}
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            remaining = 65536-len(response_bytes)
                            response_bytes.extend(chunk[:remaining])
                            if len(chunk) > remaining:
                                return result('oversize', status=status, headers=headers,
                                    raw_response=bytes(response_bytes), error_code='oversize')
            return result('received', status=status, headers=headers, raw_response=bytes(response_bytes))
        except (TimeoutError, httpx.TimeoutException):
            return result('outcome_unknown', status=status, headers=headers,
                raw_response=bytes(response_bytes), error_code='timeout')
        except httpx.HTTPError:
            return result('outcome_unknown', status=status, headers=headers,
                raw_response=bytes(response_bytes), error_code='transport')
        except Exception:
            # Unexpected transport failures cannot establish non-delivery.
            return result('outcome_unknown', status=status, headers=headers,
                raw_response=bytes(response_bytes), error_code='transport')
        except asyncio.CancelledError:
            # Context managers above have terminated local I/O before returning.
            return result('cancelled', status=status, headers=headers,
                raw_response=bytes(response_bytes), error_code='cancelled')
