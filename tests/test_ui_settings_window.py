"""Task 14 exit criteria (settings-dialog half): the dialog talks to
`config.settings_store` only through its public functions, so redirecting
where those read/write (a temp config path, the dev secret box) is enough to
test it fully -- no real DPAPI, no real network call for "Test connection"
beyond what `llm_client` already proves never raises.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QLineEdit

from manuscript_validator.config import settings_store
from manuscript_validator.config.settings_store_dev import FernetSecretBox
from manuscript_validator.rules.llm_client import GeminiSemanticClient
from manuscript_validator.ui.settings_window import SettingsDialog

pytestmark = pytest.mark.gui


@pytest.fixture
def _redirected_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Every `get_api_key()`/`set_api_key()` call the dialog makes lands in
    `tmp_path`, using the dev backend, regardless of platform or env var."""
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(settings_store, "config_path", lambda: config_path)
    monkeypatch.setattr(settings_store, "default_secret_box", lambda: FernetSecretBox())
    return config_path


def test_dialog_starts_empty_with_no_stored_key(qtbot, _redirected_store: Path) -> None:
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    assert dialog._key_edit.text() == ""


def test_dialog_prefills_an_existing_stored_key(qtbot, _redirected_store: Path) -> None:
    settings_store.set_api_key("AIzaEXISTINGEXISTINGEXISTINGEXISTIN")
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    assert dialog._key_edit.text() == "AIzaEXISTINGEXISTINGEXISTINGEXISTIN"


def test_key_field_is_masked_by_default_and_show_toggle_reveals_it(
    qtbot, _redirected_store: Path
) -> None:
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    assert dialog._key_edit.echoMode() == QLineEdit.EchoMode.Password

    dialog._show_checkbox.setChecked(True)
    assert dialog._key_edit.echoMode() == QLineEdit.EchoMode.Normal

    dialog._show_checkbox.setChecked(False)
    assert dialog._key_edit.echoMode() == QLineEdit.EchoMode.Password


def test_save_persists_the_key_via_the_settings_store(qtbot, _redirected_store: Path) -> None:
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog._key_edit.setText("AIzaNEWNEWNEWNEWNEWNEWNEWNEWNEWNEWN")

    dialog._on_save()

    assert settings_store.get_api_key() == "AIzaNEWNEWNEWNEWNEWNEWNEWNEWNEWNEWN"


def test_cancel_does_not_persist_the_key(qtbot, _redirected_store: Path) -> None:
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog._key_edit.setText("AIzaSHOULDNOTBESAVEDSHOULDNOTBESAVED")

    dialog.reject()

    assert settings_store.get_api_key() is None


def test_test_connection_with_empty_field_shows_a_message_and_does_not_crash(
    qtbot, _redirected_store: Path
) -> None:
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog._key_edit.setText("")

    dialog._on_test_connection()

    assert "Enter a key" in dialog._status_label.text()


@pytest.mark.parametrize(("connected", "expected_text"), [
    (True, "Connection successful."),
    (False, "Connection failed. Check the key and try again."),
])
def test_test_connection_reports_the_client_result_without_a_real_network_call(
    qtbot,
    _redirected_store: Path,
    monkeypatch: pytest.MonkeyPatch,
    connected: bool,
    expected_text: str,
) -> None:
    monkeypatch.setattr(GeminiSemanticClient, "test_connection", lambda self: connected)
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    dialog._key_edit.setText("AIzaOBVIOUSLYFAKEOBVIOUSLYFAKEOBVIOU")

    dialog._on_test_connection()

    assert dialog._status_label.text() == expected_text
