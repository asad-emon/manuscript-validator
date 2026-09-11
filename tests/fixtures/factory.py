"""Fixture factory for manuscript `.docx` documents (Task 3, spec section 12).

`build_compliant()` builds a complete, fully-formatted manuscript in memory: all
14 section-5.3 labels, two tables (Roman numerals, caption above), two figures
(Arabic numerals, caption below), eight references, a superscript bracket
citation, and superscript affiliation numerals on the author line.

`violating(rule_id)` builds a fresh compliant document and then applies exactly
one registered mutation, so every fixture "violates exactly that rule and no
other" (spec section 12) by construction rather than by inspection.

This module has no dependency on `manuscript_validator.parser` -- that package
does not exist yet (Task 4). Everything here operates directly on python-docx
objects and the underlying lxml elements, and `snapshot()`/`diff()` provide a
parser-independent way for tests to prove a mutation changed exactly the field
it claims to.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from docx import Document
from docx.document import Document as DocumentObject
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.text.run import Run

TNR = "Times New Roman"

SIZE_TITLE = 14
SIZE_AUTHOR = 10
SIZE_AFFIL = 7
SIZE_ABSTRACT = 9
SIZE_HEADING = 9
SIZE_BODY = 9
SIZE_TABLE_CELL = 8
SIZE_REFERENCE = 8

ABSTRACT_TEXT = (
    "Background: automated formatting review is slow and error-prone. "
    "Objectives: we aimed to evaluate a tool that validates and corrects "
    "manuscript formatting. In terms of methods and materials, we built a "
    "rule-driven validator and tested it against a journal template. "
    "Results: the tool detected and corrected the large majority of "
    "formatting deviations. Conclusion: rule-driven validation is a "
    "practical aid for manuscript preparation."
)


def _minimal_png() -> bytes:
    """A valid 1x1 grayscale PNG, built at runtime so no binary is checked in."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(
            ">I", zlib.crc32(tag + data)
        )

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff")
    return signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


_MINIMAL_PNG = _minimal_png()


def _picture_stream() -> BytesIO:
    return BytesIO(_MINIMAL_PNG)


def _run(
    paragraph: Paragraph,
    text: str,
    *,
    size: float,
    bold: bool = False,
    italic: bool = False,
    superscript: bool = False,
) -> Run:
    run = paragraph.add_run(text)
    run.font.name = TNR
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.superscript = superscript
    return run


def _has_trailing_break(paragraph: Paragraph) -> bool:
    runs = paragraph.runs
    if not runs:
        return False
    return runs[-1]._r.find(qn("w:br")) is not None


def _before(a: Any, b: Any) -> bool:
    """True if lxml element `a` precedes sibling `b` under their shared parent."""
    siblings = list(a.getparent())
    return siblings.index(a) < siblings.index(b)


@dataclass
class SectionBlock:
    heading_paragraph: Paragraph
    heading_run: Run
    body_paragraph: Paragraph
    body_run: Run


def _add_section_block(doc: DocumentObject, heading_text: str, body_text: str) -> SectionBlock:
    heading_p = doc.add_paragraph()
    heading_run = _run(heading_p, heading_text, size=SIZE_HEADING, bold=True)
    heading_p.add_run().add_break()
    body_p = doc.add_paragraph()
    body_run = _run(body_p, body_text, size=SIZE_BODY)
    return SectionBlock(heading_p, heading_run, body_p, body_run)


@dataclass
class TableFixture:
    table: Table
    caption_run: Run
    caption_element: Any
    table_element: Any
    cell_run: Run
    citing_run: Run | None = None
    narrative_element: Any | None = None


@dataclass
class FigureFixture:
    caption_run: Run
    caption_element: Any
    image_element: Any
    citing_run: Run | None = None


@dataclass
class Handles:
    """Direct references into a built document, so mutations and their tests
    never have to re-derive structure by searching text."""

    document: DocumentObject
    title_run: Run
    author_name_run: Run
    author_super_run: Run
    abstract_heading_run: Run
    abstract_body_run: Run
    keywords_run: Run
    affiliation_run: Run
    introduction_heading_paragraph: Paragraph
    introduction_heading_run: Run
    introduction_body_run: Run
    citation_super_run: Run
    table1: TableFixture
    table2: TableFixture
    figure1: FigureFixture
    figure2: FigureFixture
    reference_runs: list[Run]
    corresponding_run: Run
    order_pairs: dict[str, tuple[Any, Any]]
    doc_order_blocks: tuple[list[Any], list[Any]]
    section_blocks: dict[str, SectionBlock] = field(default_factory=dict)


