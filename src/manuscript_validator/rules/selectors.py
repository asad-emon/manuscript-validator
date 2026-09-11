"""Node selection: resolves a rule's section and selector to AST nodes.

Table-cell paragraphs are excluded from every generic paragraph/run selection
by default -- a bold, short header cell like "Metric" would otherwise satisfy
`heading-bold`'s condition by accident, and `table-text-size` (a bespoke check
in `deterministic.py`, not this generic path) is the one rule that is actually
supposed to reach into cells. Body-only in v1 (spec section 6/Task 7): headers,
footers, footnotes, and textboxes are not in `Ast.paragraphs` to begin with, so
nothing here needs to filter them out separately.
"""

from __future__ import annotations

import re
from typing import Any

from manuscript_validator.models.ast import Ast, Figure, Paragraph, Run, Table
from manuscript_validator.rules.comparators import evaluate
from manuscript_validator.rules.schema import BaseRule, Condition


def matches_condition(node: Any, condition: Condition) -> bool:
    actual = getattr(node, condition.attribute, None)
    return evaluate(condition.operator, actual, condition.value)


def _excluded_by_pattern(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def select_paragraphs(ast: Ast, rule: BaseRule) -> list[Paragraph]:
    """Paragraphs in scope for a `paragraph` or `run` node-type rule."""
    candidates = [p for p in ast.paragraphs if p.in_table is None]
    if rule.applies_to_section:
        candidates = [p for p in candidates if p.section in rule.applies_to_section]
    if rule.selector.paragraph_filter is not None:
        candidates = [p for p in candidates if matches_condition(p, rule.selector.paragraph_filter)]
    if rule.exclude_patterns:
        patterns = rule.exclude_patterns
        candidates = [p for p in candidates if not _excluded_by_pattern(p.text, patterns)]
    return candidates


def select_runs(paragraph: Paragraph, rule: BaseRule) -> list[Run]:
    """Runs in scope within `paragraph`, after the run-level `selector.filter`.

    Runs with no visible text are excluded unconditionally -- a heading built
    as `paragraph.add_run().add_break()` (the journal template's own
    line-break convention) produces a second, contentless run whose `.text`
    is `"\\n"` and whose formatting is whatever the *document* default
    happens to be, not the heading's. Checking `bold`/`font_size_pt` against
    that run would fail every heading in an otherwise-compliant document.
    """
    runs = [r for r in paragraph.runs if r.text.strip()]
    if rule.selector.filter is not None:
        runs = [r for r in runs if matches_condition(r, rule.selector.filter)]
    return runs


def select_tables(ast: Ast, rule: BaseRule) -> list[Table]:
    return list(ast.tables)


def select_figures(ast: Ast, rule: BaseRule) -> list[Figure]:
    return list(ast.figures)


__all__ = [
    "matches_condition",
    "select_figures",
    "select_paragraphs",
    "select_runs",
    "select_tables",
]
