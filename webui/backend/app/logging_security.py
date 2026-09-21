"""Keep browser WebSocket controller credentials out of Uvicorn logs."""
import logging
import re


_QUERY_CREDENTIAL = re.compile(r'([?&](?:lease|token|access_token)=)[^&\s"\]]+', re.IGNORECASE)


class RedactQueryCredentials(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "uvicorn.access" and isinstance(record.args, tuple) and len(record.args) == 5:
            # AccessFormatter unpacks these arguments to render the request line.
            # Preserve their types and structure while redacting the URL itself.
            client, method, path, version, status = record.args
            record.args = (client, method, _QUERY_CREDENTIAL.sub(r'\1[REDACTED]', str(path)), version, status)
            return True
        message = record.getMessage()
        redacted = _QUERY_CREDENTIAL.sub(r'\1[REDACTED]', message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_uvicorn_logging() -> None:
    # WebSocket accept messages use uvicorn.error, even with access logs off.
    for name in ("uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        if not any(isinstance(item, RedactQueryCredentials) for item in logger.filters):
            logger.addFilter(RedactQueryCredentials())
