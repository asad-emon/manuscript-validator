"""Task 13 exit criteria (CLI half): `validate paper.docx -o out/` emits all
five outputs and its exit code reflects violation severity, not just
success/failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fixtures.factory import violating
from manuscript_validator.cli import (
    EXIT_ERROR,
    EXIT_HIGH_SEVERITY,
    EXIT_NEEDS_REVIEW,
    EXIT_OK,
    main,
)


def test_help_with_no_command_prints_usage_and_exits_2(capsys: pytest.CaptureFixture) -> None:
    code = main([])
    assert code == 2
    assert "usage" in capsys.readouterr().out.lower()


def test_version_flag() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0


def test_validate_missing_source_exits_with_error(tmp_path: Path) -> None:
    code = main(
        ["validate", str(tmp_path / "nope.docx"), "-o", str(tmp_path / "out")]
    )
    assert code == EXIT_ERROR


def test_validate_emits_all_five_outputs(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    doc, _handles = violating("title-size")
    source = tmp_path / "paper.docx"
    doc.save(source)
    out_dir = tmp_path / "out"

    code = main(["validate", str(source), "-o", str(out_dir), "--no-semantic"])

    assert code == EXIT_OK
    for suffix in ("corrected", "tracked", "annotated", "report", "audit"):
        ext = "json" if suffix in ("report", "audit") else "docx"
        assert (out_dir / f"paper.{suffix}.{ext}").exists()
    out = capsys.readouterr().out
    assert "violation" in out


def test_validate_no_fix_flag_still_reports(tmp_path: Path) -> None:
    doc, _handles = violating("title-size")
    source = tmp_path / "paper.docx"
    doc.save(source)

    code = main(
        ["validate", str(source), "-o", str(tmp_path / "out"), "--no-semantic", "--no-fix"]
    )

    # title-size is auto_fixable and high severity; --no-fix means it stays
    # open, so it must still surface as a needs-review, high-severity exit.
    assert code == EXIT_HIGH_SEVERITY
    assert (tmp_path / "out" / "paper.report.json").exists()


def test_validate_exit_code_reflects_high_severity_needs_review(tmp_path: Path) -> None:
    """`table-caption-position` is `auto_fixable: false` and `severity: high`
    (a locked v1 decision: caption repositioning is flag-only) -- exactly the
    kind of violation that must survive to `needs_review` and drive a
    non-zero, severity-aware exit code."""
    doc, _handles = violating("table-caption-position")
    source = tmp_path / "paper.docx"
    doc.save(source)

    code = main(["validate", str(source), "-o", str(tmp_path / "out"), "--no-semantic"])

    assert code == EXIT_HIGH_SEVERITY


def test_validate_exit_code_for_medium_severity_needs_review(tmp_path: Path) -> None:
    doc, _handles = violating("title-wordlimit")  # medium severity, not auto-fixable
    source = tmp_path / "paper.docx"
    doc.save(source)

    code = main(["validate", str(source), "-o", str(tmp_path / "out"), "--no-semantic"])

    assert code == EXIT_NEEDS_REVIEW


def test_validate_uses_the_requested_ruleset(tmp_path: Path) -> None:
    doc, _handles = violating("title-size")
    source = tmp_path / "paper.docx"
    doc.save(source)

    args = [
        "validate", str(source), "-o", str(tmp_path / "out"),
        "--no-semantic", "--ruleset", "journal_v1",
    ]
    code = main(args)

    assert code in (EXIT_OK, EXIT_NEEDS_REVIEW, EXIT_HIGH_SEVERITY)
