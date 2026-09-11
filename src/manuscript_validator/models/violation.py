"""Violation records (spec section 5.4).

A dataclass rather than a pydantic model: violations are created in loops and
mutated in place -- spec section 8 sets `v.status = "fixed"` -- which a
validating model fights.

`to_dict` emits the eight spec keys first, in spec order, and appends extension
keys only when they carry information. A plain violation therefore serialises
byte-identically to section 5.4's example, and golden-file tests can assert
that rather than an approximation of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from manuscript_validator.models.enums import Section, Severity, ViolationStatus


@dataclass
class Violation:
    rule_id: str
    severity: Severity
    section: Section | None = None
    paragraph_id: str | None = None
    expected: str = ""
    found: str = ""
    auto_fixable: bool = False
    status: ViolationStatus = ViolationStatus.OPEN

    #: Which runs within the paragraph triggered this. Word splits text into
    #: runs arbitrarily, so a five-run title must yield one violation carrying
    #: five indices, not five identical violations.
    run_indices: list[int] = field(default_factory=list)

    #: Where to attach the Word comment when the violation has no paragraph of
    #: its own -- document-level rules such as `doc-order`. Kept separate from
    #: `paragraph_id` so the report does not claim a location that is not real.
    anchor_paragraph_id: str | None = None

    #: Set on semantic rules: the model's rationale and proposed correction.
    explanation: str = ""
    suggested_fix: str = ""

    #: Why a semantic check could not run (`api_key_missing`, `offline`, ...).
    failure_reason: str = ""

    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def needs_review(self) -> bool:
        return self.status in (
            ViolationStatus.OPEN,
            ViolationStatus.NEEDS_REVIEW,
            ViolationStatus.FIX_FAILED,
            ViolationStatus.CONFLICT,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "section": self.section.value if self.section else None,
            "paragraph_id": self.paragraph_id,
            "expected": self.expected,
            "found": self.found,
            "auto_fixable": self.auto_fixable,
            "status": self.status.value,
        }
        if self.run_indices:
            data["run_indices"] = list(self.run_indices)
        if self.anchor_paragraph_id is not None:
            data["anchor_paragraph_id"] = self.anchor_paragraph_id
        if self.explanation:
            data["explanation"] = self.explanation
        if self.suggested_fix:
            data["suggested_fix"] = self.suggested_fix
        if self.failure_reason:
            data["failure_reason"] = self.failure_reason
        if self.message:
            data["message"] = self.message
        if self.details:
            data["details"] = dict(self.details)
        return data
