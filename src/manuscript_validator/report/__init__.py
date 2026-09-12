"""Violations -> JSON report and annotated .docx (Task 11)."""

from manuscript_validator.report.annotate_docx import annotate_document
from manuscript_validator.report.generator import UNCHECKED_SCOPES, build_report

__all__ = ["UNCHECKED_SCOPES", "annotate_document", "build_report"]
