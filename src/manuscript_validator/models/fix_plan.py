"""FixPlan and FixOp.

Fixes are planned as data and replayed twice -- once onto `corrected.docx`,
once onto the tracked-changes redline -- which is what makes it impossible for
the two outputs to disagree about what changed. See docs/decisions.md (C2).

Because a `FixOp` names its target by id and carries only primitives, a fix
action can be tested against a synthetic one-paragraph document with no fixture
machinery, which is what spec section 13 asks for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from manuscript_validator.models.enums import FixAction


@dataclass(frozen=True)
class FixOp:
    """One attribute change against one node."""

    rule_id: str
    target_id: str
    action: FixAction
    params: dict[str, Any] = field(default_factory=dict)
    paragraph_id: str = ""
    run_index: int | None = None
    #: Lower runs first. Gives a reproducible order when several rules touch
    #: one paragraph.
    priority: int = 100

    @property
    def attribute(self) -> str:
        """The attribute this op writes.

        Conflict detection groups ops by (target_id, attribute): two rules
        writing different values to one attribute must both be withheld rather
        than resolved by whichever happens to run last.
        """
        return _ACTION_ATTRIBUTE.get(self.action, self.action.value)


#: Which AST attribute each action writes. Actions that change text or
#: structure rather than a single attribute map to their own name, so they only
#: ever conflict with themselves.
_ACTION_ATTRIBUTE: dict[FixAction, str] = {
    FixAction.SET_FONT: "font_name",
    FixAction.SET_FONT_SIZE: "font_size_pt",
    FixAction.SET_BOLD: "bold",
    FixAction.SET_ITALIC: "italic",
    FixAction.SET_SUPERSCRIPT: "superscript",
    FixAction.SET_UPPERCASE_LITERAL: "text",
    FixAction.SET_TITLE_CASE: "text",
    FixAction.STRIP_TRAILING_COLON: "text",
    FixAction.SET_CITATION_BRACKETS: "text",
    FixAction.SET_CAPTION_POSITION: "caption_position",
    FixAction.SET_NUMBERING_STYLE: "numbering_style",
    FixAction.INSERT_LINE_BREAK: "line_break_after",
}


@dataclass
class FixPlan:
    """An ordered, replayable list of fix operations."""

    ops: list[FixOp] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.ops)

    def __iter__(self) -> Any:
        return iter(self.ops)

    def ordered(self) -> list[FixOp]:
        """Ops in deterministic apply order: priority, then target, then rule."""
        return sorted(self.ops, key=lambda op: (op.priority, op.target_id, op.rule_id))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ops": [
                {
                    "rule_id": op.rule_id,
                    "target_id": op.target_id,
                    "action": op.action.value,
                    "params": dict(op.params),
                }
                for op in self.ordered()
            ]
        }
