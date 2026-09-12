"""Semantic checks (spec section 7.2). Rule-agnostic and SDK-free.

Depends only on the `SemanticClient` protocol, so unit tests inject a fake and
the default test run makes no network calls. `llm_client.py` is the only
module that imports `google.genai`; this module never does.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from manuscript_validator.models.ast import Ast
from manuscript_validator.models.enums import ViolationStatus
from manuscript_validator.models.violation import Violation
from manuscript_validator.rules.cache import SemanticCache
from manuscript_validator.rules.loader import load_prompt
from manuscript_validator.rules.schema import SemanticRule, SemanticVerdict
from manuscript_validator.rules.selectors import select_paragraphs

_KEYWORDS_PREFIXES = ("keywords", "key words", "keyword")


@dataclass(frozen=True)
class SemanticCheckResult:
    """What a `SemanticClient.check()` call returns: either a verdict, or a
    classified reason it couldn't produce one. Never both, never neither."""

    ok: bool
    verdict: SemanticVerdict | None = None
    failure_reason: str = ""


class SemanticClient(Protocol):
    def check(self, prompt: str) -> SemanticCheckResult: ...

    def test_connection(self) -> bool: ...


def evaluate_stub(rule: SemanticRule) -> Violation:
    """Always exactly one `check_failed` violation, with no network call --
    this is what proves the section 7 router works before a `SemanticClient`
    exists at all (Task 6's exit criterion), and what `engine.validate()`
    falls back to when no evaluator is supplied at all (`--no-semantic`,
    spec section 13).
    """
    return Violation(
        rule_id=rule.rule_id,
        severity=rule.severity,
        auto_fixable=False,
        status=ViolationStatus.CHECK_FAILED,
        failure_reason="semantic_check_not_implemented",
        message=rule.message,
    )


def evaluate_api_key_missing(rule: SemanticRule) -> Violation:
    """Spec section 4.2: no API key configured is treated exactly like a
    semantic-check network failure, not a crash or a silent skip -- the
    pipeline (Task 13) passes this as `evaluate_semantic` when
    `config.settings_store.get_api_key()` returns `None`, so the report can
    surface "API key not configured" instead of the generic
    "not implemented" `evaluate_stub` reports for `--no-semantic`.
    """
    return Violation(
        rule_id=rule.rule_id,
        severity=rule.severity,
        auto_fixable=False,
        status=ViolationStatus.CHECK_FAILED,
        failure_reason="api_key_missing",
        message=rule.message,
    )


def _section_text(ast: Ast, rule: SemanticRule) -> tuple[str, str | None]:
    """Joined text of every paragraph the rule's selector resolves to (its
    `applies_to_section`/`paragraph_filter`/`exclude_patterns`, already
    excluding a section heading when `paragraph_filter` asks for that), plus
    the first matching paragraph's id to anchor a violation to.
    """
    paragraphs = select_paragraphs(ast, rule)
    if not paragraphs:
        return "", None
    return " ".join(p.text for p in paragraphs), paragraphs[0].id


def _keywords_line(ast: Ast, rule: SemanticRule) -> tuple[str, str | None]:
    for paragraph in select_paragraphs(ast, rule):
        if paragraph.text.strip().lower().startswith(_KEYWORDS_PREFIXES):
            return paragraph.text, paragraph.id
    return "", None


def _section_order(ast: Ast, _rule: SemanticRule) -> tuple[str, str | None]:
    """The detected section for each paragraph, in document order,
    collapsing consecutive repeats -- "title -> author -> abstract -> ..."."""
    order: list[str] = []
    anchor: str | None = None
    for paragraph in ast.paragraphs:
        if paragraph.section is None:
            continue
        if anchor is None:
            anchor = paragraph.id
        if not order or order[-1] != paragraph.section.value:
            order.append(paragraph.section.value)
    return " -> ".join(order), anchor


#: One text extractor per semantic rule -- each prompt asks a different
#: question about a different slice of the document, so there is no single
#: generic "the text this rule cares about" rule to derive this from.
_TEXT_EXTRACTORS: dict[str, Callable[[Ast, SemanticRule], tuple[str, str | None]]] = {
    "doc-order": _section_order,
    "abstract-structure": _section_text,
    "abstract-keywords-count": _keywords_line,
    "affiliation-content": _section_text,
    "result-text-before-figure": _section_text,
    "reference-style-vancouver-format": _section_text,
    "corresponding-author-content": _section_text,
}


def _prompt_template(rule: SemanticRule) -> str:
    if rule.prompt_template is not None:
        return rule.prompt_template
    assert rule.prompt_file is not None  # schema requires exactly one
    return load_prompt(rule.prompt_file)


def _render_prompt(rule: SemanticRule, template: str, text: str) -> str:
    if not rule.prompt_vars:
        return template
    return template.format(**{var: text for var in rule.prompt_vars})


def _verdict_to_violation(
    rule: SemanticRule, verdict: SemanticVerdict, anchor_paragraph_id: str | None
) -> Violation | None:
    if not verdict.violation:
        return None
    return Violation(
        rule_id=rule.rule_id,
        severity=rule.severity,
        auto_fixable=False,
        status=ViolationStatus.NEEDS_REVIEW,
        expected=rule.message,
        found=verdict.explanation,
        anchor_paragraph_id=anchor_paragraph_id,
        explanation=verdict.explanation,
        suggested_fix=verdict.suggested_fix,
        message=rule.message,
    )


def _check_failed(rule: SemanticRule, reason: str, anchor_paragraph_id: str | None) -> Violation:
    return Violation(
        rule_id=rule.rule_id,
        severity=rule.severity,
        auto_fixable=False,
        status=ViolationStatus.CHECK_FAILED,
        anchor_paragraph_id=anchor_paragraph_id,
        failure_reason=reason,
        message=rule.message,
    )


def build_evaluator(
    ast: Ast, client: SemanticClient, cache: SemanticCache
) -> Callable[[SemanticRule], Violation | None]:
    """A closure over one document, one client, and one cache -- `engine.py`
    calls the returned function once per semantic rule and knows nothing
    about any of the three.
    """

    def evaluate(rule: SemanticRule) -> Violation | None:
        extractor = _TEXT_EXTRACTORS.get(rule.rule_id)
        if extractor is None:
            return _check_failed(rule, "semantic_check_not_implemented", None)

        text, anchor = extractor(ast, rule)
        if not text.strip():
            return _check_failed(rule, "section_text_unavailable", anchor)

        template = _prompt_template(rule)
        cached = cache.get(rule.rule_id, template, text)
        if cached is not None:
            return _verdict_to_violation(rule, cached, anchor)

        prompt = _render_prompt(rule, template, text)
        result = client.check(prompt)
        if not result.ok or result.verdict is None:
            return _check_failed(rule, result.failure_reason or "unknown", anchor)

        cache.set(rule.rule_id, template, text, result.verdict)
        return _verdict_to_violation(rule, result.verdict, anchor)

    return evaluate


_PLACEHOLDER_RE = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")


def unsubstituted_placeholders(rendered_prompt: str) -> list[str]:
    """Any `{name}`-shaped text still present after rendering -- a prompt
    contract test asserts this is always empty."""
    return _PLACEHOLDER_RE.findall(rendered_prompt)


__all__ = [
    "SemanticCheckResult",
    "SemanticClient",
    "build_evaluator",
    "evaluate_api_key_missing",
    "evaluate_stub",
    "unsubstituted_placeholders",
]
