"""Fix planning, conflict detection, and fix application.

`plan_fixes` is pure data: violations plus a ruleset in, a `FixPlan` out, no
document access at all -- the AST it read `run_indices` from is never touched
again here, satisfying "input AST provably unmutated" without needing to
assert it, since there is no document parameter to mutate. `apply_fix_plan`
is the only function that touches a live document, and it is deliberately
generic over *which* document: called once against a fresh clone for
`corrected.docx` and once more against another fresh clone for the
tracked-changes redline (Task 9/10), so the two outputs replay the exact same
plan and cannot disagree about what changed.

Conflict detection is not in the spec but FR-11 depends on it: `global-font`,
`abstract-size`, `heading-style`, and `body-text-size` could in principle all
write the same run's attributes if segmentation ever mislabelled a paragraph
into two rules' scopes at once. Last writer wins, re-validation reports the
loser, and the audit log records a change that did not survive. `FixOp`s are
grouped by `(target_id, attribute)` (`FixOp.attribute`, Task 2); a group whose
members disagree on the value to write is applied not at all, with every
violation that contributed to it marked `conflict`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from manuscript_validator.autofix import actions
from manuscript_validator.errors import DocumentError, FixApplicationError
from manuscript_validator.models.audit import AuditEntry
from manuscript_validator.models.enums import FixAction, ViolationStatus
from manuscript_validator.models.fix_plan import FixOp, FixPlan
from manuscript_validator.models.violation import Violation
from manuscript_validator.parser.binding import ElementIndex
from manuscript_validator.parser.ids import format_run_id
from manuscript_validator.rules.schema import DeterministicRule, Ruleset

_ACTIONS: dict[FixAction, Callable[[Any, dict[str, Any]], actions.ActionResult]] = {
    **actions.RUN_ACTIONS,
    **actions.PARAGRAPH_ACTIONS,
}


def _build_ops(violation: Violation, rule: DeterministicRule) -> list[FixOp]:
    assert rule.fix_action is not None  # guaranteed by schema when auto_fixable
    if violation.paragraph_id is None:
        return []
    if not violation.run_indices:
        return [
            FixOp(
                rule_id=violation.rule_id,
                target_id=violation.paragraph_id,
                action=rule.fix_action,
                params=dict(rule.fix_params),
                paragraph_id=violation.paragraph_id,
                priority=rule.priority,
            )
        ]
    return [
        FixOp(
            rule_id=violation.rule_id,
            target_id=format_run_id(violation.paragraph_id, index + 1),
            action=rule.fix_action,
            params=dict(rule.fix_params),
            paragraph_id=violation.paragraph_id,
            run_index=index,
            priority=rule.priority,
        )
        for index in violation.run_indices
    ]


def plan_fixes(violations: list[Violation], ruleset: Ruleset) -> FixPlan:
    """Every `auto_fixable`, still-`open` violation becomes one or more
    `FixOp`s; conflicting groups are withheld and their violations flipped to
    `conflict` in place.
    """
    pairs: list[tuple[Violation, FixOp]] = []
    for violation in violations:
        if not violation.auto_fixable or violation.status is not ViolationStatus.OPEN:
            continue
        rule = ruleset.by_id(violation.rule_id)
        if not isinstance(rule, DeterministicRule) or rule.fix_action is None:
            continue
        pairs.extend((violation, op) for op in _build_ops(violation, rule))

    groups: dict[tuple[str, str], list[tuple[Violation, FixOp]]] = defaultdict(list)
    for violation, op in pairs:
        groups[(op.target_id, op.attribute)].append((violation, op))

    accepted: list[FixOp] = []
    for members in groups.values():
        distinct_values = {tuple(sorted(op.params.items())) for _violation, op in members}
        if len(distinct_values) > 1:
            for violation, _op in members:
                violation.status = ViolationStatus.CONFLICT
            continue
        seen: set[tuple[str, str]] = set()
        for _violation, op in members:
            key = (op.rule_id, op.target_id)
            if key in seen:
                continue  # the same rule already contributed an identical op
            seen.add(key)
            accepted.append(op)

    return FixPlan(ops=accepted)


def resolve_target(index: ElementIndex, op: FixOp) -> Any:
    """The live element `op.target_id` names -- a run if the op came from a
    run-level violation, a paragraph otherwise. Shared with
    `output.tracked_changes`, which replays the same `FixPlan` a second time
    against a different clone.
    """
    if op.run_index is not None:
        return index.run(op.target_id)
    return index.paragraph(op.target_id)


def apply_fix_plan(
    element_index: ElementIndex,
    fix_plan: FixPlan,
    violations: list[Violation],
    timestamp: str,
) -> list[AuditEntry]:
    """Replay `fix_plan` against the document `element_index` was built over,
    marking each matching violation `fixed` on success or `fix_failed` on
    error, and returning one `AuditEntry` per successfully applied op.

    A failure in one op never aborts the run: a target that has moved or a
    caption pattern that no longer matches degrades to a single `fix_failed`
    violation, not a half-applied document.
    """
    violations_by_key = {(v.rule_id, v.paragraph_id or ""): v for v in violations}
    audit_log: list[AuditEntry] = []
    for op in fix_plan.ordered():
        violation = violations_by_key.get((op.rule_id, op.paragraph_id))
        try:
            handler = _ACTIONS[op.action]
            element = resolve_target(element_index, op)
            before, after = handler(element, op.params)
        except (FixApplicationError, DocumentError, KeyError) as exc:
            if violation is not None:
                violation.status = ViolationStatus.FIX_FAILED
                violation.failure_reason = str(exc)
            continue
        audit_log.append(
            AuditEntry(
                rule_id=op.rule_id,
                paragraph_id=op.paragraph_id,
                action=op.action,
                before=before,
                after=after,
                timestamp=timestamp,
                run_indices=(op.run_index,) if op.run_index is not None else (),
            )
        )
        if violation is not None:
            violation.status = ViolationStatus.FIXED
    return audit_log


__all__ = ["apply_fix_plan", "plan_fixes", "resolve_target"]
