"""Task 6 exit criteria (report-shape half): the JSON a real validation run
produces must validate against a committed JSON Schema for spec section 5.4's
report shape -- not just "look right" by eyeball.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import jsonschema
import pytest
from docx import Document

from fixtures.factory import RULE_IDS, build_compliant, violating
from manuscript_validator.models.report import ValidationReport
from manuscript_validator.parser.ast_builder import build_ast
from manuscript_validator.rules import engine
from manuscript_validator.rules.loader import load_ruleset
from manuscript_validator.segmenter import segment

RULESET = load_ruleset("journal_v1")
SCHEMA = json.loads(
    (Path(__file__).parent / "schemas" / "report.schema.json").read_text("utf-8")
)


def _validate_document(doc: Document) -> dict:
    buf = BytesIO()
    doc.save(buf)
    source_bytes = buf.getvalue()
    ast = build_ast(Document(BytesIO(source_bytes)), source_bytes)
    segmentation = segment(ast, RULESET)
    violations = engine.validate(ast, RULESET, segmentation)
    report = ValidationReport(
        document_id=ast.document_id,
        ruleset_version=RULESET.ruleset_version,
        violations=violations,
        missing_sections=[s.value for s in segmentation.missing_sections],
    )
    return report.to_dict()


def test_compliant_report_validates_against_the_schema() -> None:
    doc, _handles = build_compliant()
    jsonschema.validate(_validate_document(doc), SCHEMA)


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_every_violating_fixture_report_validates_against_the_schema(rule_id: str) -> None:
    doc, _handles = violating(rule_id)
    jsonschema.validate(_validate_document(doc), SCHEMA)


def test_report_is_json_serialisable_end_to_end() -> None:
    """`to_dict()` alone isn't proof -- something in it (an Enum, a set) could
    still fail at the `json.dumps` boundary the CLI/UI actually calls."""
    doc, _handles = build_compliant()
    data = _validate_document(doc)
    round_tripped = json.loads(json.dumps(data))
    jsonschema.validate(round_tripped, SCHEMA)
