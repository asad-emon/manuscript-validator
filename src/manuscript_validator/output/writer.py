"""Replays a FixPlan against a fresh clone of the original bytes.

The corrected document is produced by patching a clone, not by serialising the
AST: the AST models roughly ten attributes per run, and regenerating a document
from it would discard images, section properties, headers, numbering,
hyperlinks, fields, footnotes, and equations. See docs/decisions.md (C2).

`write_corrected_document` takes `bytes`, never a path: FR-9 ("never mutates
the original") is then structural rather than a convention -- there is no
path parameter here to write to by mistake, and the caller's own bytes object
is immutable regardless of what happens to it afterward. The caller (the
pipeline, Task 13) is responsible for reading the source to bytes exactly
once and never passing the path any further down the call chain.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from docx import Document

from manuscript_validator.autofix.engine import apply_fix_plan
from manuscript_validator.models.audit import AuditEntry
from manuscript_validator.models.fix_plan import FixPlan
from manuscript_validator.models.violation import Violation
from manuscript_validator.parser.binding import build_element_index


def write_corrected_document(
    original_bytes: bytes,
    fix_plan: FixPlan,
    violations: list[Violation],
    timestamp: str,
) -> tuple[bytes, list[AuditEntry]]:
    """Clone `original_bytes` fresh (`Document(BytesIO(...))`, never
    `copy.deepcopy` -- docs/decisions.md C1), replay `fix_plan` against the
    clone via a freshly built `ElementIndex`, and return the corrected bytes
    plus the audit log `apply_fix_plan` produced.
    """
    document = Document(BytesIO(original_bytes))
    element_index = build_element_index(document)
    audit_log = apply_fix_plan(element_index, fix_plan, violations, timestamp)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue(), audit_log


def write_bytes(path: Path, data: bytes) -> None:
    """The one call site every output write goes through, so no pipeline,
    CLI, or UI code path ever inlines its own `.write_bytes`."""
    path.write_bytes(data)


__all__ = ["write_bytes", "write_corrected_document"]
