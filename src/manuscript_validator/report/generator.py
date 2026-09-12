"""Builds the JSON ValidationReport (spec section 5.4)."""

from __future__ import annotations

from manuscript_validator.models.report import ValidationReport
from manuscript_validator.models.violation import Violation
from manuscript_validator.segmenter.section_index import SegmentationResult

#: Scope is body-only in v1 (spec section 6, Task 7's "declare scope" trap):
#: `Ast.paragraphs` never contains headers, footers, footnotes, endnotes, or
#: textboxes, regardless of the document -- said here rather than silently
#: omitted, since an author discovering the gap from a reviewer's markup
#: later is a credibility problem the report can prevent for free.
UNCHECKED_SCOPES = ("headers", "footers", "footnotes", "endnotes", "textboxes")


def build_report(
    document_id: str,
    ruleset_version: str,
    violations: list[Violation],
    segmentation: SegmentationResult,
) -> ValidationReport:
    missing = sorted(section.value for section in segmentation.missing_sections)
    return ValidationReport(
        document_id=document_id,
        ruleset_version=ruleset_version,
        violations=violations,
        missing_sections=missing,
        unchecked_scopes=list(UNCHECKED_SCOPES),
    )


__all__ = ["UNCHECKED_SCOPES", "build_report"]
