"""Output file naming: `<stem>.corrected.docx`, `.tracked.docx`, and so on.

Always resolved against a user-chosen output folder, never silently beside
the original -- writing next to the source risks the author mistaking a
`.corrected.docx` sitting in their submission folder for the file they meant
to send, or a journal's intake script picking up the wrong one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OutputPaths:
    corrected: Path
    tracked: Path
    annotated: Path
    report: Path
    audit: Path


def output_paths(source_path: Path, output_dir: Path) -> OutputPaths:
    """Every output path for one input, all sharing its stem, all rooted at
    `output_dir` -- never `source_path.parent`."""
    stem = source_path.stem
    return OutputPaths(
        corrected=output_dir / f"{stem}.corrected.docx",
        tracked=output_dir / f"{stem}.tracked.docx",
        annotated=output_dir / f"{stem}.annotated.docx",
        report=output_dir / f"{stem}.report.json",
        audit=output_dir / f"{stem}.audit.json",
    )


__all__ = ["OutputPaths", "output_paths"]