def build_compliant() -> tuple[DocumentObject, Handles]:
    """Build a manuscript satisfying every rule in the section 6 rule set."""
    doc = Document()

    # -- Title --------------------------------------------------------
    title_p = doc.add_paragraph()
    title_run = _run(
        title_p, "A Compliant Manuscript Title For Automated Validation",
        size=SIZE_TITLE, bold=True,
    )

    # -- Author ---------------------------------------------------------
    author_p = doc.add_paragraph()
    author_name_run = _run(author_p, "Jane A. Doe", size=SIZE_AUTHOR, bold=True)
    author_super_run = _run(author_p, "1", size=SIZE_AUTHOR, bold=True, superscript=True)
    _run(author_p, ", John B. Roe", size=SIZE_AUTHOR, bold=True)
    _run(author_p, "2", size=SIZE_AUTHOR, bold=True, superscript=True)

    # -- Abstract ---------------------------------------------------------
    abstract_heading_p = doc.add_paragraph()
    abstract_heading_run = _run(abstract_heading_p, "Abstract", size=SIZE_ABSTRACT, italic=True)
    abstract_body_p = doc.add_paragraph()
    abstract_body_run = _run(abstract_body_p, ABSTRACT_TEXT, size=SIZE_ABSTRACT, italic=True)
    keywords_p = doc.add_paragraph()
    keywords_run = _run(
        keywords_p, "Keywords: validation, formatting, manuscripts, automation",
        size=SIZE_ABSTRACT, italic=True,
    )

    # -- Affiliation ---------------------------------------------------------
    affiliation_p = doc.add_paragraph()
    _run(affiliation_p, "1", size=SIZE_AFFIL, italic=True, superscript=True)
    affiliation_run = _run(
        affiliation_p,
        "Department of Clinical Research, Sagbrain Institute, Dhaka, Bangladesh. "
        "Email: jane.doe@example.com. ORCID: 0000-0001-2345-6789.",
        size=SIZE_AFFIL, italic=True,
    )

    # -- Introduction (built manually: needs an inline citation) ------------
    intro_heading_p = doc.add_paragraph()
    intro_heading_run = _run(intro_heading_p, "INTRODUCTION", size=SIZE_HEADING, bold=True)
    intro_heading_p.add_run().add_break()
    intro_body_p = doc.add_paragraph()
    intro_body_run = _run(
        intro_body_p, "This study builds on established evidence", size=SIZE_BODY
    )
    citation_super_run = _run(intro_body_p, "[1]", size=SIZE_BODY, superscript=True)
    _run(intro_body_p, " and extends the framework.", size=SIZE_BODY)

    # -- Methods and Materials ---------------------------------------------
    methods_block = _add_section_block(
        doc, "METHODS AND MATERIALS",
        "Participants were enrolled under a controlled protocol and outcomes were "
        "recorded using standardized instruments.",
    )

    # -- Result: narrative, tables, and figures -----------------------------
    result_heading_p = doc.add_paragraph()
    _run(result_heading_p, "RESULT", size=SIZE_HEADING, bold=True)
    result_heading_p.add_run().add_break()

    narrative_1_p = doc.add_paragraph()
    citing_run_1 = _run(
        narrative_1_p, "Table I summarizes the primary outcomes.", size=SIZE_BODY
    )
    caption_1_p = doc.add_paragraph()
    caption_run_1 = _run(
        caption_1_p, "Table I. Summary of primary outcomes.", size=SIZE_BODY
    )
    table1 = doc.add_table(rows=2, cols=2)
    table1.style = "Table Grid"
    _run(table1.cell(0, 0).paragraphs[0], "Metric", size=SIZE_TABLE_CELL, bold=True)
    _run(table1.cell(0, 1).paragraphs[0], "Value", size=SIZE_TABLE_CELL, bold=True)
    _run(table1.cell(1, 0).paragraphs[0], "Accuracy", size=SIZE_TABLE_CELL)
    cell_run_1 = _run(table1.cell(1, 1).paragraphs[0], "92%", size=SIZE_TABLE_CELL)
    table1_fixture = TableFixture(
        table=table1,
        caption_run=caption_run_1,
        caption_element=caption_1_p._p,
        table_element=table1._tbl,
        cell_run=cell_run_1,
        citing_run=citing_run_1,
        narrative_element=narrative_1_p._p,
    )

    narrative_2_p = doc.add_paragraph()
    _run(narrative_2_p, "Table II presents the secondary outcomes.", size=SIZE_BODY)
    caption_2_p = doc.add_paragraph()
    caption_run_2 = _run(
        caption_2_p, "Table II. Secondary outcomes overview.", size=SIZE_BODY
    )
    table2 = doc.add_table(rows=1, cols=2)
    table2.style = "Table Grid"
    _run(table2.cell(0, 0).paragraphs[0], "Sensitivity", size=SIZE_TABLE_CELL)
    _run(table2.cell(0, 1).paragraphs[0], "88%", size=SIZE_TABLE_CELL)
    table2_fixture = TableFixture(
        table=table2,
        caption_run=caption_run_2,
        caption_element=caption_2_p._p,
        table_element=table2._tbl,
        cell_run=table2.cell(0, 1).paragraphs[0].runs[0],
    )

    narrative_fig1_p = doc.add_paragraph()
    citing_run_fig1 = _run(
        narrative_fig1_p, "Figure 1 illustrates the trend over time.", size=SIZE_BODY
    )
    image1_p = doc.add_paragraph()
    image1_p.add_run().add_picture(_picture_stream(), width=Inches(1), height=Inches(1))
    caption_fig1_p = doc.add_paragraph()
    caption_run_fig1 = _run(caption_fig1_p, "Figure 1. Trend over time.", size=SIZE_BODY)
    figure1_fixture = FigureFixture(
        caption_run=caption_run_fig1,
        caption_element=caption_fig1_p._p,
        image_element=image1_p._p,
        citing_run=citing_run_fig1,
    )

    narrative_fig2_p = doc.add_paragraph()
    _run(narrative_fig2_p, "Figure 2 displays the distribution of results.", size=SIZE_BODY)
    image2_p = doc.add_paragraph()
    image2_p.add_run().add_picture(_picture_stream(), width=Inches(1), height=Inches(1))
    caption_fig2_p = doc.add_paragraph()
    caption_run_fig2 = _run(
        caption_fig2_p, "Figure 2. Distribution of results.", size=SIZE_BODY
    )
    figure2_fixture = FigureFixture(
        caption_run=caption_run_fig2,
        caption_element=caption_fig2_p._p,
        image_element=image2_p._p,
    )

    # -- Discussion / Conclusion --------------------------------------------
    _add_section_block(
        doc, "DISCUSSION",
        "These findings are consistent with the study objectives and prior work.",
    )
    _add_section_block(
        doc, "CONCLUSION",
        "The validator is an effective aid for manuscript formatting review.",
    )

    # -- Conflict of Interest / Funding (kept adjacent for the doc-order test) --
    coi_block = _add_section_block(
        doc, "CONFLICT OF INTEREST", "The authors declare no conflict of interest."
    )
    funding_block = _add_section_block(
        doc, "FUNDING", "This work received no external funding."
    )

    # -- Acknowledgement (optional, included for structural completeness) ---
    _add_section_block(
        doc, "ACKNOWLEDGEMENT", "The authors thank the editorial staff for their support."
    )

    # -- References -----------------------------------------------------
    references_heading_p = doc.add_paragraph()
    _run(references_heading_p, "REFERENCES", size=SIZE_HEADING, bold=True)
    references_heading_p.add_run().add_break()
    reference_runs: list[Run] = []
    for i in range(1, 9):
        reference_p = doc.add_paragraph()
        text = (
            f"{i}. Doe JA, Roe JB. Study {i} on manuscript formatting validation. "
            f"J Med Inform. 2024;{10 + i}(3):{100 + i}-{110 + i}."
        )
        reference_runs.append(_run(reference_p, text, size=SIZE_REFERENCE, italic=True))

    # -- Corresponding Author Address ------------------------------------
    corresponding_heading_p = doc.add_paragraph()
    _run(corresponding_heading_p, "CORRESPONDING AUTHOR", size=SIZE_HEADING, bold=True)
    corresponding_heading_p.add_run().add_break()
    corresponding_body_p = doc.add_paragraph()
    corresponding_run = _run(
        corresponding_body_p,
        "Jane A. Doe, Senior Researcher, Sagbrain Institute, Dhaka, Bangladesh. "
        "Mobile: +880-1710000000. Email: jane.doe@example.com. "
        "ORCID: 0000-0001-2345-6789.",
        size=SIZE_BODY,
    )

    order_pairs: dict[str, tuple[Any, Any]] = {
        "coi_vs_funding_heading": (
            coi_block.heading_paragraph._p, funding_block.heading_paragraph._p,
        ),
        "table1_caption_vs_table": (
            table1_fixture.caption_element, table1_fixture.table_element,
        ),
        "table1_narrative_vs_table": (
            table1_fixture.narrative_element, table1_fixture.table_element,
        ),
        "figure1_caption_vs_image": (
            figure1_fixture.caption_element, figure1_fixture.image_element,
        ),
    }
    doc_order_blocks = (
        [coi_block.heading_paragraph._p, coi_block.body_paragraph._p],
        [funding_block.heading_paragraph._p, funding_block.body_paragraph._p],
    )

    handles = Handles(
        document=doc,
        title_run=title_run,
        author_name_run=author_name_run,
        author_super_run=author_super_run,
        abstract_heading_run=abstract_heading_run,
        abstract_body_run=abstract_body_run,
        keywords_run=keywords_run,
        affiliation_run=affiliation_run,
        introduction_heading_paragraph=intro_heading_p,
        introduction_heading_run=intro_heading_run,
        introduction_body_run=intro_body_run,
        citation_super_run=citation_super_run,
        table1=table1_fixture,
        table2=table2_fixture,
        figure1=figure1_fixture,
        figure2=figure2_fixture,
        reference_runs=reference_runs,
        corresponding_run=corresponding_run,
        order_pairs=order_pairs,
        doc_order_blocks=doc_order_blocks,
        section_blocks={
            "methods_and_materials": methods_block,
            "conflict_of_interest": coi_block,
            "funding": funding_block,
        },
    )
    return doc, handles


