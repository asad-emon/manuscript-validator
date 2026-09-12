"""Qt application bootstrap -- the only Qt entry point (Task 14)."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from manuscript_validator.logging_setup import configure_logging
from manuscript_validator.ui.main_window import MainWindow


def main() -> int:
    """Launch the desktop UI."""
    configure_logging()
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
