"""Inserts native Word comments, one per violation.

python-docx 1.2.0 has native comment support (`Document.add_comment`), which
wires `word/comments.xml`, the content-type override, the relationship, and
the `commentRangeStart`/`End`/`commentReference` markers automatically -- so
this does not hand-roll OOXML, despite what spec section 11 implies. It also
continues comment-id allocation correctly on a reopened file, which hand-
rolled code would have to reimplement.

Comments go on a clone of the *original*, so the author sees them against
what they submitted, never on `corrected.docx` or the redline.
"""

from __future__ import annotations

from typing import Any, cast

from docx.document import Document as DocumentObject
from docx.oxml.ns import qn
from docx.text.run import Run
from lxml import etree

from manuscript_validator.errors import DocumentError
from manuscript_validator.models.violation import Violation
from manuscript_validator.parser.binding import ElementIndex

DEFAULT_AUTHOR = "Manuscript Validator"
DEFAULT_INITIALS = "MV"


def _wrap(run_el: Any) -> Run:
    # Only ever used to anchor a comment range -- `mark_comment_range` reads
    # `self._r` directly and never touches `.part`, so `None` is safe here
    # for the same reason it is in `autofix.actions._wrap`.
    return Run(run_el, cast(Any, None))


def anchor_runs(paragraph_el: Any) -> list[Run]:
    """Runs to anchor a comment to. Falls back to inserting a zero-width run
    when the paragraph has none -- an empty paragraph has nothing for
    `Document.add_comment` to mark a range around, and it would otherwise
    raise `IndexError` reaching for a first/last run that doesn't exist.
    """
    run_elements = paragraph_el.xpath(".//w:r[not(ancestor::w:rPr)]")
    if not run_elements:
        run_elements = [etree.SubElement(paragraph_el, qn("w:r"))]
    return [_wrap(run_el) for run_el in run_elements]


def _comment_text(violation: Violation) -> str:
    if violation.message:
        return violation.message
    return f"{violation.rule_id}: expected {violation.expected}, found {violation.found}"


def annotate_document(
    document: DocumentObject,
    element_index: ElementIndex,
    violations: list[Violation],
    author: str = DEFAULT_AUTHOR,
    initials: str = DEFAULT_INITIALS,
) -> int:
    """Add one native comment per violation that has a paragraph to anchor
    to -- `paragraph_id` first, falling back to `anchor_paragraph_id` for a
    document-level violation (a missing section, an ordering problem) that
    has no paragraph of its own. A violation with neither is skipped, not
    raised on; the JSON report (`build_report`) is the source of truth for
    those regardless of whether the document copy can also show them.

    Returns the number of comments actually added.
    """
    annotated = 0
    for violation in violations:
        target_id = violation.paragraph_id or violation.anchor_paragraph_id
        if target_id is None:
            continue
        try:
            paragraph_el = element_index.paragraph(target_id)
        except DocumentError:
            continue
        runs = anchor_runs(paragraph_el)
        document.add_comment(runs, text=_comment_text(violation), author=author, initials=initials)
        annotated += 1
    return annotated


__all__ = ["DEFAULT_AUTHOR", "DEFAULT_INITIALS", "anchor_runs", "annotate_document"]
