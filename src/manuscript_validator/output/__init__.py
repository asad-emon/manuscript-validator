"""Corrected AST -> .docx outputs (Tasks 9, 10)."""

from manuscript_validator.output.naming import OutputPaths, output_paths
from manuscript_validator.output.tracked_changes import apply_fix_plan_as_revisions
from manuscript_validator.output.writer import write_bytes, write_corrected_document

__all__ = [
    "OutputPaths",
    "apply_fix_plan_as_revisions",
    "output_paths",
    "write_bytes",
    "write_corrected_document",
]
