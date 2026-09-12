"""ValidationReport (spec section 5.4).

Serialisation is hand-written rather than delegated to a library: the report is
a published file format, and its key order and shape should change only when
someone decides to change them, not when a library's dump defaults shift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from manuscript_validator.models.enums import ViolationStatus
from manuscript_validator.models.violation import Violation


def utc_timestamp() -> str:
    """ISO-8601 UTC, no fractional seconds.

    Word rejects some fractional forms in revision dates, so the whole
    application uses one timestamp format rather than two.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ValidationReport:
    document_id: str
    ruleset_version: str
    validated_at: str = field(default_factory=utc_timestamp)
    violations: list[Violation] = field(default_factory=list)

    #: Sections the segmenter could not locate, and parts of the document not
    #: examined (headers, footers, footnotes are out of scope in v1). Reported
    #: rather than silently skipped -- an author discovering the gap via a
    #: reviewer's markup later is a credibility problem.
    missing_sections: list[str] = field(default_factory=list)
    unchecked_scopes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    #: Paragraph id -> section value, for every paragraph a human corrected
    #: through the UI's section-override panel (Task 14). Recorded so a
    #: second run of the same file reproduces the same corrected labelling
    #: rather than the segmenter's original guess.
    section_overrides: dict[str, str] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.violations)

    @property
    def auto_fixed(self) -> int:
        return sum(1 for v in self.violations if v.status is ViolationStatus.FIXED)

    @property
    def needs_review(self) -> int:
        return sum(1 for v in self.violations if v.needs_review)

    @property
    def check_failed(self) -> int:
        return sum(1 for v in self.violations if v.status is ViolationStatus.CHECK_FAILED)

    def summary(self) -> dict[str, int]:
        """Spec section 5.4's three keys, plus check_failed.

        `total` deliberately is not `auto_fixed + needs_review`: a semantic
        check that could not run is neither, and collapsing it into either one
        would misreport what happened.
        """
        data = {
            "total": self.total,
            "auto_fixed": self.auto_fixed,
            "needs_review": self.needs_review,
        }
        if self.check_failed:
            data["check_failed"] = self.check_failed
        return data

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "document_id": self.document_id,
            "ruleset_version": self.ruleset_version,
            "validated_at": self.validated_at,
            "summary": self.summary(),
            "violations": [v.to_dict() for v in self.violations],
        }
        if self.missing_sections:
            data["missing_sections"] = list(self.missing_sections)
        if self.unchecked_scopes:
            data["unchecked_scopes"] = list(self.unchecked_scopes)
        if self.notes:
            data["notes"] = list(self.notes)
        if self.section_overrides:
            data["section_overrides"] = dict(self.section_overrides)
        return data
