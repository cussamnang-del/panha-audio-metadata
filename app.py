"""Application bootstrap."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from . import __app_name__
from .main_window import MainWindow
from .ui import DARK_STYLESHEET


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv or sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName("Panha")
    app.setStyleSheet(DARK_STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()
