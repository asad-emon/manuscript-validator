"""Rule routing (spec section 7): deterministic and semantic paths.

`validate` is the single entry point the `pipeline` module (Task 13) calls.
It merges the JSON-configured rules with Task 5's generated
`section-present-*` family (there is no reason a caller should have to
remember to do that separately) and routes each by `check_type` -- a
deterministic rule runs the real check; a semantic rule is handed to
`evaluate_semantic`, which defaults to `semantic.evaluate_stub` (always one
`check_failed`, no network) so every existing caller -- and every test
written before Task 12 -- keeps working unchanged. `--no-semantic` (spec
section 13) and "no API key configured" (spec section 4.2) both mean "don't
pass a different `evaluate_semantic`"; there is no separate code path for
either, since the stub already produces exactly the `check_failed` outcome
both are supposed to.

Semantic rules run in a small thread pool: seven rules at roughly three
seconds apiece serially is twenty seconds of a frozen UI, and each call is
network I/O (or, for the stub/fake, so cheap the pool overhead is noise
either way), so there is no reason to serialize them. Deterministic rules run
first and stay single-threaded -- they are fast, local, and their relative
order is what gives Task 8's autofix a reproducible apply order; only the
semantic tail benefits from parallelism.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from manuscript_validator.models.ast import Ast
from manuscript_validator.models.enums import CheckType
from manuscript_validator.models.violation import Violation
from manuscript_validator.rules import deterministic, semantic
from manuscript_validator.rules.schema import Rule, Ruleset, SemanticRule
from manuscript_validator.segmenter.section_index import (
    SegmentationResult,
    generate_section_present_rules,
)

#: Pure stdlib, no Qt dependency here -- Task 14's UI marshals progress via
#: its own signal/slot mechanism regardless of how this pool is sized.
MAX_SEMANTIC_WORKERS = 4


def validate(
    ast: Ast,
    ruleset: Ruleset,
    segmentation: SegmentationResult,
    evaluate_semantic: Callable[[SemanticRule], Violation | None] = semantic.evaluate_stub,
) -> list[Violation]:
    """Run every rule in `ruleset`, plus the generated section-present family,
    against `ast`. Deterministic violations come first, ordered by
    `priority` ascending (ties keep declaration order, since `sorted` is
    stable) so Task 8's autofix sees a reproducible apply order; semantic
    violations follow, in whatever order their (parallel) calls complete.
    """
    rules: list[Rule] = sorted(
        [*ruleset.rules, *generate_section_present_rules(ruleset)],
        key=lambda rule: rule.priority,
    )
    deterministic_rules = [r for r in rules if r.check_type is CheckType.DETERMINISTIC]
    semantic_rules = [r for r in rules if isinstance(r, SemanticRule)]

    violations: list[Violation] = []
    for rule in deterministic_rules:
        violations.extend(deterministic.evaluate_rule(ast, rule, segmentation))

    if semantic_rules:
        with ThreadPoolExecutor(max_workers=MAX_SEMANTIC_WORKERS) as executor:
            results = executor.map(evaluate_semantic, semantic_rules)
        violations.extend(result for result in results if result is not None)

    return violations


__all__ = ["MAX_SEMANTIC_WORKERS", "validate"]
