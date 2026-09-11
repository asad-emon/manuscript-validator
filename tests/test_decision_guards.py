"""Guards for decisions in docs/decisions.md that code could silently violate.

These run against stub modules today and cost nothing; they exist so the
mistakes they describe cannot land later without a red test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import manuscript_validator

_ROOT = Path(manuscript_validator.__path__[0])

DEEPCOPY = re.compile(r"\bdeepcopy\b")

# C1: copy.deepcopy(Document) produces two independent XML trees and silently
# discards every mutation on save. Cloning goes through the original bytes.
#
# Scoped to autofix/ deliberately. output/tracked_changes.py deep-copies lxml
# *elements* -- snapshotting an rPr, cloning a run into a w:del/w:ins pair --
# which is both necessary and safe; the trap is deep-copying a Document.
NO_DEEPCOPY_DIRS = ["autofix"]


@pytest.mark.parametrize("directory", NO_DEEPCOPY_DIRS)
def test_no_deepcopy_of_documents(directory: str) -> None:
    offenders = [
        path.relative_to(_ROOT)
        for path in sorted((_ROOT / directory).rglob("*.py"))
        if DEEPCOPY.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"deepcopy found in {offenders}; see docs/decisions.md C1 -- "
        "clone via Document(BytesIO(original_bytes)) instead"
    )
