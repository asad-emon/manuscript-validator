"""Corrected AST -> .docx outputs (Tasks 9, 10)."""

from manuscript_validator.output.naming import OutputPaths, output_paths
from manuscript_validator.output.writer import write_bytes, write_corrected_document

__all__ = ["OutputPaths", "output_paths", "write_bytes", "write_corrected_document"]
