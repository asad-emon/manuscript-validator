"""Logging configuration, including API-key redaction.

Spec section 13 requires the Gemini API key never be logged, written to the
audit log, or included in exported reports. Redaction lives in a logging
filter rather than at each call site, so a key reaching a log record by a route
nobody anticipated is still scrubbed.
"""

from __future__ import annotations

import logging
import re
from typing import Any

#: Google API keys are a fixed shape: the literal "AIza" then 35 URL-safe chars.
_API_KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_\-]{35}")

REDACTED = "<redacted>"


class RedactingFilter(logging.Filter):
    """Scrub API keys from log records.

    Catches both the generic Google key shape and any literal secrets
    registered via `register_secret` -- registration covers keys that do not
    match the published shape, which the pattern alone would miss.
    """

    def __init__(self) -> None:
        super().__init__()
        self._secrets: set[str] = set()

    def register_secret(self, secret: str) -> None:
        """Register a literal value to scrub. Short values are ignored."""
        if secret and len(secret) >= 8:
            self._secrets.add(secret)

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return _API_KEY_PATTERN.sub(REDACTED, text)

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.redact(record.msg)
        if record.args:
            record.args = self._redact_args(record.args)
        return True

    def _redact_args(self, args: Any) -> Any:
        if isinstance(args, dict):
            return {k: self._redact_one(v) for k, v in args.items()}
        if isinstance(args, tuple):
            return tuple(self._redact_one(v) for v in args)
        return args

    def _redact_one(self, value: Any) -> Any:
        return self.redact(value) if isinstance(value, str) else value


_filter = RedactingFilter()


def get_redacting_filter() -> RedactingFilter:
    """Return the process-wide redacting filter."""
    return _filter


def configure_logging(level: int = logging.INFO, *, stream: Any = None) -> None:
    """Install a console handler carrying the redacting filter.

    Idempotent: calling it twice does not duplicate handlers.
    """
    root = logging.getLogger()
    root.setLevel(level)
    for existing in root.handlers:
        if getattr(existing, "_mv_configured", False):
            return
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    handler.addFilter(_filter)
    handler._mv_configured = True  # type: ignore[attr-defined]
    root.addHandler(handler)