def _swap_adjacent_blocks(a_elements: list[Any], b_elements: list[Any]) -> None:
    """Reorder two adjacent, contiguous element runs from [A, B] to [B, A]."""
    ref = b_elements[-1]
    for element in a_elements:
        ref.addnext(element)
        ref = element


def _mut_heading_line_break_after(handles: Handles) -> None:
    last_run = handles.introduction_heading_paragraph.runs[-1]._r
    parent = last_run.getparent()
    assert parent is not None
    parent.remove(last_run)


MUTATIONS: dict[str, Any] = {
    "global-font": lambda h: setattr(h.introduction_body_run.font, "name", "Arial"),
    "doc-order": lambda h: _swap_adjacent_blocks(*h.doc_order_blocks),
    "title-size": lambda h: setattr(h.title_run.font, "size", Pt(11)),
    "title-bold": lambda h: setattr(h.title_run.font, "bold", False),
    "title-case": lambda h: setattr(h.title_run, "text", h.title_run.text.lower()),
    "title-wordlimit": lambda h: setattr(
        h.title_run, "text", h.title_run.text + " " + " ".join(f"word{i}" for i in range(30))
    ),
    "author-bold": lambda h: setattr(h.author_name_run.font, "bold", False),
    "author-size": lambda h: setattr(h.author_name_run.font, "size", Pt(12)),
    "author-affiliation-superscript": lambda h: setattr(
        h.author_super_run.font, "superscript", False
    ),
    "abstract-heading-italic": lambda h: setattr(h.abstract_heading_run.font, "italic", False),
    "abstract-body-italic": lambda h: setattr(h.abstract_body_run.font, "italic", False),
    "abstract-size": lambda h: setattr(h.abstract_body_run.font, "size", Pt(11)),
    "abstract-wordlimit": lambda h: setattr(
        h.abstract_body_run,
        "text",
        h.abstract_body_run.text + " " + " ".join(f"filler{i}" for i in range(260)),
    ),
    "abstract-structure": lambda h: setattr(
        h.abstract_body_run,
        "text",
        "Results are reported first, before any background or objectives are given.",
    ),
    "abstract-keywords-count": lambda h: setattr(
        h.keywords_run, "text", "Keywords: onlyonekeyword"
    ),
    "affiliation-italic": lambda h: setattr(h.affiliation_run.font, "italic", False),
    "affiliation-size": lambda h: setattr(h.affiliation_run.font, "size", Pt(9)),
    "affiliation-content": lambda h: setattr(
        h.affiliation_run, "text", "Department of Clinical Research, Sagbrain Institute"
    ),
    "heading-uppercase-literal": lambda h: setattr(
        h.introduction_heading_run, "text", "Introduction"
    ),
    "heading-bold": lambda h: setattr(h.introduction_heading_run.font, "bold", False),
    "heading-size": lambda h: setattr(h.introduction_heading_run.font, "size", Pt(11)),
    "heading-no-colon": lambda h: setattr(
        h.introduction_heading_run, "text", h.introduction_heading_run.text + ":"
    ),
    "heading-line-break-after": _mut_heading_line_break_after,
    "body-text-size": lambda h: setattr(h.introduction_body_run.font, "size", Pt(11)),
    "citation-superscript": lambda h: setattr(
        h.citation_super_run.font, "superscript", False
    ),
    "citation-bracket-format": lambda h: setattr(h.citation_super_run, "text", "(1)"),
    "table-caption-position": lambda h: h.table1.table_element.addnext(
        h.table1.caption_element
    ),
    "table-caption-numbering-style": lambda h: setattr(
        h.table1.caption_run,
        "text",
        h.table1.caption_run.text.replace("Table I.", "Table 1."),
    ),
    "table-numbering-sequence": lambda h: setattr(
        h.table2.caption_run,
        "text",
        h.table2.caption_run.text.replace("Table II.", "Table III."),
    ),
    "table-text-size": lambda h: setattr(h.table1.cell_run.font, "size", Pt(10)),
    "table-cited-in-text": lambda h: setattr(
        h.table1.citing_run, "text", "The primary outcomes are summarized below."
    ),
    "figure-caption-position": lambda h: h.figure1.image_element.addprevious(
        h.figure1.caption_element
    ),
    "figure-caption-numbering-style": lambda h: setattr(
        h.figure1.caption_run,
        "text",
        h.figure1.caption_run.text.replace("Figure 1.", "Figure I."),
    ),
    "figure-numbering-sequence": lambda h: setattr(
        h.figure2.caption_run,
        "text",
        h.figure2.caption_run.text.replace("Figure 2.", "Figure 4."),
    ),
    "figure-cited-in-text": lambda h: setattr(
        h.figure1.citing_run, "text", "The trend is illustrated below."
    ),
    "result-text-before-figure": lambda h: h.table1.table_element.addnext(
        h.table1.narrative_element
    ),
    "reference-style-italic": lambda h: setattr(h.reference_runs[0].font, "italic", False),
    "reference-style-size": lambda h: setattr(h.reference_runs[0].font, "size", Pt(10)),
    "reference-style-vancouver-format": lambda h: setattr(
        h.reference_runs[0],
        "text",
        "Doe, J. A., & Roe, J. B. (2024). Effect of standardized formatting. "
        "Journal of Medical Informatics, 12(3), 145-152.",
    ),
    "corresponding-author-content": lambda h: setattr(
        h.corresponding_run,
        "text",
        h.corresponding_run.text.replace("ORCID: 0000-0001-2345-6789.", "").strip(),
    ),
}

