"""Audit log entries (spec section 5.5).

Frozen: an audit entry records something that already happened, so it is
write-once by definition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from manuscript_validator.models.enums import FixAction


@dataclass(frozen=True)
class AuditEntry:
    rule_id: str
    paragraph_id: str
    action: FixAction
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    #: Which runs the fix touched, and -- when the fix split a run -- the id it
    #: was split from, so the redline can be traced back to the original.
    run_indices: tuple[int, ...] = ()
    split_from: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "rule_id": self.rule_id,
            "paragraph_id": self.paragraph_id,
            "action": self.action.value,
            "before": dict(self.before),
            "after": dict(self.after),
            "timestamp": self.timestamp,
        }
        if self.run_indices:
            data["run_indices"] = list(self.run_indices)
        if self.split_from is not None:
            data["split_from"] = self.split_from
        return data
