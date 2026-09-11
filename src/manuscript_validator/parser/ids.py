"""Paragraph, run, table, and figure id allocation (`p0042`, `p0042.r03`).

Ids are positional **at build time only**. Once assigned they are looked up by
value, not recomputed, so `ast_builder.build_ast` (which needs the AST) and
`binding.build_element_index` (which needs id -> live element for a
*different*, byte-identical clone) must walk in exactly the same order or
their ids drift apart. `walk_document` is that single canonical walk, and
both modules call it rather than each re-implementing traversal.

Table-cell paragraphs are yielded here too, tagged with their table id and
`(row, col)`, because spec section 5.1 omits them entirely and every
run-level rule (`table-text-size`) needs to reach them. Horizontally- or
vertically-merged cells make `Table.rows[i].cells` repeat the same
underlying `<w:tc>` for each spanned position -- de-duplicated here by
element identity so a merged cell's paragraph is not assigned two ids.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from docx.document import Document as DocumentObject
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table as DocxTable


def format_paragraph_id(n: int) -> str:
    return f"p{n:04d}"


def format_run_id(paragraph_id: str, n: int) -> str:
    return f"{paragraph_id}.r{n:02d}"


def format_table_id(n: int) -> str:
    return f"t{n:02d}"


def format_figure_id(n: int) -> str:
    return f"f{n:02d}"


@dataclass(frozen=True)
class ParagraphItem:
    id: str
    element: Any  # CT_P
    in_table: str | None
    cell: tuple[int, int] | None


@dataclass(frozen=True)
class TableItem:
    id: str
    element: Any  # CT_Tbl
    docx_table: DocxTable


def walk_document(document: DocumentObject) -> Iterator[ParagraphItem | TableItem]:
    """Yield paragraphs and tables in true document order.

    Iterates `body.iterchildren()`, not `document.paragraphs`/`.tables`, so
    paragraph/table interleaving survives -- caption-position detection
    depends on it. A table's cell paragraphs are yielded immediately after
    its `TableItem`, in row-then-column order.
    """
    p_counter = 0
    t_counter = 0
    body = document.element.body
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            p_counter += 1
            yield ParagraphItem(
                id=format_paragraph_id(p_counter), element=child, in_table=None, cell=None
            )
        elif isinstance(child, CT_Tbl):
            t_counter += 1
            table_id = format_table_id(t_counter)
            docx_table = DocxTable(child, document)
            yield TableItem(id=table_id, element=child, docx_table=docx_table)
            # Keyed by the element itself, not `id(cell._tc)`: `row.cells`
            # builds a fresh `_Cell` wrapper on every access, so nothing else
            # keeps a just-checked one alive -- once garbage collected, a
            # later cell's proxy can reuse the same address and collide.
            seen_cells: set[Any] = set()
            for row_idx, row in enumerate(docx_table.rows):
                for col_idx, cell in enumerate(row.cells):
                    if cell._tc in seen_cells:
                        continue  # merged cell already visited at an earlier position
                    seen_cells.add(cell._tc)
                    for cell_child in cell._tc.iterchildren():
                        if isinstance(cell_child, CT_P):
                            p_counter += 1
                            yield ParagraphItem(
                                id=format_paragraph_id(p_counter),
                                element=cell_child,
                                in_table=table_id,
                                cell=(row_idx, col_idx),
                            )


def iter_indexed_runs(paragraph_id: str, p_el: Any) -> Iterator[tuple[str, Any]]:
    """Yield `(run_id, run_element)` for a paragraph's real content runs.

    `.//w:r[not(ancestor::w:rPr)]`, not `./w:r` (which is what
    `Paragraph.runs` uses): the latter skips runs inside `w:ins` and
    `w:hyperlink`, so a manuscript carrying co-author tracked changes or
    hyperlinked text would be partly invisible to every run-level rule.
    """
    run_elements = p_el.xpath(".//w:r[not(ancestor::w:rPr)]")
    for i, r_el in enumerate(run_elements, start=1):
        yield format_run_id(paragraph_id, i), r_el


__all__ = [
    "ParagraphItem",
    "TableItem",
    "format_figure_id",
    "format_paragraph_id",
    "format_run_id",
    "format_table_id",
    "iter_indexed_runs",
    "walk_document",
]