#: The dotted snapshot key(s) each mutation is expected -- and only expected --
#: to change. Read by the meta-test; see `snapshot()`/`diff()` below.
MUTATION_TARGETS: dict[str, frozenset[str]] = {
    "global-font": frozenset({"introduction_body_run.font_name"}),
    "doc-order": frozenset({"order_pairs.coi_vs_funding_heading"}),
    "title-size": frozenset({"title_run.font_size_pt"}),
    "title-bold": frozenset({"title_run.bold"}),
    "title-case": frozenset({"title_run.text"}),
    "title-wordlimit": frozenset({"title_run.text"}),
    "author-bold": frozenset({"author_name_run.bold"}),
    "author-size": frozenset({"author_name_run.font_size_pt"}),
    "author-affiliation-superscript": frozenset({"author_super_run.superscript"}),
    "abstract-heading-italic": frozenset({"abstract_heading_run.italic"}),
    "abstract-body-italic": frozenset({"abstract_body_run.italic"}),
    "abstract-size": frozenset({"abstract_body_run.font_size_pt"}),
    "abstract-wordlimit": frozenset({"abstract_body_run.text"}),
    "abstract-structure": frozenset({"abstract_body_run.text"}),
    "abstract-keywords-count": frozenset({"keywords_run.text"}),
    "affiliation-italic": frozenset({"affiliation_run.italic"}),
    "affiliation-size": frozenset({"affiliation_run.font_size_pt"}),
    "affiliation-content": frozenset({"affiliation_run.text"}),
    "heading-uppercase-literal": frozenset({"introduction_heading_run.text"}),
    "heading-bold": frozenset({"introduction_heading_run.bold"}),
    "heading-size": frozenset({"introduction_heading_run.font_size_pt"}),
    "heading-no-colon": frozenset({"introduction_heading_run.text"}),
    "heading-line-break-after": frozenset({"introduction_heading_break.present"}),
    "body-text-size": frozenset({"introduction_body_run.font_size_pt"}),
    "citation-superscript": frozenset({"citation_super_run.superscript"}),
    "citation-bracket-format": frozenset({"citation_super_run.text"}),
    "table-caption-position": frozenset({"order_pairs.table1_caption_vs_table"}),
    "table-caption-numbering-style": frozenset({"table1.caption_run.text"}),
    "table-numbering-sequence": frozenset({"table2.caption_run.text"}),
    "table-text-size": frozenset({"table1.cell_run.font_size_pt"}),
    "table-cited-in-text": frozenset({"table1.citing_run.text"}),
    "figure-caption-position": frozenset({"order_pairs.figure1_caption_vs_image"}),
    "figure-caption-numbering-style": frozenset({"figure1.caption_run.text"}),
    "figure-numbering-sequence": frozenset({"figure2.caption_run.text"}),
    "figure-cited-in-text": frozenset({"figure1.citing_run.text"}),
    "result-text-before-figure": frozenset({"order_pairs.table1_narrative_vs_table"}),
    "reference-style-italic": frozenset({"reference_runs.0.italic"}),
    "reference-style-size": frozenset({"reference_runs.0.font_size_pt"}),
    "reference-style-vancouver-format": frozenset({"reference_runs.0.text"}),
    "corresponding-author-content": frozenset({"corresponding_run.text"}),
}

