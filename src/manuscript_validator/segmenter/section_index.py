"""Section -> ordered paragraph ids, with confidence and provenance.

`segment()` is the segmenter's single entry point: one pass over
`Ast.paragraphs` in document order, assigning `Paragraph.section`,
`.section_confidence`, and `.section_source` in place, plus a
`SegmentationResult` recording which sections were actually found. Table-cell
paragraphs never run through heading detection -- a bold, short cell like
"Metric" scores as a heading by every structural signal `headings.py` uses --
they simply inherit whatever section is active where their table sits.

Also owns the missing-section contract. A section that is absent makes
`select_nodes` return an empty list, which would let FR-11 pass on a
manuscript with no title at all; `missing_sections` and
`generate_section_present_rules` close that gap by turning "found nothing" into
a violation in its own right rather than a silent pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from manuscript_validator.models.ast import Ast, Paragraph
from manuscript_validator.models.enums import (
    CheckType,
    NodeType,
    Operator,
    Section,
    SectionSource,
    SelectorScope,
    Severity,
)
from manuscript_validator.rules.schema import Condition, DeterministicRule, Ruleset, Selector
from manuscript_validator.segmenter.headings import evaluate_heading
from manuscript_validator.segmenter.heuristics import FRONT_MATTER_SECTIONS, resolve_front_matter

#: Below this many recognised body headings, section boundaries cannot be
#: trusted -- a title mislabelled as a heading would otherwise cascade into
#: dozens of garbage violations rather than one honest "could not segment".
MIN_BODY_HEADINGS = 4

#: A missing section's "attribute" in the synthesized rule's condition. There
#: is no node to select for something absent, so unlike every other
#: deterministic rule this one is read by Task 6's engine as a lookup into
#: `SegmentationResult.missing_sections` rather than a paragraph/run field.
_SECTION_PRESENT_ATTRIBUTE_PREFIX = "section:"


@dataclass(frozen=True)
class SegmentationResult:
    section_paragraph_ids: dict[Section, list[str]]
    detected_sections: frozenset[Section]
    missing_sections: frozenset[Section]
    body_heading_count: int
    #: True when fewer than `MIN_BODY_HEADINGS` body headings were recognised
    #: at all -- segmentation degraded to front matter only, and body rules
    #: should report `check_failed`, not run against guessed boundaries.
    front_matter_only: bool
    degraded_reason: str | None = field(default=None)


def _split_front_matter(
    paragraphs: list[Paragraph], section_synonyms: dict[Section, list[str]]
) -> int:
    """Index of the first paragraph belonging to a recognised body heading --
    i.e. where front matter ends. Table-cell paragraphs are skipped: a table
    can never appear before the first body heading in this template."""
    for i, paragraph in enumerate(paragraphs):
        if paragraph.in_table is not None:
            continue
        match = evaluate_heading(paragraph, section_synonyms)
        is_body_heading = (
            match.is_heading and match.section is not None
            and match.section not in FRONT_MATTER_SECTIONS
        )
        if is_body_heading:
            return i
    return len(paragraphs)


def segment(ast: Ast, ruleset: Ruleset) -> SegmentationResult:
    """Label every paragraph in `ast` with its section, in place, and report
    which of `ruleset.required_sections` were actually found."""
    paragraphs = ast.paragraphs
    section_synonyms = ruleset.section_synonyms
    body_start = _split_front_matter(paragraphs, section_synonyms)

    section_paragraph_ids: dict[Section, list[str]] = {}

    def _assign(
        paragraph: Paragraph, section: Section, confidence: float, source: SectionSource
    ) -> None:
        paragraph.section = section
        paragraph.section_confidence = confidence
        paragraph.section_source = source
        section_paragraph_ids.setdefault(section, []).append(paragraph.id)

    front_assignments = resolve_front_matter(paragraphs[:body_start], section_synonyms)
    for paragraph in paragraphs[:body_start]:
        assignment = front_assignments.get(paragraph.id)
        if assignment is not None:
            _assign(paragraph, assignment.section, assignment.confidence, assignment.source)

    current_section: Section | None = None
    body_heading_count = 0
    for paragraph in paragraphs[body_start:]:
        if paragraph.in_table is not None:
            if current_section is not None:
                _assign(paragraph, current_section, 0.4, SectionSource.INHERITED)
            continue

        match = evaluate_heading(paragraph, section_synonyms)
        if match.is_heading and match.section is not None:
            current_section = match.section
            body_heading_count += 1
            _assign(paragraph, match.section, match.confidence, SectionSource.HEADING)
        elif current_section is not None:
            _assign(paragraph, current_section, 0.5, SectionSource.INHERITED)

    detected_sections = frozenset(
        section for section, ids in section_paragraph_ids.items() if ids
    )
    missing_sections = frozenset(ruleset.required_sections) - detected_sections
    front_matter_only = body_heading_count < MIN_BODY_HEADINGS

    return SegmentationResult(
        section_paragraph_ids=section_paragraph_ids,
        detected_sections=detected_sections,
        missing_sections=missing_sections,
        body_heading_count=body_heading_count,
        front_matter_only=front_matter_only,
        degraded_reason="section boundaries undetected" if front_matter_only else None,
    )


def generate_section_present_rules(ruleset: Ruleset) -> list[DeterministicRule]:
    """One `section-present-<name>` rule per required section.

    `acknowledgement` is excluded per spec section 6 by never being in
    `required_sections` to begin with, so no special case is needed here.
    """
    rules: list[DeterministicRule] = []
    for section in ruleset.required_sections:
        rules.append(
            DeterministicRule(
                rule_id=f"section-present-{section.value}",
                category="structure",
                message=f"Required section '{section.value}' was not found.",
                severity=Severity.HIGH,
                applies_to_section=[],
                selector=Selector(node_type=NodeType.DOCUMENT, scope=SelectorScope.FIRST),
                check_type=CheckType.DETERMINISTIC,
                condition=Condition(
                    attribute=f"{_SECTION_PRESENT_ATTRIBUTE_PREFIX}{section.value}",
                    operator=Operator.IS_NON_EMPTY,
                ),
                auto_fixable=False,
                expected_repr=f"section '{section.value}' present",
            )
        )
    return rules


__all__ = [
    "MIN_BODY_HEADINGS",
    "SegmentationResult",
    "generate_section_present_rules",
    "segment",
]
