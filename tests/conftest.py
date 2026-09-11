"""Shared fixtures.

Document fixtures are built in memory (Task 3) so tests need no temp files and
FR-9 -- the original is never mutated -- is testable by construction.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def frozen_timestamp() -> str:
    """Fixed timestamp so audit-log golden comparisons are deterministic."""
    return "2026-09-03T10:00:02Z"
