"""QRunnable wrapper marshalling pipeline progress callbacks onto Qt signals.

The only adapter between the Qt-free pipeline and the event loop -- `pipeline.run()`
itself never imports Qt (`test_no_qt_imports` enforces that mechanically), so
this module's only job is to call it on a worker thread and turn its plain
`progress(stage, fraction)` callback into a signal the main thread can connect
a progress bar to.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from manuscript_validator.pipeline import PipelineOptions, PipelineResult
from manuscript_validator.pipeline import run as run_pipeline


class WorkerSignals(QObject):
    """A `QRunnable` cannot itself define signals (it isn't a `QObject`), so
    the runnable owns one of these instead and the caller connects to it
    before scheduling the runnable on a `QThreadPool`."""

    progress = Signal(str, float)
    finished = Signal(object)  # PipelineResult
    failed = Signal(str)


class PipelineWorker(QRunnable):
    """Runs `pipeline.run()` on a thread-pool thread. Any exception the
    pipeline itself didn't already turn into a `check_failed`/`fix_failed`
    violation (an unreadable file, a permissions error) is caught here and
    reported through `failed` rather than crashing the worker thread, which
    Qt would otherwise just print to stderr and silently drop.
    """

    def __init__(self, source: Path, options: PipelineOptions) -> None:
        super().__init__()
        self._source = source
        self._options = options
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result: PipelineResult = run_pipeline(
                self._source, self._options, progress=self._emit_progress
            )
        except Exception as exc:
            self.signals.failed.emit(str(exc))
            return
        self.signals.finished.emit(result)

    def _emit_progress(self, stage: str, fraction: float) -> None:
        self.signals.progress.emit(stage, fraction)


__all__ = ["PipelineWorker", "WorkerSignals"]
