"""Heading detection and vocabulary matching.

Detection is a weighted score, not a branch chain: style name, all-bold runs,
literal uppercase, word count, and terminal punctuation each contribute, and a
vocabulary hit on the ruleset's `section_synonyms` contributes on top of those.
`outlineLvl` is not modelled on `Paragraph` (Task 4 closed before this task
started), so style name alone carries that signal's weight.

Matching normalises (NFKC -> casefold -> strip leading enumeration -> strip
trailing colon -> collapse whitespace) then escalates exact -> token-set ->
fuzzy. Token-set matching is what makes "materials and methods" equivalent to
"methods and materials" without a special case. Fuzzy matching only runs for a
paragraph that already scored as a heading on its structural signals alone --
running `SequenceMatcher` against every paragraph in the document would let
ordinary prose that happens to resemble a section name (a references-list
entry, a caption) get relabelled.

The synonym table and section order live in the rule config JSON, not here:
heading vocabulary is the most journal-specific thing in the system, and spec
section 2's "a second template is a config addition" is false otherwise.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher

from manuscript_validator.models.ast import Paragraph
from manuscript_validator.models.enums import Section

HEADING_SCORE_THRESHOLD = 3
FUZZY_MATCH_THRESHOLD = 0.85

_HEADING_STYLE_NAME_RE = re.compile(r"^heading\s*\d*$", re.IGNORECASE)
_LEADING_ENUMERATION_RE = re.compile(
    r"^\s*(?:\d+|[ivxlcdm]+|[a-z])[.)]\s+", re.IGNORECASE
)


@dataclass(frozen=True)
class HeadingMatch:
    """The result of scoring one paragraph as a candidate heading.

    `section` and `match_kind` are only meaningful when `is_heading` is True --
    a structural score below threshold is not "a heading of unknown section",
    it is not a heading at all.
    """

    is_heading: bool
    section: Section | None
    confidence: float
    score: int
    match_kind: str  # "exact" | "token_set" | "fuzzy" | "none"


def normalize_heading_text(text: str) -> str:
    """NFKC -> casefold -> strip leading enumeration -> strip trailing colon
    -> collapse whitespace, so "1. Introduction:" and "INTRODUCTION" compare
    equal to the vocabulary entry "introduction"."""
    normalized = unicodedata.normalize("NFKC", text).casefold().strip()
    normalized = _LEADING_ENUMERATION_RE.sub("", normalized)
    normalized = normalized.rstrip(":").strip()
    return re.sub(r"\s+", " ", normalized)


def _structural_score(paragraph: Paragraph, text: str) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []

    if _HEADING_STYLE_NAME_RE.match(paragraph.style_name or ""):
        score += 3
        signals.append("style_name")

    if paragraph.runs and all(run.bold for run in paragraph.runs):
        score += 2
        signals.append("all_bold")

    if bool(re.search(r"[A-Za-z]", text)) and text == text.upper():
        score += 2
        signals.append("uppercase")

    if len(text.split()) <= 8:
        score += 1
        signals.append("short")

    if not text.rstrip().endswith("."):
        score += 1
        signals.append("no_terminal_period")

    return score, signals


def _exact_or_token_set_match(
    normalized: str, section_synonyms: Mapping[Section, list[str]]
) -> tuple[Section, float, str] | None:
    tokens = frozenset(normalized.split())
    token_set_hit: Section | None = None
    for section, variants in section_synonyms.items():
        for variant in variants:
            normalized_variant = normalize_heading_text(variant)
            if normalized == normalized_variant:
                return section, 1.0, "exact"
            if token_set_hit is None and tokens and tokens == frozenset(
                normalized_variant.split()
            ):
                token_set_hit = section
    if token_set_hit is not None:
        return token_set_hit, 0.95, "token_set"
    return None


def _fuzzy_match(
    normalized: str, section_synonyms: Mapping[Section, list[str]]
) -> tuple[Section, float] | None:
    best: tuple[Section, float] | None = None
    for section, variants in section_synonyms.items():
        for variant in variants:
            ratio = SequenceMatcher(None, normalized, normalize_heading_text(variant)).ratio()
            if ratio >= FUZZY_MATCH_THRESHOLD and (best is None or ratio > best[1]):
                best = (section, ratio)
    return best


def evaluate_heading(
    paragraph: Paragraph, section_synonyms: Mapping[Section, list[str]]
) -> HeadingMatch:
    """Score `paragraph` as a candidate section heading against the ruleset's
    vocabulary. `section_synonyms` normally comes from `Ruleset.section_synonyms`."""
    text = paragraph.text.strip()
    if not text:
        return HeadingMatch(False, None, 0.0, 0, "none")

    structural_score, _signals = _structural_score(paragraph, text)
    normalized = normalize_heading_text(text)

    section: Section | None = None
    confidence = 0.0
    match_kind = "none"
    score = structural_score

    exact_or_token_set = _exact_or_token_set_match(normalized, section_synonyms)
    if exact_or_token_set is not None:
        section, confidence, match_kind = exact_or_token_set
        score += 3
    elif structural_score >= HEADING_SCORE_THRESHOLD:
        fuzzy = _fuzzy_match(normalized, section_synonyms)
        if fuzzy is not None:
            section, confidence = fuzzy
            match_kind = "fuzzy"
            score += 3

    is_heading = score >= HEADING_SCORE_THRESHOLD
    if not is_heading:
        return HeadingMatch(False, None, 0.0, score, "none")
    return HeadingMatch(True, section, confidence, score, match_kind)


__all__ = [
    "FUZZY_MATCH_THRESHOLD",
    "HEADING_SCORE_THRESHOLD",
    "HeadingMatch",
    "evaluate_heading",
    "normalize_heading_text",
]
