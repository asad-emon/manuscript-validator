"""Task 9 exit criteria (naming half): every output path shares the input's
stem and is rooted at the caller's output directory, never the source's own
parent directory.
"""

from __future__ import annotations

from pathlib import Path

from manuscript_validator.output import output_paths


def test_output_paths_share_stem_and_root_at_output_dir() -> None:
    source = Path("/home/user/submissions/paper.docx")
    output_dir = Path("/home/user/Desktop/results")

    paths = output_paths(source, output_dir)

    assert paths.corrected == output_dir / "paper.corrected.docx"
    assert paths.tracked == output_dir / "paper.tracked.docx"
    assert paths.annotated == output_dir / "paper.annotated.docx"
    assert paths.report == output_dir / "paper.report.json"
    assert paths.audit == output_dir / "paper.audit.json"
    for path in (paths.corrected, paths.tracked, paths.annotated, paths.report, paths.audit):
        assert path.parent == output_dir
        assert path.parent != source.parent