assert set(MUTATIONS) == set(MUTATION_TARGETS)

#: Canonical rule-ID inventory (docs/decisions.md: section 6's 25 rows -> ~38
#: entries; see `~/.claude/plans/create-a-development-plan-eager-scroll.md`).
#: Task 6 authors the full `journal_v1.json` against this same inventory.
RULE_IDS: tuple[str, ...] = tuple(MUTATIONS)


def violating(rule_id: str) -> tuple[DocumentObject, Handles]:
    """A compliant document mutated to violate exactly `rule_id`."""
    if rule_id not in MUTATIONS:
        raise KeyError(f"no violating() mutation registered for rule {rule_id!r}")
    doc, handles = build_compliant()
    MUTATIONS[rule_id](handles)
    return doc, handles


def _run_fields(run: Run) -> dict[str, Any]:
    size = run.font.size
    return {
        "text": run.text,
        "font_name": run.font.name,
        "font_size_pt": size.pt if size is not None else None,
        "bold": run.font.bold,
        "italic": run.font.italic,
        "superscript": run.font.superscript,
    }


def snapshot(handles: Handles) -> dict[str, Any]:
    """A flat, comparable fingerprint of every field a mutation can target."""
    out: dict[str, Any] = {}

    def add(prefix: str, run: Run) -> None:
        for name, value in _run_fields(run).items():
            out[f"{prefix}.{name}"] = value

    add("title_run", handles.title_run)
    add("author_name_run", handles.author_name_run)
    add("author_super_run", handles.author_super_run)
    add("abstract_heading_run", handles.abstract_heading_run)
    add("abstract_body_run", handles.abstract_body_run)
    add("keywords_run", handles.keywords_run)
    add("affiliation_run", handles.affiliation_run)
    add("introduction_heading_run", handles.introduction_heading_run)
    add("introduction_body_run", handles.introduction_body_run)
    add("citation_super_run", handles.citation_super_run)
    add("table1.caption_run", handles.table1.caption_run)
    add("table1.cell_run", handles.table1.cell_run)
    assert handles.table1.citing_run is not None
    add("table1.citing_run", handles.table1.citing_run)
    add("table2.caption_run", handles.table2.caption_run)
    add("figure1.caption_run", handles.figure1.caption_run)
    assert handles.figure1.citing_run is not None
    add("figure1.citing_run", handles.figure1.citing_run)
    add("figure2.caption_run", handles.figure2.caption_run)
    for i, run in enumerate(handles.reference_runs):
        add(f"reference_runs.{i}", run)
    add("corresponding_run", handles.corresponding_run)

    out["introduction_heading_break.present"] = _has_trailing_break(
        handles.introduction_heading_paragraph
    )
    for name, (a, b) in handles.order_pairs.items():
        out[f"order_pairs.{name}"] = _before(a, b)
    return out


def diff(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    """The set of snapshot keys whose value differs between two snapshots."""
    keys = set(before) | set(after)
    return {key for key in keys if before.get(key) != after.get(key)}
