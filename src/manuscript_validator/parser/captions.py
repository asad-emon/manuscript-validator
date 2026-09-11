"""Table and figure caption detection by proximity and pattern.

A caption is identified by text pattern (`"Table <roman>"`, `"Fig(ure) <arabic>"`)
on the paragraph immediately before or after the anchor element (a `<w:tbl>`
for tables, the image's own `<w:p>` for figures) -- python-docx has no
first-class caption concept, and the spec's own guidance (section 5.1) is
exactly this proximity heuristic. A caption sitting in a merged first row of
the table itself is reported as `position: "inside"` and is never
auto-fixable: repositioning it is a structural edit, not a formatting one.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from lxml import etree

from manuscript_validator.models.enums import CaptionPosition, NumberingStyle
from manuscript_validator.parser.effective import paragraph_text

#: The number must be followed by `.` or `:` -- mandatory, not optional. A
#: narrative sentence like "Table I summarizes the primary outcomes." starts
#: exactly like a caption; only the punctuation immediately after the number
#: (as in "Table I. Summary...") tells the two apart.
_TABLE_CAPTION_RE = re.compile(r"^\s*Table\s+([IVXLCDM0-9]+)[.:]", re.IGNORECASE)
_FIGURE_CAPTION_RE = re.compile(r"^\s*Fig(?:ure)?\.?\s+([IVXLCDM0-9]+)[.:]", re.IGNORECASE)
_ROMAN_RE = re.compile(r"^[IVXLCDM]+$", re.IGNORECASE)


@dataclass(frozen=True)
class CaptionMatch:
    element: Any
    position: CaptionPosition
    prefix: str  # "Table" or "Figure", as matched
    number_token: str  # e.g. "I", "1"
    numbering_style: NumberingStyle
    text: str


def classify_numbering(token: str) -> NumberingStyle:
    if token.isdigit():
        return NumberingStyle.ARABIC
    if _ROMAN_RE.match(token):
        return NumberingStyle.ROMAN
    return NumberingStyle.OTHER


_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_ROMAN_NUMERALS = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
    (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)


def roman_to_int(token: str) -> int | None:
    """`None` for a malformed token rather than raising -- callers (a
    numbering-sequence check, a numbering-style fix) treat "couldn't parse"
    as "doesn't match", not as a crash."""
    total = 0
    previous = 0
    for char in reversed(token.upper()):
        value = _ROMAN_VALUES.get(char)
        if value is None:
            return None
        total = total - value if value < previous else total + value
        previous = max(previous, value)
    return total or None


def int_to_roman(value: int) -> str:
    result = []
    remaining = value
    for magnitude, symbol in _ROMAN_NUMERALS:
        count, remaining = divmod(remaining, magnitude)
        result.append(symbol * count)
    return "".join(result)


def numeral_value(token: str | None, style: NumberingStyle | None) -> int | None:
    """The integer value of a caption number, honouring its detected style --
    `"4"` (arabic) and `"IV"` (roman) both mean 4, but a bare digit string
    misread as roman (or vice versa) must not silently produce a value."""
    if token is None:
        return None
    if style is NumberingStyle.ARABIC and token.isdigit():
        return int(token)
    if style is NumberingStyle.ROMAN:
        return roman_to_int(token)
    return None


def _is_paragraph(el: Any) -> bool:
    return el is not None and etree.QName(el).localname == "p"


def _match(pattern: re.Pattern[str], el: Any) -> re.Match[str] | None:
    if not _is_paragraph(el):
        return None
    return pattern.match(paragraph_text(el))


def _build_match(
    pattern: re.Pattern[str], el: Any, position: CaptionPosition, prefix: str
) -> CaptionMatch | None:
    match = _match(pattern, el)
    if match is None:
        return None
    token = match.group(1)
    return CaptionMatch(
        element=el,
        position=position,
        prefix=prefix,
        number_token=token,
        numbering_style=classify_numbering(token),
        text=paragraph_text(el),
    )


def find_table_caption(table_el: Any) -> CaptionMatch | None:
    """Search, in order: the paragraph directly above the table, the paragraph
    directly below it, then the table's own first cell (a merged caption row)."""
    above = _build_match(_TABLE_CAPTION_RE, table_el.getprevious(), CaptionPosition.ABOVE, "Table")
    if above is not None:
        return above
    below = _build_match(_TABLE_CAPTION_RE, table_el.getnext(), CaptionPosition.BELOW, "Table")
    if below is not None:
        return below
    first_cell_paragraphs = table_el.xpath(".//w:tr[1]/w:tc[1]/w:p")
    first_cell_paragraph = first_cell_paragraphs[0] if first_cell_paragraphs else None
    return _build_match(_TABLE_CAPTION_RE, first_cell_paragraph, CaptionPosition.INSIDE, "Table")


def find_figure_caption(image_paragraph_el: Any) -> CaptionMatch | None:
    """Search the paragraphs directly below, then directly above, the image's
    own paragraph -- a figure caption belongs below per the journal template,
    so that is checked first."""
    below = _build_match(
        _FIGURE_CAPTION_RE, image_paragraph_el.getnext(), CaptionPosition.BELOW, "Figure"
    )
    if below is not None:
        return below
    return _build_match(
        _FIGURE_CAPTION_RE, image_paragraph_el.getprevious(), CaptionPosition.ABOVE, "Figure"
    )


def find_citing_paragraph_ids(
    caption: CaptionMatch, candidates: Iterable[tuple[str, str]]
) -> list[str]:
    """Ids of paragraphs (other than the caption itself) whose text cites this
    table/figure by the same prefix and number the caption uses."""
    pattern = re.compile(
        rf"\b{re.escape(caption.prefix)}\s+{re.escape(caption.number_token)}\b", re.IGNORECASE
    )
    return [pid for pid, text in candidates if pattern.search(text)]


__all__ = [
    "CaptionMatch",
    "classify_numbering",
    "find_citing_paragraph_ids",
    "find_figure_caption",
    "find_table_caption",
    "int_to_roman",
    "numeral_value",
    "roman_to_int",
]
