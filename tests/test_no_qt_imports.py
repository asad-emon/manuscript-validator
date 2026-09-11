"""Spec section 13: no pipeline module may depend on Qt.

This constraint is what lets the whole pipeline be built and tested on a machine
with no display, so it is enforced mechanically rather than by convention. The
check is textual because importing a Qt module to find out would defeat the
purpose on a box where Qt is not installed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import manuscript_validator

PIPELINE_DIRS = [
    "models",
    "parser",
    "segmenter",
    "rules",
    "autofix",
    "report",
    "output",
    "config",
]

QT_IMPORT = re.compile(r"^\s*(?:import|from)\s+(PySide6|PyQt5|PyQt6)\b", re.MULTILINE)

_ROOT = Path(manuscript_validator.__path__[0])


def _pipeline_sources() -> list[Path]:
    files = [_ROOT / "pipeline.py", _ROOT / "cli.py"]
    for directory in PIPELINE_DIRS:
        files.extend(sorted((_ROOT / directory).rglob("*.py")))
    return files


@pytest.mark.parametrize("source", _pipeline_sources(), ids=lambda p: p.name)
def test_pipeline_module_is_qt_free(source: Path) -> None:
    match = QT_IMPORT.search(source.read_text(encoding="utf-8"))
    assert match is None, f"{source} imports {match.group(1) if match else ''}"
