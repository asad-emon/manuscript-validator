"""Gemini adapter -- the only module importing `google.genai`.

Every failure is classified and returned, never raised: a missing key, a
dropped connection, or a malformed response becomes a `check_failed`
violation so the deterministic pipeline still completes (spec sections 4.2
and 13). `GeminiSemanticClient` implements `semantic.SemanticClient`, so
`rules/semantic.py` never needs to know this module exists.
"""

from __future__ import annotations

import httpx
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from manuscript_validator.logging_setup import get_redacting_filter
from manuscript_validator.rules.schema import SemanticVerdict
from manuscript_validator.rules.semantic import SemanticCheckResult

#: Fast, cheap, and good enough for structured yes/no-with-explanation
#: classification -- these prompts ask for a single boolean verdict plus a
#: short rationale, not open-ended generation.
DEFAULT_MODEL = "gemini-2.5-flash"

_REQUEST_TIMEOUT_MS = 30_000
_RETRY_ATTEMPTS = 3


def _is_api_key_invalid(exc: errors.APIError) -> bool:
    """Gemini does not use 401/403 for a bad key -- it returns plain 400
    `INVALID_ARGUMENT` with the real reason nested in `error.details[]`
    (`reason: "API_KEY_INVALID"`), confirmed against the live API with a
    malformed key. Falls back to a message-text check for any other shape
    the API might use, so a future response format doesn't silently
    misclassify this as a generic `service_error`.
    """
    details = exc.details if isinstance(exc.details, dict) else {}
    error = details.get("error", {}) if isinstance(details, dict) else {}
    for item in error.get("details") or []:
        if isinstance(item, dict) and item.get("reason") == "API_KEY_INVALID":
            return True
    return "api key not valid" in (exc.message or "").lower()


def _classify_error(exc: Exception) -> str:
    if isinstance(exc, errors.ClientError):
        if _is_api_key_invalid(exc):
            return "api_key_invalid"
        if exc.code in (401, 403):
            return "api_key_invalid"
        if exc.code == 429:
            return "quota_exceeded"
        return "service_error"
    if isinstance(exc, errors.ServerError):
        return "service_error"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.RequestError):
        return "offline"
    return "unknown"


class GeminiSemanticClient:
    """Wraps one `genai.Client`. Construct one per API key; registers the key
    with the process-wide redacting log filter immediately, so it can never
    reach a log line even if something downstream logs the client's repr.
    """

    def __init__(self, api_key: str, model_id: str = DEFAULT_MODEL) -> None:
        get_redacting_filter().register_secret(api_key)
        self.model_id = model_id
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=_REQUEST_TIMEOUT_MS,
                retry_options=types.HttpRetryOptions(attempts=_RETRY_ATTEMPTS),
            ),
        )

    def check(self, prompt: str) -> SemanticCheckResult:
        try:
            response = self._client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SemanticVerdict,
                    temperature=0.0,
                    seed=42,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
        except Exception as exc:  # classified below, never re-raised
            return SemanticCheckResult(ok=False, failure_reason=_classify_error(exc))
        return self._parse_response(response)

    def _parse_response(self, response: types.GenerateContentResponse) -> SemanticCheckResult:
        # Never rely on `resp.parsed` alone: the SDK only populates it when
        # the response was schema-conformant JSON with the exact expected
        # types, which a real model occasionally fails to produce even with
        # `response_mime_type="application/json"` set.
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, SemanticVerdict):
            return SemanticCheckResult(ok=True, verdict=parsed)
        text = getattr(response, "text", None)
        if not text:
            return SemanticCheckResult(ok=False, failure_reason="bad_response")
        try:
            verdict = SemanticVerdict.model_validate_json(text)
        except (ValidationError, ValueError):
            return SemanticCheckResult(ok=False, failure_reason="bad_response")
        return SemanticCheckResult(ok=True, verdict=verdict)

    def test_connection(self) -> bool:
        """A real auth check with zero token spend: lists models rather than
        generating content."""
        try:
            next(iter(self._client.models.list()), None)
        except Exception:  # "did auth work" is boolean by design
            return False
        return True


__all__ = ["DEFAULT_MODEL", "GeminiSemanticClient"]
