"""Deterministic checks: pure attribute comparisons, no external calls.

`evaluate_rule` is the single entry point `engine.py` calls for every
`DeterministicRule`. It handles the missing-section and front-matter-only
degradation contracts (Task 5) uniformly for every rule, then dispatches by
`selector.node_type` -- except for the three checks the generic
attribute/operator grammar cannot express (a numbering *sequence* depends on
every table's relative position, not one table's own attributes; a table
cell's font size needs runs whose *paragraph* is a table cell, which is a
different granularity than the paragraph/run selection every other rule
shares) and are registered in `_BESPOKE_CHECKS` instead.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any

from manuscript_validator.models.ast import Ast, Figure, Table
from manuscript_validator.models.enums import (
    NodeType,
    OnMissingSection,
    Section,
    SelectorScope,
    ViolationStatus,
)
from manuscript_validator.models.violation import Violation
from manuscript_validator.parser.captions import numeral_value
from manuscript_validator.rules.comparators import evaluate
from manuscript_validator.rules.schema import DeterministicRule
from manuscript_validator.rules.selectors import (
    matches_condition,
    select_figures,
    select_paragraphs,
    select_runs,
    select_tables,
)
from manuscript_validator.segmenter.heuristics import FRONT_MATTER_SECTIONS
from manuscript_validator.segmenter.section_index import SegmentationResult

#: The attribute prefix Task 5's `generate_section_present_rules` uses for
#: `NodeType.DOCUMENT` rules -- there is no node to select for a section that
#: doesn't exist, so this is a lookup key into `missing_sections`, not a
#: paragraph/run/table attribute.
_SECTION_PRESENT_PREFIX = "section:"

_BODY_SECTIONS = frozenset(Section) - frozenset(FRONT_MATTER_SECTIONS) - {Section.UNKNOWN}


def _format_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _expected_str(rule: DeterministicRule) -> str:
    if rule.expected_repr:
        return rule.expected_repr
    condition = rule.condition
    return f"{condition.attribute} {condition.operator.value} {_format_value(condition.value)}"


def _found_str(attribute: str, value: Any) -> str:
    return f"{attribute} == {_format_value(value)!r}"


def _build_violation(
    rule: DeterministicRule,
    *,
    section: Section | None = None,
    paragraph_id: str | None = None,
    anchor_paragraph_id: str | None = None,
    found: str = "",
    run_indices: list[int] | None = None,
    status: ViolationStatus = ViolationStatus.OPEN,
    failure_reason: str = "",
    details: dict[str, Any] | None = None,
) -> Violation:
    return Violation(
        rule_id=rule.rule_id,
        severity=rule.severity,
        section=section,
        paragraph_id=paragraph_id,
        anchor_paragraph_id=anchor_paragraph_id,
        expected=_expected_str(rule),
        found=found,
        auto_fixable=rule.auto_fixable and status is ViolationStatus.OPEN,
        status=status,
        run_indices=run_indices or [],
        failure_reason=failure_reason,
        message=rule.message,
        details=details or {},
    )


def _is_fully_missing(rule: DeterministicRule, segmentation: SegmentationResult) -> bool:
    """True only when *every* section the rule applies to is missing.

    A rule like `heading-bold` applies to ten sections; if exactly one of
    them (say, Discussion) is missing, the right outcome is that
    `select_paragraphs` simply finds no Discussion paragraphs to check --
    the other nine still must be checked normally. Treating *any* overlap
    with `missing_sections` as "skip this rule" would silently stop checking
    every section the rule covers just because one of them is absent.
    """
    sections = set(rule.applies_to_section)
    return bool(sections) and sections <= segmentation.missing_sections


def _degradation_reason(rule: DeterministicRule, segmentation: SegmentationResult) -> str | None:
    if segmentation.front_matter_only and set(rule.applies_to_section) & _BODY_SECTIONS:
        return segmentation.degraded_reason or "section boundaries undetected"
    fully_missing = _is_fully_missing(rule, segmentation)
    if fully_missing and rule.on_missing_section is not OnMissingSection.SKIP:
        names = ", ".join(sorted(s.value for s in rule.applies_to_section))
        return f"section not found: {names}"
    return None


def _is_skipped_by_missing_section(
    rule: DeterministicRule, segmentation: SegmentationResult
) -> bool:
    if segmentation.front_matter_only and set(rule.applies_to_section) & _BODY_SECTIONS:
        return False  # degrades to check_failed, handled by _degradation_reason
    skip = rule.on_missing_section is OnMissingSection.SKIP
    return _is_fully_missing(rule, segmentation) and skip


def _evaluate_run_rule(ast: Ast, rule: DeterministicRule) -> list[Violation]:
    violations: list[Violation] = []
    for paragraph in select_paragraphs(ast, rule):
        runs = select_runs(paragraph, rule)
        indexed = [(i, r) for i, r in enumerate(paragraph.runs) if r in runs]
        if not indexed:
            continue
        passes = [matches_condition(r, rule.condition) for _i, r in indexed]
        scope = rule.selector.scope
        if scope is SelectorScope.EVERY:
            failing = [i for (i, _r), ok in zip(indexed, passes, strict=True) if not ok]
            if not failing:
                continue
            bad_value = getattr(paragraph.runs[failing[0]], rule.condition.attribute, None)
        elif scope is SelectorScope.ANY:
            if any(passes):
                continue
            failing = [i for i, _r in indexed]
            bad_value = getattr(paragraph.runs[failing[0]], rule.condition.attribute, None)
        else:  # FIRST
            first_index, first_run = indexed[0]
            if matches_condition(first_run, rule.condition):
                continue
            failing = [first_index]
            bad_value = getattr(first_run, rule.condition.attribute, None)
        violations.append(
            _build_violation(
                rule,
                section=paragraph.section,
                paragraph_id=paragraph.id,
                found=_found_str(rule.condition.attribute, bad_value),
                run_indices=failing,
            )
        )
    return violations


def _evaluate_paragraph_rule(ast: Ast, rule: DeterministicRule) -> list[Violation]:
    violations = []
    for paragraph in select_paragraphs(ast, rule):
        if matches_condition(paragraph, rule.condition):
            continue
        value = getattr(paragraph, rule.condition.attribute, None)
        violations.append(
            _build_violation(
                rule,
                section=paragraph.section,
                paragraph_id=paragraph.id,
                found=_found_str(rule.condition.attribute, value),
            )
        )
    return violations


def _evaluate_section_text_rule(ast: Ast, rule: DeterministicRule) -> list[Violation]:
    paragraphs = select_paragraphs(ast, rule)
    if not paragraphs:
        return []
    text = " ".join(p.text for p in paragraphs)
    if evaluate(rule.condition.operator, text, rule.condition.value):
        return []
    section = rule.applies_to_section[0] if rule.applies_to_section else paragraphs[0].section
    return [
        _build_violation(
            rule,
            section=section,
            anchor_paragraph_id=paragraphs[0].id,
            found=_found_str(rule.condition.attribute, text),
        )
    ]


def _evaluate_table_or_figure_rule(
    items: list[Table] | list[Figure], rule: DeterministicRule
) -> list[Violation]:
    violations = []
    for item in items:
        if matches_condition(item, rule.condition):
            continue
        value = getattr(item, rule.condition.attribute, None)
        violations.append(
            _build_violation(
                rule,
                section=Section.RESULT,
                paragraph_id=item.caption_paragraph_id,
                found=_found_str(rule.condition.attribute, value),
                details={"id": item.id},
            )
        )
    return violations


def _evaluate_document_rule(
    ast: Ast, rule: DeterministicRule, segmentation: SegmentationResult
) -> list[Violation]:
    attribute = rule.condition.attribute
    if not attribute.startswith(_SECTION_PRESENT_PREFIX):
        return []
    section_name = attribute.removeprefix(_SECTION_PRESENT_PREFIX)
    missing_names = {s.value for s in segmentation.missing_sections}
    if section_name not in missing_names:
        return []
    return [_build_violation(rule, found=f"section '{section_name}' not found")]


def _check_numbering_sequence(
    ast: Ast, rule: DeterministicRule, items: list[Table] | list[Figure]
) -> list[Violation]:
    """Numbers must run 1/I, 2/II, 3/III, ... with no gaps -- a check about
    every item's position *relative to the others*, which a single-item
    `Condition` cannot express."""
    violations = []
    numbered = [item for item in items if item.caption_number is not None]
    for expected_index, item in enumerate(numbered, start=1):
        value = numeral_value(item.caption_number, item.numbering_style)
        if value == expected_index:
            continue
        violations.append(
            _build_violation(
                rule,
                section=Section.RESULT,
                paragraph_id=item.caption_paragraph_id,
                found=f"caption_number == {item.caption_number!r} (position {expected_index})",
                details={"id": item.id},
            )
        )
    return violations


def _check_table_numbering_sequence(ast: Ast, rule: DeterministicRule) -> list[Violation]:
    return _check_numbering_sequence(ast, rule, ast.tables)


def _check_figure_numbering_sequence(ast: Ast, rule: DeterministicRule) -> list[Violation]:
    return _check_numbering_sequence(ast, rule, ast.figures)


def _check_table_text_size(ast: Ast, rule: DeterministicRule) -> list[Violation]:
    """Cell font size, checked across *every* cell run in *every* table --
    `Ast.Table.cell_font_size_pt` only samples one representative cell, so
    this reads `Paragraph.in_table` directly rather than going through the
    generic paragraph/run selection (which excludes table cells entirely).

    One violation per *offending cell paragraph*, not per table: Task 8's fix
    planner turns `run_indices` into per-run `FixOp`s, and `set_font_size` is
    a run-level action -- a single table-wide violation would leave the fix
    planner with a paragraph id but a run-scoped action and nowhere correct
    to point it.
    """
    violations = []
    for table in ast.tables:
        for paragraph in ast.paragraphs:
            if paragraph.in_table != table.id:
                continue
            failing = [
                i
                for i, run in enumerate(paragraph.runs)
                if not matches_condition(run, rule.condition)
            ]
            if not failing:
                continue
            bad_value = getattr(paragraph.runs[failing[0]], rule.condition.attribute, None)
            violations.append(
                _build_violation(
                    rule,
                    section=Section.RESULT,
                    paragraph_id=paragraph.id,
                    found=_found_str(rule.condition.attribute, bad_value),
                    run_indices=failing,
                    details={"table_id": table.id},
                )
            )
    return violations


_BESPOKE_CHECKS: dict[str, Callable[[Ast, DeterministicRule], list[Violation]]] = {
    "table-numbering-sequence": _check_table_numbering_sequence,
    "figure-numbering-sequence": _check_figure_numbering_sequence,
    "table-text-size": _check_table_text_size,
}


def evaluate_rule(
    ast: Ast, rule: DeterministicRule, segmentation: SegmentationResult
) -> list[Violation]:
    if _is_skipped_by_missing_section(rule, segmentation):
        return []
    reason = _degradation_reason(rule, segmentation)
    if reason is not None:
        status = (
            ViolationStatus.CHECK_FAILED
            if rule.on_missing_section is not OnMissingSection.VIOLATION
            else ViolationStatus.OPEN
        )
        return [_build_violation(rule, status=status, failure_reason=reason, found=reason)]

    bespoke = _BESPOKE_CHECKS.get(rule.rule_id)
    if bespoke is not None:
        return bespoke(ast, rule)

    node_type = rule.selector.node_type
    if node_type is NodeType.RUN:
        return _evaluate_run_rule(ast, rule)
    if node_type is NodeType.PARAGRAPH:
        return _evaluate_paragraph_rule(ast, rule)
    if node_type is NodeType.SECTION_TEXT:
        return _evaluate_section_text_rule(ast, rule)
    if node_type is NodeType.TABLE:
        return _evaluate_table_or_figure_rule(select_tables(ast, rule), rule)
    if node_type is NodeType.FIGURE:
        return _evaluate_table_or_figure_rule(select_figures(ast, rule), rule)
    if node_type is NodeType.DOCUMENT:
        return _evaluate_document_rule(ast, rule, segmentation)
    return []


__all__ = ["evaluate_rule"]
