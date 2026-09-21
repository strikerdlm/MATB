import logging

import pytest
from uvicorn.logging import AccessFormatter

from app.logging_security import RedactQueryCredentials, configure_uvicorn_logging


@pytest.mark.parametrize("key", ["lease", "token", "access_token"])
def test_query_credentials_are_redacted_after_log_interpolation(key):
    record = logging.LogRecord("uvicorn.error", logging.INFO, "", 0,
        '%s - "WebSocket %s" [accepted]',
        ("127.0.0.1:1234", f"/simulation/sessions/synthetic/stream?after_sequence=2&{key}=synthetic-secret&mode=observer"), None)
    assert RedactQueryCredentials().filter(record)
    assert "synthetic-secret" not in record.getMessage()
    assert f"{key}=[REDACTED]&mode=observer" in record.getMessage()
    assert "after_sequence=2" in record.getMessage()


@pytest.mark.parametrize("key", ["lease", "token", "access_token"])
def test_redaction_preserves_uvicorn_access_formatter_arguments(key):
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1234", "GET", f"/stream?{key}=synthetic-secret&mode=observer", "1.1", 200), None)
    assert RedactQueryCredentials().filter(record)
    formatter = AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False)
    formatted = formatter.format(record)
    assert "synthetic-secret" not in formatted
    assert "synthetic-secret" not in record.getMessage()
    assert f"GET /stream?{key}=[REDACTED]&mode=observer HTTP/1.1" in formatted
    assert "200 OK" in formatted


def test_logging_configuration_is_idempotent_and_preserves_ordinary_messages():
    configure_uvicorn_logging()
    configure_uvicorn_logging()
    for name in ("uvicorn.error", "uvicorn.access"):
        assert sum(isinstance(item, RedactQueryCredentials) for item in logging.getLogger(name).filters) == 1
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "GET %s", ("/health",), None)
    assert RedactQueryCredentials().filter(record)
    assert record.getMessage() == "GET /health"
