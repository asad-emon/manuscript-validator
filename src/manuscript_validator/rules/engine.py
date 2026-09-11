"""Rule routing (spec section 7): deterministic and semantic paths.

`validate` is the single entry point the future `pipeline`/`validator` module
calls. It merges the JSON-configured rules with Task 5's generated
`section-present-*` family (there is no reason a caller should have to
remember to do that separately) and routes each by `check_type` -- a
deterministic rule runs the real check; a semantic rule always resolves to
`semantic.evaluate_stub` until Task 12 wires up a real `SemanticClient`.
"""

from __future__ import annotations

from manuscript_validator.models.ast import Ast
from manuscript_validator.models.enums import CheckType
from manuscript_validator.models.violation import Violation
from manuscript_validator.rules import deterministic, semantic
from manuscript_validator.rules.schema import Ruleset
from manuscript_validator.segmenter.section_index import (
    SegmentationResult,
    generate_section_present_rules,
)


def validate(ast: Ast, ruleset: Ruleset, segmentation: SegmentationResult) -> list[Violation]:
    """Run every rule in `ruleset`, plus the generated section-present family,
    against `ast`. Ordered by `priority` ascending (ties keep declaration
    order, since `sorted` is stable) so Task 8's autofix sees a reproducible
    apply order.
    """
    rules = sorted(
        [*ruleset.rules, *generate_section_present_rules(ruleset)],
        key=lambda rule: rule.priority,
    )
    violations: list[Violation] = []
    for rule in rules:
        if rule.check_type is CheckType.DETERMINISTIC:
            violations.extend(deterministic.evaluate_rule(ast, rule, segmentation))
        else:
            violations.append(semantic.evaluate_stub(rule))
    return violations


__all__ = ["validate"]
