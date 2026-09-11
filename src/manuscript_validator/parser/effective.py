"""Effective formatting resolution and canonical text extraction.

The highest-risk module in the project. `run.font.name` returns None whenever
formatting is inherited from a style, which is the normal case in a real
manuscript, so every font check would report `found: None` without this.

Resolution order, highest priority first:
    run w:rPr -> character style -> paragraph style + w:basedOn chain
    -> w:docDefaults -> theme fonts in word/theme/theme1.xml

Each step is tried in full (explicit value *and*, for fonts, a theme
reference) before falling through to the next: a level that specifies
*something* stops the walk there, matching how Word itself resolves
formatting rather than checking one attribute at a time across all levels.

`paragraph_text` is the single canonical text extractor. Every caller -- word
counts, segmentation, caption matching, the Gemini payload -- must use it;
divergent extraction across modules produces inconsistent results that are
miserable to debug.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from docx.document import Document as DocumentObject
from docx.oxml.ns import qn
from docx.text.font import Font
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from lxml import etree

from manuscript_validator.models.enums import FormattingSource

_MAX_STYLE_DEPTH = 20
_DRAWING_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_THEME_RELTYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"

#: `w:rFonts` theme attributes that point into `theme1.xml`'s font scheme.
_THEME_FONT_ATTRS = ("asciiTheme", "hAnsiTheme", "cstheme", "eastAsiaTheme")


@dataclass(frozen=True)
class Resolved:
    value: Any
    source: FormattingSource


class _StaticRPrHolder:
    """Duck-types the `.rPr` surface `docx.text.font.Font` expects.

    `Font` only ever reads `self._element.rPr` -- it works unmodified against
    a run, a style, or (via this holder) `w:docDefaults/w:rPrDefault/w:rPr`,
    which has no python-docx wrapper of its own.
    """

    def __init__(self, rpr: Any | None) -> None:
        self.rPr = rpr


def run_text(r_el: Any) -> str:
    """The text of a single `<w:r>` element, `w:tab`/`w:br`/`w:noBreakHyphen`
    included (`CT_R.text` already translates each to its text equivalent) and
    NBSP normalized to an ordinary space."""
    return str(r_el.text).replace("\xa0", " ")


def paragraph_text(p_el: Any) -> str:
    """The canonical plain-text rendering of a `<w:p>` element.

    Walks `.//w:r[not(ancestor::w:rPr)]` so text inside `w:ins` and
    `w:hyperlink` is included and text inside a `w:rPrChange` snapshot is not.
    Without `run_text`'s tab/break normalization, "A<tab>B" would concatenate
    into the single word "AB" -- both word counts and caption/citation regexes
    depend on the boundary surviving.
    """
    return "".join(run_text(r_el) for r_el in p_el.xpath(".//w:r[not(ancestor::w:rPr)]"))


def has_trailing_line_break(p_el: Any) -> bool:
    """True if the paragraph's last content run carries a `<w:br/>` -- the
    journal template's convention for a manual break after a heading, built
    via `paragraph.add_run().add_break()`. Checked on the *last* run only:
    a `w:br` earlier in the paragraph is a mid-paragraph line wrap, not a
    trailing one."""
    run_elements = p_el.xpath(".//w:r[not(ancestor::w:rPr)]")
    if not run_elements:
        return False
    return run_elements[-1].find(qn("w:br")) is not None


def is_uppercase_literal(text: str) -> bool:
    """True if `text` is actually typed in caps, not rendered so via a style
    transform. Distinct from `w:caps` (`all_caps_property`): the journal rule
    this backs requires the former."""
    return bool(re.search(r"[A-Za-z]", text)) and text == text.upper()


def _style_chain(style_elm: Any) -> Iterator[Any]:
    """Walk a style's `w:basedOn` chain, depth-capped and cycle-guarded.

    A malformed or hand-edited styles.xml can reference a style as its own
    (indirect) ancestor; without the `seen` guard that is an infinite loop.
    """
    seen: set[str] = set()
    depth = 0
    while style_elm is not None and depth < _MAX_STYLE_DEPTH:
        style_id = style_elm.styleId
        if style_id in seen:
            return
        seen.add(style_id)
        yield style_elm
        style_elm = style_elm.base_style
        depth += 1


class EffectiveFormattingResolver:
    """Resolves one document's run formatting through the full inheritance
    chain. Build once per document -- theme parsing happens once here."""

    def __init__(self, document: DocumentObject) -> None:
        self._doc_defaults_holder = _StaticRPrHolder(self._find_doc_defaults_rpr(document))
        self._theme_fonts = self._load_theme_fonts(document)

    @staticmethod
    def _find_doc_defaults_rpr(document: DocumentObject) -> Any | None:
        styles_elm = document.styles.element
        doc_defaults = styles_elm.find(qn("w:docDefaults"))
        if doc_defaults is None:
            return None
        rpr_default = doc_defaults.find(qn("w:rPrDefault"))
        if rpr_default is None:
            return None
        return rpr_default.find(qn("w:rPr"))

    @staticmethod
    def _load_theme_fonts(document: DocumentObject) -> dict[str, str]:
        for rel in document.part.rels.values():
            if rel.is_external or rel.reltype != _THEME_RELTYPE:
                continue
            root = etree.fromstring(rel.target_part.blob)
            fonts: dict[str, str] = {}
            for slot in ("major", "minor"):
                path = (
                    f".//{{{_DRAWING_A_NS}}}fontScheme"
                    f"/{{{_DRAWING_A_NS}}}{slot}Font/{{{_DRAWING_A_NS}}}latin"
                )
                latin = root.find(path)
                typeface = latin.get("typeface") if latin is not None else None
                if typeface:
                    fonts[slot] = typeface
            return fonts
        return {}

    def _chain_for(self, run: Run, paragraph: Paragraph) -> list[tuple[Any, FormattingSource]]:
        chain: list[tuple[Any, FormattingSource]] = [(run._r, FormattingSource.RUN)]
        character_style = run.style
        if character_style is not None:
            for style_elm in _style_chain(character_style.element):
                chain.append((style_elm, FormattingSource.CHARACTER_STYLE))
        paragraph_style = paragraph.style
        if paragraph_style is not None:
            for style_elm in _style_chain(paragraph_style.element):
                chain.append((style_elm, FormattingSource.PARAGRAPH_STYLE))
        chain.append((self._doc_defaults_holder, FormattingSource.DOC_DEFAULT))
        return chain

    def _theme_font_name(self, r_fonts: Any) -> str | None:
        for attr in _THEME_FONT_ATTRS:
            theme_ref = r_fonts.get(qn(f"w:{attr}"))
            if not theme_ref:
                continue
            slot = "major" if theme_ref.startswith("major") else "minor"
            typeface = self._theme_fonts.get(slot)
            if typeface:
                return typeface
        return None

    def resolve_font_name(self, run: Run, paragraph: Paragraph) -> Resolved:
        for element, source in self._chain_for(run, paragraph):
            rpr = element.rPr
            if rpr is None:
                continue
            r_fonts = rpr.rFonts
            if r_fonts is None:
                continue
            theme_name = self._theme_font_name(r_fonts)
            if theme_name is not None:
                return Resolved(theme_name, FormattingSource.THEME)
            if r_fonts.ascii:
                return Resolved(r_fonts.ascii, source)
        return Resolved(None, FormattingSource.UNRESOLVED)

    def resolve_font_size(self, run: Run, paragraph: Paragraph) -> Resolved:
        for element, source in self._chain_for(run, paragraph):
            size = Font(element).size
            if size is not None:
                return Resolved(size.pt, source)
        return Resolved(None, FormattingSource.UNRESOLVED)

    def _resolve_tri_state(self, run: Run, paragraph: Paragraph, attr: str) -> Resolved:
        """Bold/italic/superscript/caps have no "unset" rendering: absence at
        every level in the chain means Word renders the flag off, not that
        the value is unknown -- unlike font name/size, which can genuinely
        have nothing to fall back to. So the walk-off-the-end case resolves
        to `False`, not `None`."""
        for element, source in self._chain_for(run, paragraph):
            value = getattr(Font(element), attr)
            if value is not None:
                return Resolved(value, source)
        return Resolved(False, FormattingSource.UNRESOLVED)

    def resolve_bold(self, run: Run, paragraph: Paragraph) -> Resolved:
        return self._resolve_tri_state(run, paragraph, "bold")

    def resolve_italic(self, run: Run, paragraph: Paragraph) -> Resolved:
        return self._resolve_tri_state(run, paragraph, "italic")

    def resolve_superscript(self, run: Run, paragraph: Paragraph) -> Resolved:
        return self._resolve_tri_state(run, paragraph, "superscript")

    def resolve_all_caps(self, run: Run, paragraph: Paragraph) -> Resolved:
        return self._resolve_tri_state(run, paragraph, "all_caps")


__all__ = [
    "EffectiveFormattingResolver",
    "Resolved",
    "has_trailing_line_break",
    "is_uppercase_literal",
    "paragraph_text",
    "run_text",
]
