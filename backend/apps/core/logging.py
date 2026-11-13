"""Logging filter that scrubs secrets (e.g. the xAI API key) from log records."""
import logging

REPLACEMENT = "[REDACTED]"


def _secrets() -> list[str]:
    try:
        from django.conf import settings

        values = [getattr(settings, "XAI_API_KEY", ""), getattr(settings, "SECRET_KEY", "")]
    except Exception:  # settings not configured yet
        return []
    return [v for v in values if v and len(v) >= 8]


def redact(text: str) -> str:
    for secret in _secrets():
        text = text.replace(secret, REPLACEMENT)
    return text


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not _secrets():
            return True
        message = record.getMessage()
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True
