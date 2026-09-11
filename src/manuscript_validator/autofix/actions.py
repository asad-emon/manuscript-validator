"""Fix action registry.

Each action is a small isolated function over a single live `<w:r>` or `<w:p>`
element, with no cross-paragraph side effects, so each is independently
unit-testable against a synthetic node (spec section 13). Every action
returns `(before, after)` attribute snapshots for the audit log (spec
section 5.5) -- read from the *live* element just before and after the edit,
never from the AST, so the audit log always reflects what the document
actually had, not what a stale AST snapshot claimed.

`set_caption_position` and `set_title_case` are registered but disabled in
v1: a caption move is a structural edit spec section 8 forbids and the
redline cannot represent, and automatic title-casing mangles acronyms and
Latin binomials. Both are reported as flag-only violations instead (see
`journal_v1.json`: both rules are `auto_fixable: false`), so no rule ever
plans a `FixOp` for either action and no handler is needed here.

None of the 40 rules this project ships need to split a run (Task 7's citation
run-splitting trap remains open, tracked in the development checklist) -- every
fix action here targets either a whole run or a whole paragraph's last
visible run.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, cast

from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.run import Run
from lxml import etree

from manuscript_validator.errors import FixApplicationError
from manuscript_validator.models.enums import FixAction
from manuscript_validator.parser.captions import int_to_roman, roman_to_int

#: `w:rFonts` theme attributes that, per ECMA-376 17.3.2.26, win over an
#: explicit `ascii`/`hAnsi` when both are present -- spec-alignment risk 2
#: (docs/decisions.md): setting `Font.name` alone leaves Word rendering the
#: theme font, and re-validation would report a false green.
_THEME_FONT_ATTRS = ("asciiTheme", "hAnsiTheme", "cstheme", "eastAsiaTheme")

_CAPTION_TOKEN_RE = re.compile(
    r"^(\s*(?:Table|Fig(?:ure)?\.?)\s+)([IVXLCDM0-9]+)([.:].*)$", re.IGNORECASE | re.DOTALL
)

ActionResult = tuple[dict[str, Any], dict[str, Any]]


def _wrap(run_el: Any) -> Run:
    # Every action here only ever touches `.text`/`.font` -- never anything
    # that needs a real parent (e.g. adding an image) -- so `None` is safe at
    # runtime even though `Run.__init__` is typed to want a real one.
    return Run(run_el, cast(Any, None))


def _last_visible_run(paragraph_el: Any) -> Any | None:
    """The last run in `paragraph_el` that carries visible text -- skips a
    trailing `add_run().add_break()` run, whose own `.text` is `"\\n"`."""
    run_elements = paragraph_el.xpath(".//w:r[not(ancestor::w:rPr)]")
    for run_el in reversed(run_elements):
        if _wrap(run_el).text.strip():
            return run_el
    return None


def set_font(run_el: Any, params: dict[str, Any]) -> ActionResult:
    run = _wrap(run_el)
    before = {"font_name": run.font.name}
    font_name = params["font_name"]
    r_fonts = run_el.get_or_add_rPr().get_or_add_rFonts()
    for attr in _THEME_FONT_ATTRS:
        qname = qn(f"w:{attr}")
        if r_fonts.get(qname) is not None:
            del r_fonts.attrib[qname]
    run.font.name = font_name
    return before, {"font_name": font_name}


def set_font_size(run_el: Any, params: dict[str, Any]) -> ActionResult:
    run = _wrap(run_el)
    size = run.font.size
    before = {"font_size_pt": size.pt if size is not None else None}
    font_size_pt = params["font_size_pt"]
    run.font.size = Pt(font_size_pt)
    return before, {"font_size_pt": font_size_pt}


def set_bold(run_el: Any, params: dict[str, Any]) -> ActionResult:
    run = _wrap(run_el)
    before = {"bold": run.font.bold}
    value = params["bold"]
    run.font.bold = value
    return before, {"bold": value}


def set_italic(run_el: Any, params: dict[str, Any]) -> ActionResult:
    run = _wrap(run_el)
    before = {"italic": run.font.italic}
    value = params["italic"]
    run.font.italic = value
    return before, {"italic": value}


def set_superscript(run_el: Any, params: dict[str, Any]) -> ActionResult:
    run = _wrap(run_el)
    before = {"superscript": run.font.superscript}
    value = params["superscript"]
    run.font.superscript = value
    return before, {"superscript": value}


def set_uppercase_literal(run_el: Any, _params: dict[str, Any]) -> ActionResult:
    """Uppercases the text **and** clears `w:caps` (Task 7's rule-
    implementation trap): leaving the caps transform in place would make the
    document look right while the literal check fails forever."""
    run = _wrap(run_el)
    before_text = run.text
    after_text = before_text.upper()
    run.text = after_text
    run.font.all_caps = False
    return {"text": before_text}, {"text": after_text}


def strip_trailing_colon(paragraph_el: Any, _params: dict[str, Any]) -> ActionResult:
    run_el = _last_visible_run(paragraph_el)
    if run_el is None:
        raise FixApplicationError("strip_trailing_colon: paragraph has no visible run")
    run = _wrap(run_el)
    before = run.text
    after = re.sub(r":\s*$", "", before)
    run.text = after
    return {"text": before}, {"text": after}


def insert_line_break(paragraph_el: Any, _params: dict[str, Any]) -> ActionResult:
    run_el = etree.SubElement(paragraph_el, qn("w:r"))
    etree.SubElement(run_el, qn("w:br"))
    return {"line_break_after": False}, {"line_break_after": True}


def set_citation_brackets(run_el: Any, _params: dict[str, Any]) -> ActionResult:
    run = _wrap(run_el)
    before = run.text
    match = re.match(r"^([\[(])(\d+)([\])])$", before)
    if match is None:
        raise FixApplicationError(f"set_citation_brackets: {before!r} is not a wrapped number")
    after = f"[{match.group(2)}]"
    run.text = after
    return {"text": before}, {"text": after}


def set_numbering_style(paragraph_el: Any, params: dict[str, Any]) -> ActionResult:
    """Rewrites a caption's number token in place, preserving its numeric
    value -- "Table 1." with `numbering_style: "roman"` becomes "Table I.",
    never a reset to 1/I regardless of the table's actual position (that is
    `table-numbering-sequence`'s job, and it is not auto-fixable: closing a
    numbering gap can renumber every table after it)."""
    target_style = params["numbering_style"]
    for run_el in paragraph_el.xpath(".//w:r[not(ancestor::w:rPr)]"):
        run = _wrap(run_el)
        match = _CAPTION_TOKEN_RE.match(run.text)
        if match is None:
            continue
        prefix, token, suffix = match.groups()
        value = int(token) if token.isdigit() else roman_to_int(token)
        if value is None:
            continue
        new_token = int_to_roman(value) if target_style == "roman" else str(value)
        before = run.text
        after = f"{prefix}{new_token}{suffix}"
        run.text = after
        return {"text": before}, {"text": after}
    raise FixApplicationError("set_numbering_style: no caption-numbered run found")


#: Whether an action's `target_id` names a run or a paragraph -- resolved by
#: `autofix.engine._resolve_target`, which looks the id up in the matching
#: `ElementIndex` table.
RUN_ACTIONS: dict[FixAction, Callable[[Any, dict[str, Any]], ActionResult]] = {
    FixAction.SET_FONT: set_font,
    FixAction.SET_FONT_SIZE: set_font_size,
    FixAction.SET_BOLD: set_bold,
    FixAction.SET_ITALIC: set_italic,
    FixAction.SET_SUPERSCRIPT: set_superscript,
    FixAction.SET_UPPERCASE_LITERAL: set_uppercase_literal,
    FixAction.SET_CITATION_BRACKETS: set_citation_brackets,
}

PARAGRAPH_ACTIONS: dict[FixAction, Callable[[Any, dict[str, Any]], ActionResult]] = {
    FixAction.STRIP_TRAILING_COLON: strip_trailing_colon,
    FixAction.INSERT_LINE_BREAK: insert_line_break,
    FixAction.SET_NUMBERING_STYLE: set_numbering_style,
}


__all__ = [
    "PARAGRAPH_ACTIONS",
    "RUN_ACTIONS",
    "ActionResult",
    "insert_line_break",
    "set_bold",
    "set_citation_brackets",
    "set_font",
    "set_font_size",
    "set_italic",
    "set_numbering_style",
    "set_superscript",
    "set_uppercase_literal",
    "strip_trailing_colon",
]
