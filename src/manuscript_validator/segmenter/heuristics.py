"""Positional fallback for front matter.

Title carries no heading at all -- there is nothing for
`headings.evaluate_heading` to match against -- and abstract's own heading
("Abstract") is too short and unstyled to reliably clear the structural score
on its own, so both are resolved by a scored state machine over the
paragraphs preceding the first recognised *body* heading, not by fixed
indices: a manuscript that inserts an extra affiliation line, or omits the
"Abstract" heading text entirely, must not shift every subsequent label.

Author and affiliation are **not** separated positionally at all. Five
real-world submissions supplied against this task (`tests/fixtures/real/`)
all place institutional/ORCID/email content for each author *directly under
the author line, before the abstract* -- not after it, as the compliant
fixture (built from the spec's assumed template) does. An earlier version of
this module defaulted "whatever front-matter paragraph has no stronger signal"
to affiliation, which produced a real false positive: a single-paragraph
abstract immediately followed by a "Keywords:" line had its abstract body
paragraph mislabelled affiliation, purely because it happened to be the last
paragraph before an already-claimed keywords line. Content signals (an
ORCID/email string, or a paragraph opening with a superscript digit -- the
standard numbered-affiliation-footnote convention) are scanned across the
*entire* front matter, before and after the abstract heading alike, and only
a positive hit is ever labelled affiliation. Everything else in the author
region defaults to author; everything else after the abstract heading
defaults to abstract. Nothing is labelled affiliation on position alone --
if no signal fires anywhere, affiliation simply is not detected, and
`SegmentationResult.missing_sections` reports that honestly rather than
`resolve_front_matter` fabricating a guess.
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
_KEYWORDS_PREFIXES = ("keywords", "key words", "keyword")


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


def _looks_like_keywords(paragraph: Paragraph) -> bool:
    return paragraph.text.strip().lower().startswith(_KEYWORDS_PREFIXES)


def _affiliation_score(paragraph: Paragraph) -> int:
    lowered = paragraph.text.lower()
    score = 0
    if "orcid" in lowered or "email" in lowered or "@" in paragraph.text:
        score += 3
    first_run = paragraph.runs[0] if paragraph.runs else None
    # A paragraph opening on a bare superscript digit is, on its own, the
    # standard numbered-affiliation-footnote convention -- real samples carry
    # it with no ORCID/email in sight, so it must clear the threshold alone.
    if first_run is not None and first_run.superscript and first_run.text.strip().isdigit():
        score += 2
    return score


def _classify_non_heading(
    paragraph: Paragraph, *, default: Section, default_confidence: float
) -> FrontMatterAssignment:
    if _looks_like_keywords(paragraph):
        return FrontMatterAssignment(Section.ABSTRACT, 0.9, SectionSource.POSITIONAL)
    if _affiliation_score(paragraph) >= _AFFILIATION_SCORE_THRESHOLD:
        return FrontMatterAssignment(Section.AFFILIATION, 0.9, SectionSource.POSITIONAL)
    if default is Section.AUTHOR:
        score = _author_line_score(paragraph)
        confidence = 0.5 + 0.1 * min(score, 4)
        return FrontMatterAssignment(Section.AUTHOR, confidence, SectionSource.POSITIONAL)
    return FrontMatterAssignment(default, default_confidence, SectionSource.POSITIONAL)


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

    author_region_end = abstract_heading_idx if abstract_heading_idx is not None else len(non_blank)
    for paragraph in non_blank[1:author_region_end]:
        assignments[paragraph.id] = _classify_non_heading(
            paragraph, default=Section.AUTHOR, default_confidence=0.5
        )

    remainder_start = (
        (abstract_heading_idx + 1) if abstract_heading_idx is not None else author_region_end
    )
    for paragraph in non_blank[remainder_start:]:
        assignments[paragraph.id] = _classify_non_heading(
            paragraph, default=Section.ABSTRACT, default_confidence=0.6
        )

    return assignments


__all__ = ["FRONT_MATTER_SECTIONS", "FrontMatterAssignment", "resolve_front_matter"]
