"""Task 13 exit criteria: the pipeline façade runs validate -> fix -> report
end to end over every real manuscript with no crash, and FR-9 (never mutate
the original) and `--no-semantic` (fully offline) both hold as properties of
the design, not conventions.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from lxml import etree

from fixtures.factory import build_compliant, violating
from manuscript_validator.models.enums import ViolationStatus
from manuscript_validator.parser.ast_builder import build_ast
from manuscript_validator.pipeline import PipelineOptions, run

REAL_MANUSCRIPTS = sorted((Path(__file__).parent / "fixtures" / "real").glob("*.docx"))


def _progress_events(events: list[tuple[str, float]]):
    def progress(stage: str, fraction: float) -> None:
        events.append((stage, fraction))

    return progress


def test_run_produces_all_five_outputs(tmp_path: Path) -> None:
    doc, _handles = violating("title-size")
    source = tmp_path / "paper.docx"
    doc.save(source)

    result = run(source, PipelineOptions(output_dir=tmp_path / "out", run_semantic=False))

    assert set(result.outputs) == {"corrected", "tracked", "annotated", "report", "audit"}
    for path in result.outputs.values():
        assert path.exists()
        assert path.stat().st_size > 0
        assert path.parent == tmp_path / "out"


def test_run_reports_progress_from_0_to_1(tmp_path: Path) -> None:
    doc, _handles = violating("title-size")
    source = tmp_path / "paper.docx"
    doc.save(source)
    events: list[tuple[str, float]] = []

    run(
        source,
        PipelineOptions(output_dir=tmp_path / "out", run_semantic=False),
        progress=_progress_events(events),
    )

    assert events[0][1] == 0.0
    assert events[-1] == ("done", 1.0)
    assert [f for _s, f in events] == sorted(f for _s, f in events)


def test_no_semantic_runs_fully_offline_and_never_calls_the_stub_evaluator_api_key_path(
    tmp_path: Path,
) -> None:
    """`--no-semantic` (`run_semantic=False`) must never attempt to construct
    a real client even if an api_key happens to be set -- offline means
    offline regardless of what credentials are lying around."""
    doc, _handles = violating("title-size")
    source = tmp_path / "paper.docx"
    doc.save(source)

    fake_key = "AIzaNOTAREALKEYNOTAREALKEYNOTAREALK"
    result = run(
        source,
        PipelineOptions(output_dir=tmp_path / "out", run_semantic=False, api_key=fake_key),
    )

    semantic_failures = {
        v.failure_reason for v in (result.report.violations if result.report else [])
        if v.status is ViolationStatus.CHECK_FAILED
    }
    assert semantic_failures == {"semantic_check_not_implemented"}


def test_run_never_mutates_the_original_file(tmp_path: Path) -> None:
    doc, _handles = violating("heading-uppercase-literal")
    source = tmp_path / "paper.docx"
    doc.save(source)
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()

    run(source, PipelineOptions(output_dir=tmp_path / "out", run_semantic=False))

    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash


def test_no_fix_reports_but_does_not_correct(tmp_path: Path) -> None:
    doc, _handles = violating("title-size")
    source = tmp_path / "paper.docx"
    doc.save(source)

    result = run(
        source,
        PipelineOptions(output_dir=tmp_path / "out", run_semantic=False, apply_fixes=False),
    )

    assert result.fixed_count == 0
    assert result.violation_count > 0


def test_missing_api_key_degrades_to_check_failed_not_a_crash(tmp_path: Path) -> None:
    doc, _handles = violating("title-size")
    source = tmp_path / "paper.docx"
    doc.save(source)

    result = run(
        source,
        PipelineOptions(output_dir=tmp_path / "out", run_semantic=True, api_key=None),
    )

    semantic_failures = {
        v.failure_reason for v in (result.report.violations if result.report else [])
        if v.status is ViolationStatus.CHECK_FAILED
    }
    assert semantic_failures == {"api_key_missing"}


def _remove_section_block(doc, heading_text: str, next_heading_text: str) -> None:
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    body = doc.element.body
    to_remove = []
    capturing = False
    for p in list(body.iterchildren()):
        if etree.QName(p).localname != "p":
            continue
        text = "".join(t.text or "" for t in p.iter(f"{ns}t"))
        if text.strip() == heading_text:
            capturing = True
        elif capturing and text.strip() == next_heading_text:
            break
        if capturing:
            to_remove.append(p)
    for p in to_remove:
        p.getparent().remove(p)


def test_section_override_reclassifies_a_paragraph_before_validation(tmp_path: Path) -> None:
    """The UI's section-override panel (Task 14) must actually change what
    every rule sees, not just annotate the report -- a missing required
    section becomes present once a human relabels a paragraph, and the
    override is recorded for a reproducible re-run."""
    doc, _handles = build_compliant()
    _remove_section_block(doc, "DISCUSSION", "CONCLUSION")
    source = tmp_path / "paper.docx"
    doc.save(source)

    without_override = run(
        source, PipelineOptions(output_dir=tmp_path / "out1", run_semantic=False)
    )
    assert "discussion" in without_override.report.missing_sections

    source_bytes = source.read_bytes()
    ast = build_ast(Document(BytesIO(source_bytes)), source_bytes)
    conclusion_id = next(p.id for p in ast.paragraphs if p.text.strip() == "CONCLUSION")

    with_override = run(
        source,
        PipelineOptions(
            output_dir=tmp_path / "out2",
            run_semantic=False,
            section_overrides={conclusion_id: "discussion"},
        ),
    )

    assert "discussion" not in with_override.report.missing_sections
    assert with_override.report.section_overrides == {conclusion_id: "discussion"}


@pytest.mark.parametrize("source", REAL_MANUSCRIPTS, ids=[p.stem for p in REAL_MANUSCRIPTS])
def test_pipeline_runs_end_to_end_over_every_real_manuscript(source: Path, tmp_path: Path) -> None:
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()

    result = run(source, PipelineOptions(output_dir=tmp_path / "out", run_semantic=False))

    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
    for path in result.outputs.values():
        assert path.exists()
        assert path.stat().st_size > 0
    assert result.violation_count > 0  # every real submission has *something* to flag
