"""Positional fallback for front matter.

Title, author, and affiliation carry no heading at all -- there is nothing for
`headings.evaluate_heading` to match against -- and abstract's own heading
("Abstract") is too short and unstyled to reliably clear the structural score
on its own, so all four are resolved by a scored state machine over the
paragraphs preceding the first recognised *body* heading, not by fixed
indices: a manuscript that inserts an extra affiliation line, or omits the
"Abstract" heading text entirely, must not shift every subsequent label.

Order within front matter (title, then author, then abstract, then
affiliation) is treated as fixed for this template -- multi-journal support is
out of scope for v1 (spec section 2) -- but *where each one ends* is decided
by content signals: an explicit "Abstract"/"Summary" heading anchors the
abstract block, and an ORCID/email/superscript-numeral signal anchors
affiliation. Absent those signals, the module falls back to the narrowest
reasonable default (one paragraph for author, the last front-matter paragraph
for affiliation) rather than guessing further.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from manuscript_validator.models.ast import Paragraph
from manuscript_validator.models.enums import Section, SectionSource
from manuscript_validator.segmenter.headings import evaluate_heading

#: These four are always front matter for this template, regardless of
#: whether a rule config's `section_order` lists them first.
FRONT_MATTER_SECTIONS = (Section.TITLE, Section.AUTHOR, Section.ABSTRACT, Section.AFFILIATION)

_AFFILIATION_SCORE_THRESHOLD = 2


@dataclass(frozen=True)
class FrontMatterAssignment:
    section: Section
    confidence: float
    source: SectionSource


def _author_line_score(paragraph: Paragraph) -> int:
    text = paragraph.text.strip()
    score = 0
    if any(run.superscript for run in paragraph.runs):
        score += 2
    words = text.split()
    if 1 <= len(words) <= 20:
        score += 1
    if "," in text or " and " in text.lower():
        score += 1
    return score


def _affiliation_score(paragraph: Paragraph) -> int:
    lowered = paragraph.text.lower()
    score = 0
    if "orcid" in lowered or "email" in lowered or "@" in paragraph.text:
        score += 3
    first_run = paragraph.runs[0] if paragraph.runs else None
    if first_run is not None and first_run.superscript and first_run.text.strip().isdigit():
        score += 1
    return score


def resolve_front_matter(
    paragraphs: list[Paragraph], section_synonyms: Mapping[Section, list[str]]
) -> dict[str, FrontMatterAssignment]:
    """Assign title/author/abstract/affiliation labels within `paragraphs`,
    the run of paragraphs preceding the first recognised body heading."""
    assignments: dict[str, FrontMatterAssignment] = {}
    non_blank = [p for p in paragraphs if p.text.strip()]
    if not non_blank:
        return assignments

    assignments[non_blank[0].id] = FrontMatterAssignment(
        Section.TITLE, 0.7, SectionSource.POSITIONAL
    )

    abstract_heading_idx: int | None = None
    for i, paragraph in enumerate(non_blank[1:], start=1):
        match = evaluate_heading(paragraph, section_synonyms)
        if match.is_heading and match.section is Section.ABSTRACT:
            abstract_heading_idx = i
            assignments[paragraph.id] = FrontMatterAssignment(
                Section.ABSTRACT, match.confidence, SectionSource.HEADING
            )
            break

    author_end = (
        abstract_heading_idx if abstract_heading_idx is not None else min(2, len(non_blank))
    )
    for paragraph in non_blank[1:author_end]:
        score = _author_line_score(paragraph)
        assignments[paragraph.id] = FrontMatterAssignment(
            Section.AUTHOR, 0.5 + 0.1 * min(score, 4), SectionSource.POSITIONAL
        )

    remainder_start = (
        (abstract_heading_idx + 1) if abstract_heading_idx is not None else author_end
    )
    remainder = non_blank[remainder_start:]
    affiliation_scores = (_affiliation_score(p) for p in remainder)
    affiliation_idx = next(
        (i for i, score in enumerate(affiliation_scores) if score >= _AFFILIATION_SCORE_THRESHOLD),
        None,
    )
    boundary = affiliation_idx if affiliation_idx is not None else max(len(remainder) - 1, 0)
    for i, paragraph in enumerate(remainder):
        if i < boundary:
            assignments[paragraph.id] = FrontMatterAssignment(
                Section.ABSTRACT, 0.6, SectionSource.POSITIONAL
            )
        else:
            confidence = 0.9 if i == affiliation_idx else 0.6
            assignments[paragraph.id] = FrontMatterAssignment(
                Section.AFFILIATION, confidence, SectionSource.POSITIONAL
            )
    return assignments


__all__ = ["FRONT_MATTER_SECTIONS", "FrontMatterAssignment", "resolve_front_matter"]
