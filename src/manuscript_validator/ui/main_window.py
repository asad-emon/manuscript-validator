"""Main window: file picker, progress, results (Task 14).

A shell over `pipeline.run()` -- every decision this window makes (which
file, which output folder, whether to re-run with overrides) turns into a
`PipelineOptions` and a call into `ui.workers.PipelineWorker`. No validation
logic lives here; `test_no_qt_imports` would fail immediately if `pipeline.py`
ever needed to import this package back.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from manuscript_validator.config import get_api_key
from manuscript_validator.pipeline import PipelineOptions, PipelineResult
from manuscript_validator.ui.report_view import ReportView, SectionOverridePanel
from manuscript_validator.ui.settings_window import SettingsDialog
from manuscript_validator.ui.workers import PipelineWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Manuscript Validator")
        self.resize(960, 640)

        self._thread_pool = QThreadPool.globalInstance()
        self._source: Path | None = None
        self._output_dir: Path | None = None

        self._open_button = QPushButton("Open manuscript...")
        self._open_button.clicked.connect(self._on_open)

        self._status_label = QLabel("No manuscript loaded.")
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)

        self._report_view = ReportView()
        self._override_panel = SectionOverridePanel()
        self._override_panel.overrides_applied.connect(self._on_overrides_applied)

        splitter = QSplitter()
        splitter.addWidget(self._report_view)
        splitter.addWidget(self._override_panel)

        layout = QVBoxLayout()
        layout.addWidget(self._open_button)
        layout.addWidget(self._status_label)
        layout.addWidget(self._progress_bar)
        layout.addWidget(splitter)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self._build_menu()
        self._set_file_operations_enabled(True)

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("File")
        settings_action = menu.addAction("Settings")
        settings_action.triggered.connect(self._open_settings)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not get_api_key():
            self._prompt_for_settings_before_first_use()

    def _prompt_for_settings_before_first_use(self) -> None:
        """Spec section 4.1: on first launch with no key, Settings opens
        modally *before* any file operation is enabled."""
        self._set_file_operations_enabled(False)
        dialog = SettingsDialog(self)
        dialog.exec()
        self._set_file_operations_enabled(True)

    def _set_file_operations_enabled(self, enabled: bool) -> None:
        self._open_button.setEnabled(enabled)

    def _open_settings(self) -> None:
        SettingsDialog(self).exec()

    def _on_open(self) -> None:
        path_str, _filter = QFileDialog.getOpenFileName(
            self, "Open manuscript", "", "Word documents (*.docx)"
        )
        if not path_str:
            return
        output_dir_str = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if not output_dir_str:
            return

        self._source = Path(path_str)
        self._output_dir = Path(output_dir_str)
        self._run_pipeline(section_overrides=None)

    def _on_overrides_applied(self, overrides: dict[str, str]) -> None:
        if not overrides:
            return
        self._run_pipeline(section_overrides=overrides)

    def _run_pipeline(self, *, section_overrides: dict[str, str] | None) -> None:
        if self._source is None or self._output_dir is None:
            return
        options = PipelineOptions(
            output_dir=self._output_dir,
            api_key=get_api_key(),
            section_overrides=section_overrides,
        )
        self._set_file_operations_enabled(False)
        self._progress_bar.setValue(0)
        self._status_label.setText(f"Validating {self._source.name}...")

        worker = PipelineWorker(self._source, options)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.failed.connect(self._on_failed)
        self._thread_pool.start(worker)

    def _on_progress(self, stage: str, fraction: float) -> None:
        self._progress_bar.setValue(int(fraction * 100))
        self._status_label.setText(stage)

    def _on_finished(self, result: PipelineResult) -> None:
        self._set_file_operations_enabled(True)
        self._status_label.setText(
            f"{result.violation_count} violation(s): {result.fixed_count} fixed, "
            f"{result.needs_review_count} need review"
        )
        if result.report is not None:
            self._report_view.set_report(result.report)
        if result.ast is not None:
            self._override_panel.set_ast(result.ast)

    def _on_failed(self, message: str) -> None:
        self._set_file_operations_enabled(True)
        self._status_label.setText("Failed.")
        QMessageBox.critical(self, "Validation failed", message)


__all__ = ["MainWindow"]
