"""Task 16 exit criterion: a Gemini API key must never appear in application
logs, the JSON report, or the audit log -- audited end to end, not just at
the `RedactingFilter` unit level Task 1 already covers.
"""

from __future__ import annotations

import json
import logging
from io import StringIO
from pathlib import Path

import pytest

from fixtures.factory import violating
from manuscript_validator.logging_setup import configure_logging, get_redacting_filter
from manuscript_validator.pipeline import PipelineOptions, run
from manuscript_validator.rules.llm_client import GeminiSemanticClient


def _google_shaped_key(marker: str) -> str:
    """A syntactically valid Google API key shape (`AIza` + exactly 35
    chars) built from `marker` -- computed, not hand-counted, since an
    off-by-one here would silently test nothing."""
    body = (marker * 8)[:35]
    assert len(body) == 35
    return f"AIza{body}"


_FAKE_KEY = _google_shaped_key("Sy0Real")


@pytest.fixture(autouse=True)
def _clean_root_handlers():
    """`configure_logging()` is idempotent by design but still adds a real
    handler to the root logger -- remove it after each test so one test's
    logging setup can't leak into another's assertions."""
    root = logging.getLogger()
    before = list(root.handlers)
    yield
    for handler in list(root.handlers):
        if handler not in before:
            root.removeHandler(handler)


def _configure_capturing_logger() -> StringIO:
    stream = StringIO()
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_mv_configured", False):
            root.removeHandler(handler)
    configure_logging(level=logging.DEBUG, stream=stream)
    return stream


def test_a_registered_key_is_redacted_from_log_output_in_every_form() -> None:
    stream = _configure_capturing_logger()
    get_redacting_filter().register_secret(_FAKE_KEY)
    logger = logging.getLogger("manuscript_validator.test_audit")

    logger.info("Constructed client with key %s", _FAKE_KEY)
    logger.error("Request failed: https://example.com/api?key=%s", _FAKE_KEY)
    logger.debug("raw: %s", {"api_key": _FAKE_KEY})

    output = stream.getvalue()
    assert _FAKE_KEY not in output
    assert "<redacted>" in output


def test_the_generic_google_key_shape_is_redacted_even_without_registration() -> None:
    """The pattern-based half of the filter: a key shaped like a real Google
    API key is caught even if nothing ever called `register_secret` on it --
    covers a key reaching a log line through a path nobody anticipated."""
    stream = _configure_capturing_logger()
    logger = logging.getLogger("manuscript_validator.test_audit_pattern")
    unregistered_key = _google_shaped_key("Unreg1")

    logger.info("using key %s", unregistered_key)

    assert unregistered_key not in stream.getvalue()


def test_gemini_client_construction_registers_the_key_for_redaction() -> None:
    stream = _configure_capturing_logger()
    GeminiSemanticClient(api_key=_FAKE_KEY)

    logger = logging.getLogger("manuscript_validator.test_audit_client")
    logger.info("client ready, key was %s", _FAKE_KEY)

    assert _FAKE_KEY not in stream.getvalue()


def test_report_and_audit_json_never_contain_the_api_key(tmp_path: Path) -> None:
    """End-to-end: run the real pipeline with a real-shaped key in scope
    (semantic checks disabled to avoid a real network call -- this test is
    about output-file hygiene, not connectivity) and grep every byte of
    every JSON output file for the key.
    """
    doc, _handles = violating("title-size")
    source = tmp_path / "paper.docx"
    doc.save(source)

    get_redacting_filter().register_secret(_FAKE_KEY)
    result = run(
        source,
        PipelineOptions(output_dir=tmp_path / "out", run_semantic=False, api_key=_FAKE_KEY),
    )

    report_text = result.outputs["report"].read_text("utf-8")
    audit_text = result.outputs["audit"].read_text("utf-8")
    assert _FAKE_KEY not in report_text
    assert _FAKE_KEY not in audit_text

    # Also confirm both files are valid, non-trivial JSON -- a redaction bug
    # that silently emptied the file would pass a naive "key not present"
    # check for the wrong reason.
    assert json.loads(report_text)["document_id"]
    assert "entries" in json.loads(audit_text)
