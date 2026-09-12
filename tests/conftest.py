"""Shared fixtures.

Document fixtures are built in memory (Task 3) so tests need no temp files and
FR-9 -- the original is never mutated -- is testable by construction.
"""

from __future__ import annotations

import os

import pytest

#: Task 14's `gui`-marked tests need a Qt platform plugin, and this repo's
#: dev boxes have no display. `setdefault` only takes effect when nothing
#: already set the variable, so a developer with a real display and PYSIDE6
#: installed can still unset/override it to watch a test run on screen.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def frozen_timestamp() -> str:
    """Fixed timestamp so audit-log golden comparisons are deterministic."""
    return "2026-09-03T10:00:02Z"
