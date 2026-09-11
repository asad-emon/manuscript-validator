"""Spec section 13: the API key must never reach a log."""

from __future__ import annotations

import logging

from manuscript_validator.logging_setup import REDACTED, RedactingFilter

SAMPLE_KEY = "AIza" + "B" * 35


def _record(msg: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord("test", logging.INFO, __file__, 1, msg, args or None, None)


def test_google_key_shape_is_redacted() -> None:
    record = _record("calling gemini with %s", SAMPLE_KEY)
    RedactingFilter().filter(record)
    assert SAMPLE_KEY not in str(record.args)


def test_key_in_message_body_is_redacted() -> None:
    record = _record(f"key={SAMPLE_KEY} rejected")
    RedactingFilter().filter(record)
    assert record.msg == f"key={REDACTED} rejected"


def test_registered_secret_is_redacted() -> None:
    """Covers keys that do not match the published Google shape."""
    filt = RedactingFilter()
    filt.register_secret("not-a-google-shaped-key")
    record = _record("using not-a-google-shaped-key now")
    filt.filter(record)
    assert "not-a-google-shaped-key" not in record.msg


def test_short_values_are_not_registered() -> None:
    """Guards against a stray short secret redacting common substrings."""
    filt = RedactingFilter()
    filt.register_secret("abc")
    record = _record("abc appears here")
    filt.filter(record)
    assert record.msg == "abc appears here"
