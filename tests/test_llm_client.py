"""Task 12 exit criteria (Gemini adapter half): `check()` never raises under
any injected fault -- a malformed response, a dropped connection, or an API
error all become a classified `SemanticCheckResult`, never an exception.

Recorded payloads live in `tests/data/gemini/`: truncated JSON, markdown-
fenced JSON, prose wrapped around the object, and schema-valid-but-wrong-
types -- where most real-world LLM response bugs live, per the checklist.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors

from manuscript_validator.logging_setup import RedactingFilter
from manuscript_validator.rules.llm_client import GeminiSemanticClient, _classify_error
from manuscript_validator.rules.schema import SemanticVerdict

_DATA_DIR = Path(__file__).parent / "data" / "gemini"

#: A key matching Google's own key shape (the redacting filter's pattern),
#: but not a real one -- long enough that `register_secret` doesn't ignore it
#: even if the shape check somehow didn't fire.
_FAKE_API_KEY = "AIzaSyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAK"


def _client(monkeypatch: pytest.MonkeyPatch) -> GeminiSemanticClient:
    # Constructing genai.Client with a fake key never makes a network call by
    # itself -- only .models.generate_content()/.list() do.
    return GeminiSemanticClient(api_key=_FAKE_API_KEY)


def _fake_response(*, parsed: Any = None, text: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(parsed=parsed, text=text)


# --------------------------------------------------------------------------
# Response parsing: recorded payloads
# --------------------------------------------------------------------------


def test_parse_response_uses_parsed_when_the_sdk_already_populated_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch)
    verdict = SemanticVerdict(violation=True, explanation="x")
    result = client._parse_response(_fake_response(parsed=verdict, text="ignored"))
    assert result.ok
    assert result.verdict is verdict


def test_parse_response_falls_back_to_text_when_parsed_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch)
    text = (_DATA_DIR / "valid.json").read_text()
    result = client._parse_response(_fake_response(parsed=None, text=text))
    assert result.ok
    assert result.verdict is not None
    assert result.verdict.violation is True


@pytest.mark.parametrize(
    "filename", ["truncated.json", "markdown_fenced.txt", "prose_wrapped.txt", "wrong_types.json"]
)
def test_parse_response_classifies_every_malformed_payload_as_bad_response(
    filename: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(monkeypatch)
    text = (_DATA_DIR / filename).read_text()
    result = client._parse_response(_fake_response(parsed=None, text=text))
    assert not result.ok
    assert result.failure_reason == "bad_response"
    assert result.verdict is None


def test_parse_response_classifies_empty_text_as_bad_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch)
    result = client._parse_response(_fake_response(parsed=None, text=""))
    assert not result.ok
    assert result.failure_reason == "bad_response"


# --------------------------------------------------------------------------
# Error classification
# --------------------------------------------------------------------------


def _client_error(code: int) -> errors.ClientError:
    return errors.ClientError(code, {"error": {"message": "x", "status": "X"}})


def _server_error(code: int = 503) -> errors.ServerError:
    return errors.ServerError(code, {"error": {"message": "x", "status": "X"}})


@pytest.mark.parametrize(
    ("exc", "expected_reason"),
    [
        (_client_error(401), "api_key_invalid"),
        (_client_error(403), "api_key_invalid"),
        (_client_error(429), "quota_exceeded"),
        (_client_error(400), "service_error"),
        (_server_error(503), "service_error"),
        (httpx.ConnectTimeout("timed out"), "timeout"),
        (httpx.ReadTimeout("timed out"), "timeout"),
        (httpx.ConnectError("no route"), "offline"),
        (ValueError("something else entirely"), "unknown"),
    ],
)
def test_classify_error(exc: Exception, expected_reason: str) -> None:
    assert _classify_error(exc) == expected_reason


def test_classify_error_recognises_gemini_s_real_400_shaped_invalid_key() -> None:
    """Regression: confirmed live against the real API with a malformed key
    -- Gemini returns a plain HTTP 400 `INVALID_ARGUMENT`, not 401/403, with
    the actual reason nested in `error.details[]`. Classifying by status
    code alone silently downgraded this to `service_error`."""
    exc = errors.ClientError(
        400,
        {
            "error": {
                "code": 400,
                "message": "API key not valid. Please pass a valid API key.",
                "status": "INVALID_ARGUMENT",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "reason": "API_KEY_INVALID",
                        "domain": "googleapis.com",
                    }
                ],
            }
        },
    )
    assert _classify_error(exc) == "api_key_invalid"


def test_check_never_raises_and_classifies_the_fault(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)

    def _raise(*_args: Any, **_kwargs: Any) -> Any:
        raise _client_error(429)

    monkeypatch.setattr(client._client.models, "generate_content", _raise)

    result = client.check("does this violate the rule?")

    assert not result.ok
    assert result.failure_reason == "quota_exceeded"


def test_check_returns_ok_on_a_well_formed_response(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    verdict = SemanticVerdict(violation=False, explanation="fine")

    def _generate(*_args: Any, **_kwargs: Any) -> Any:
        return _fake_response(parsed=verdict)

    monkeypatch.setattr(client._client.models, "generate_content", _generate)

    result = client.check("prompt")

    assert result.ok
    assert result.verdict is verdict


def test_test_connection_returns_false_on_any_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)

    def _raise(*_args: Any, **_kwargs: Any) -> Any:
        raise _client_error(401)

    monkeypatch.setattr(client._client.models, "list", _raise)

    assert client.test_connection() is False


def test_test_connection_returns_true_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    monkeypatch.setattr(client._client.models, "list", lambda *a, **k: iter([object()]))

    assert client.test_connection() is True


# --------------------------------------------------------------------------
# API-key redaction
# --------------------------------------------------------------------------


def test_constructing_the_client_registers_the_key_for_redaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filt = RedactingFilter()
    monkeypatch.setattr(
        "manuscript_validator.rules.llm_client.get_redacting_filter", lambda: filt
    )

    GeminiSemanticClient(api_key=_FAKE_API_KEY)

    assert filt.redact(f"using key {_FAKE_API_KEY}") == "using key <redacted>"


def test_api_key_never_appears_in_a_redacted_log_line(monkeypatch: pytest.MonkeyPatch) -> None:
    from manuscript_validator.logging_setup import get_redacting_filter

    GeminiSemanticClient(api_key=_FAKE_API_KEY)
    redacted = get_redacting_filter().redact(f"error using {_FAKE_API_KEY}")
    assert _FAKE_API_KEY not in redacted


# --------------------------------------------------------------------------
# Live (deselected by default; requires a real key via env var)
# --------------------------------------------------------------------------


@pytest.mark.live
def test_live_connection_check() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not set")
    client = GeminiSemanticClient(api_key=api_key)
    assert client.test_connection() is True
