"""Settings dialog: API key entry and connection test (spec section 4.1).

Talks to `config.settings_store` only through its module-level functions
(`get_api_key`/`set_api_key`), which dispatch to whichever `SecretBox` the
platform provides -- this dialog never imports DPAPI or Fernet directly, so
it works unchanged on the dev backend (Linux) and DPAPI (Windows).

"Test connection" calls `client.models.list()` -- a real authentication check
that consumes no generation quota.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from manuscript_validator.config import get_api_key, set_api_key
from manuscript_validator.logging_setup import get_redacting_filter
from manuscript_validator.rules.llm_client import GeminiSemanticClient


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)

        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        existing_key = get_api_key()
        if existing_key:
            self._key_edit.setText(existing_key)
            get_redacting_filter().register_secret(existing_key)

        self._show_checkbox = QCheckBox("Show")
        self._show_checkbox.toggled.connect(self._on_show_toggled)

        self._status_label = QLabel(
            "Semantic checks (section ordering, exact phrasing, content "
            "presence) require a Gemini API key."
        )
        self._status_label.setWordWrap(True)

        key_row = QHBoxLayout()
        key_row.addWidget(self._key_edit)
        key_row.addWidget(self._show_checkbox)
        key_row_widget = QWidget()
        key_row_widget.setLayout(key_row)

        form = QFormLayout()
        form.addRow("Gemini API key:", key_row_widget)

        test_button = QPushButton("Test connection")
        test_button.clicked.connect(self._on_test_connection)

        save_button = QPushButton("Save")
        save_button.setDefault(True)
        save_button.clicked.connect(self._on_save)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addWidget(test_button)
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._status_label)
        layout.addLayout(button_row)

    def _on_show_toggled(self, checked: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self._key_edit.setEchoMode(mode)

    def _on_test_connection(self) -> None:
        key = self._key_edit.text().strip()
        if not key:
            self._status_label.setText("Enter a key first.")
            return
        self._status_label.setText("Testing...")
        client = GeminiSemanticClient(api_key=key)
        ok = client.test_connection()
        self._status_label.setText(
            "Connection successful." if ok else "Connection failed. Check the key and try again."
        )

    def _on_save(self) -> None:
        key = self._key_edit.text().strip()
        if key:
            get_redacting_filter().register_secret(key)
            set_api_key(key)
        self.accept()

    def has_key(self) -> bool:
        return bool(get_api_key())


__all__ = ["SettingsDialog"]
