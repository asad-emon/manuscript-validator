"""Task 14 exit criteria (worker half): `PipelineWorker` runs `pipeline.run()`
on a `QThreadPool` thread and marshals its plain progress callback onto Qt
signals -- the only adapter between the Qt-free pipeline and the event loop.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QThreadPool

from fixtures.factory import violating
from manuscript_validator.pipeline import PipelineOptions, PipelineResult
from manuscript_validator.ui.workers import PipelineWorker

pytestmark = pytest.mark.gui


def test_worker_emits_progress_and_finished_signals(qtbot, tmp_path: Path) -> None:
    doc, _handles = violating("title-size")
    source = tmp_path / "paper.docx"
    doc.save(source)

    options = PipelineOptions(output_dir=tmp_path / "out", run_semantic=False)
    worker = PipelineWorker(source, options)

    progress_events: list[tuple[str, float]] = []
    worker.signals.progress.connect(lambda stage, frac: progress_events.append((stage, frac)))

    with qtbot.waitSignal(worker.signals.finished, timeout=15_000) as blocker:
        QThreadPool.globalInstance().start(worker)

    result = blocker.args[0]
    assert isinstance(result, PipelineResult)
    assert result.violation_count > 0
    assert progress_events  # at least one progress update was emitted
    assert progress_events[-1] == ("done", 1.0)


def test_worker_emits_failed_signal_for_a_bad_source(qtbot, tmp_path: Path) -> None:
    options = PipelineOptions(output_dir=tmp_path / "out", run_semantic=False)
    worker = PipelineWorker(tmp_path / "does_not_exist.docx", options)

    with qtbot.waitSignal(worker.signals.failed, timeout=15_000) as blocker:
        QThreadPool.globalInstance().start(worker)

    assert isinstance(blocker.args[0], str)
    assert blocker.args[0]  # a non-empty error message, not a crash
