"""Figure detection.

Uses `//w:drawing | //w:pict` then `ancestor::w:p[1]`. `document.inline_shapes`
is insufficient: its xpath misses floating (`wp:anchor`) and VML images, and
`InlineShape` has no paragraph back-reference. Body-scoped only -- headers,
footers, and footnotes are out of scope in v1 (see docs/decisions.md).
"""

from __future__ import annotations

from typing import Any

from docx.document import Document as DocumentObject


def find_figure_paragraphs(document: DocumentObject) -> list[Any]:
    """The distinct `<w:p>` elements that contain an image, in document order.

    A paragraph with more than one drawing (rare, but not invalid OOXML) is
    reported once -- it is one figure position, however many images it holds.
    """
    body = document.element.body
    drawings = body.xpath(".//w:drawing | .//w:pict")
    seen: set[Any] = set()
    paragraphs: list[Any] = []
    for drawing_el in drawings:
        ancestors = drawing_el.xpath("ancestor::w:p[1]")
        if not ancestors:
            continue
        p_el = ancestors[0]
        if p_el in seen:
            continue
        seen.add(p_el)
        paragraphs.append(p_el)
    return paragraphs


__all__ = ["find_figure_paragraphs"]
