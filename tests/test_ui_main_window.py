"""Task 14 exit criteria (main-window half): first launch with no key opens
Settings modally before any file operation is enabled (spec section 4.1),
and running the pipeline end to end populates the report view and override
panel without touching a real file dialog.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fixtures.factory import violating
from manuscript_validator.ui.main_window import MainWindow
from manuscript_validator.ui.settings_window import SettingsDialog

pytestmark = pytest.mark.gui


@pytest.fixture
def _no_stored_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("manuscript_validator.ui.main_window.get_api_key", lambda: None)


@pytest.fixture
def _has_stored_key(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_key = "AIzaEXISTINGEXISTINGEXISTINGEXISTIN"
    monkeypatch.setattr("manuscript_validator.ui.main_window.get_api_key", lambda: fake_key)


def test_first_launch_with_no_key_opens_settings_modally(
    qtbot, _no_stored_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = []
    monkeypatch.setattr(SettingsDialog, "exec", lambda self: opened.append(True))

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert opened == [True]


def test_launch_with_a_stored_key_never_opens_settings(
    qtbot, _has_stored_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = []
    monkeypatch.setattr(SettingsDialog, "exec", lambda self: opened.append(True))

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert opened == []
    assert window._open_button.isEnabled()


def test_running_the_pipeline_populates_report_view_and_override_panel(
    qtbot, _has_stored_key: None, tmp_path: Path
) -> None:
    doc, _handles = violating("title-size")
    source = tmp_path / "paper.docx"
    doc.save(source)

    window = MainWindow()
    qtbot.addWidget(window)
    window._source = source
    window._output_dir = tmp_path / "out"

    window._run_pipeline(section_overrides=None)
    qtbot.waitUntil(lambda: window._open_button.isEnabled(), timeout=15_000)

    assert window._report_view.rowCount() > 0
    assert window._override_panel._table.rowCount() > 0
    assert "violation(s)" in window.statusBar().currentMessage()


def test_opening_a_file_derives_output_dir_from_its_stem_with_no_directory_prompt(
    qtbot, _has_stored_key: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QFileDialog

    doc, _handles = violating("title-size")
    source = tmp_path / "paper.docx"
    doc.save(source)

    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(source), ""))
    )
    directory_prompted = []
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *a, **k: directory_prompted.append(True) or ""),
    )

    window = MainWindow()
    qtbot.addWidget(window)

    window._on_open()

    assert directory_prompted == []
    assert window._output_dir == tmp_path / "paper"
    assert window._output_dir.is_dir()

    qtbot.waitUntil(lambda: window._open_button.isEnabled(), timeout=15_000)


def test_failed_run_shows_an_error_and_re_enables_file_operations(
    qtbot, _has_stored_key: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: shown.append(a)))

    window = MainWindow()
    qtbot.addWidget(window)
    window._source = tmp_path / "does_not_exist.docx"
    window._output_dir = tmp_path / "out"

    window._run_pipeline(section_overrides=None)
    qtbot.waitUntil(lambda: window._open_button.isEnabled(), timeout=15_000)

    assert shown  # QMessageBox.critical was called with the error
