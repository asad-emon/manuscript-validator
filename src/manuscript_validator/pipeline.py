"""Qt-free orchestration facade (Task 13).

Spec section 4 has the main window calling the pipeline stages directly, which
puts orchestration, error handling, and progress reporting inside a Qt class --
precisely the code that cannot be tested without a display and cannot be reused
by the CLI. This module is that code instead, and both shells call it.

Progress is a plain callable, not a Qt signal; `ui.workers` adapts it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

ProgressCallback = Callable[[str, float], None]


@dataclass(frozen=True)
class PipelineOptions:
    """Knobs the UI and CLI both expose."""

    run_semantic: bool = True
    apply_fixes: bool = True
    ruleset_id: str = "journal_v1"


@dataclass
class PipelineResult:
    """Everything a caller needs to render results and write outputs."""

    source: Path
    outputs: dict[str, Path] = field(default_factory=dict)
    violation_count: int = 0
    fixed_count: int = 0
    needs_review_count: int = 0


def run(
    source: Path,
    options: PipelineOptions | None = None,
    progress: ProgressCallback | None = None,
) -> PipelineResult:
    """Run the full validate -> fix -> report pipeline.

    The source file is read to bytes once here and the path is never passed
    downstream, which makes FR-9 ("never mutates the original") a property of
    the design rather than a convention each stage has to honour.
    """
    raise NotImplementedError("Task 13")
