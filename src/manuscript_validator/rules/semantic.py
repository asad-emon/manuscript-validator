"""Semantic checks (spec section 7.2). Rule-agnostic and SDK-free.

Depends only on the `SemanticClient` protocol, so unit tests inject a fake and
the default test run makes no network calls.
"""

from __future__ import annotations

from manuscript_validator.models.enums import ViolationStatus
from manuscript_validator.models.violation import Violation
from manuscript_validator.rules.schema import SemanticRule


def evaluate_stub(rule: SemanticRule) -> Violation:
    """Always exactly one `check_failed` violation, with no network call --
    this is what proves the section 7 router works before a `SemanticClient`
    exists at all (Task 6's exit criterion). Task 12 replaces this with a real
    call; `engine.py`'s router only depends on this function's signature, so
    nothing here changes when it does.
    """
    return Violation(
        rule_id=rule.rule_id,
        severity=rule.severity,
        auto_fixable=False,
        status=ViolationStatus.CHECK_FAILED,
        failure_reason="semantic_check_not_implemented",
        message=rule.message,
    )


__all__ = ["evaluate_stub"]
