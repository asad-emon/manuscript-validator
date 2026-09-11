"""Document AST (spec section 5.1).

A pure-data snapshot. It holds no references to python-docx or lxml objects,
which is what makes `copy.deepcopy` safe and meaningful here -- the deep copy
spec section 8 asks for works on this, it just must never be applied to a
`Document`. Write-back is `parser.binding.ElementIndex`'s job; see
docs/decisions.md (C1, C2).

Dataclasses rather than pydantic: there are thousands of these per document,
they are mutable, and they are produced internally, so per-assignment
validation would be pure overhead. `slots=True` keeps run-level memory sane.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from manuscript_validator.models.enums import (
    CaptionPosition,
    FormattingSource,
    NumberingStyle,
    Section,
    SectionSource,
)


@dataclass(slots=True)
class Run:
    """A run of text with uniform formatting.

    Formatting fields hold the *effective* value -- resolved through the style
    chain, document defaults, and the theme -- not the raw run property, which
    is None whenever formatting is inherited. `*_source` records where each
    value came from, which is what lets a violation report say something more
    useful than "found: None".
    """

    text: str = ""
    font_name: str | None = None
    font_size_pt: float | None = None
    bold: bool | None = None
    italic: bool | None = None
    superscript: bool | None = None

    #: True when the characters are literally typed in caps. Distinct from
    #: `all_caps_property`, which is the w:caps rendering transform -- the
    #: journal rule requires literal uppercase, so the two must not be conflated.
    uppercase_literal: bool = False
    all_caps_property: bool = False

    font_name_source: FormattingSource = FormattingSource.UNRESOLVED
    font_size_source: FormattingSource = FormattingSource.UNRESOLVED
    bold_source: FormattingSource = FormattingSource.UNRESOLVED
    italic_source: FormattingSource = FormattingSource.UNRESOLVED

    def to_dict(self) -> dict[str, Any]:
        """Serialise in spec section 5.1 key order, extensions last."""
        return {
            "text": self.text,
            "font_name": self.font_name,
            "font_size_pt": self.font_size_pt,
            "bold": self.bold,
            "italic": self.italic,
            "superscript": self.superscript,
            "uppercase_literal": self.uppercase_literal,
            "all_caps_property": self.all_caps_property,
        }


@dataclass(slots=True)
class Paragraph:
    """One paragraph, including paragraphs inside table cells.

    Cell paragraphs live in this same flat list rather than hanging off `Table`
    (as spec section 5.1 implies) so every run-level rule reaches them without
    a special case -- `table-text-size` has nothing to check otherwise.
    """

    id: str
    text: str = ""
    style_name: str = ""
    section: Section | None = None
    runs: list[Run] = field(default_factory=list)
    alignment: str | None = None
    is_table_caption: bool = False
    is_figure_caption: bool = False
    line_break_after: bool = False

    #: Set when this paragraph is inside a table cell.
    in_table: str | None = None
    cell: tuple[int, int] | None = None

    section_confidence: float = 0.0
    section_source: SectionSource = SectionSource.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "text": self.text,
            "style_name": self.style_name,
            "section": self.section.value if self.section else None,
            "runs": [run.to_dict() for run in self.runs],
            "alignment": self.alignment,
            "is_table_caption": self.is_table_caption,
            "line_break_after": self.line_break_after,
        }
        if self.is_figure_caption:
            data["is_figure_caption"] = True
        if self.in_table is not None:
            data["in_table"] = self.in_table
            data["cell"] = list(self.cell) if self.cell else None
        return data


@dataclass(slots=True)
class Table:
    id: str
    caption_paragraph_id: str | None = None
    caption_position: CaptionPosition | None = None
    numbering_style: NumberingStyle | None = None
    caption_number: str | None = None
    cell_font_size_pt: float | None = None
    referenced_in_paragraph_ids: list[str] = field(default_factory=list)
    cell_paragraph_ids: list[str] = field(default_factory=list)
    #: Word auto-captions carry their number in a SEQ field with a cached
    #: result, so patching the visible text is futile -- Word re-renders it.
    caption_from_field: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "caption_paragraph_id": self.caption_paragraph_id,
            "caption_position": self.caption_position.value if self.caption_position else None,
            "numbering_style": self.numbering_style.value if self.numbering_style else None,
            "cell_font_size_pt": self.cell_font_size_pt,
            "referenced_in_paragraph_ids": list(self.referenced_in_paragraph_ids),
        }


@dataclass(slots=True)
class Figure:
    id: str
    paragraph_id: str | None = None
    caption_paragraph_id: str | None = None
    caption_position: CaptionPosition | None = None
    numbering_style: NumberingStyle | None = None
    caption_number: str | None = None
    referenced_in_paragraph_ids: list[str] = field(default_factory=list)
    caption_from_field: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "caption_paragraph_id": self.caption_paragraph_id,
            "caption_position": self.caption_position.value if self.caption_position else None,
            "numbering_style": self.numbering_style.value if self.numbering_style else None,
            "referenced_in_paragraph_ids": list(self.referenced_in_paragraph_ids),
        }


@dataclass(slots=True)
class Ast:
    """The parsed document.

    `document_id` is the SHA-256 of the source bytes rather than a random UUID:
    it is stable across runs and doubles as the semantic cache's document key.
    """

    paragraphs: list[Paragraph] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)
    document_id: str = ""

    def paragraph_by_id(self, paragraph_id: str) -> Paragraph | None:
        for paragraph in self.paragraphs:
            if paragraph.id == paragraph_id:
                return paragraph
        return None

    def paragraphs_in_section(self, section: Section) -> list[Paragraph]:
        return [p for p in self.paragraphs if p.section == section]

    def to_dict(self) -> dict[str, Any]:
        return {
            "paragraphs": [p.to_dict() for p in self.paragraphs],
            "tables": [t.to_dict() for t in self.tables],
            "figures": [f.to_dict() for f in self.figures],
        }
