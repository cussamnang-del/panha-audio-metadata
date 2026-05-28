"""Application bootstrap."""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Suppress Qt multimedia's own verbose log BEFORE QApplication is created.
# Qt multimedia's internal FFmpeg backend prints its version/copyright line
# via Qt's logging system; turning it off avoids the
#   qt.multimedia.ffmpeg: Using Qt multimedia with FFmpeg version …
# line that otherwise clutters every terminal session.
# ---------------------------------------------------------------------------
os.environ.setdefault(
    "QT_LOGGING_RULES",
    "qt.multimedia.ffmpeg=false;qt.multimedia=false",
)

from PyQt6.QtCore import QtMsgType, qInstallMessageHandler  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from . import __app_name__  # noqa: E402
from .main_window import MainWindow  # noqa: E402
from .ui import DARK_STYLESHEET  # noqa: E402

# ---------------------------------------------------------------------------
# Patterns that are known-benign Qt warnings we don't want to surface:
#
# • "QFont::setPointSize: Point size <= 0 (-1)" — Qt6 HiDPI font resolution
#   emits this when a widget's default QFont hasn't been resolved yet by the
#   style engine (point size == -1 is Qt's "unset" sentinel). It fires
#   harmlessly during QMediaPlayer file loading on Windows and never affects
#   rendering.
# ---------------------------------------------------------------------------
_SUPPRESS = (
    "QFont::setPointSize: Point size <= 0",
    "QFont::setPixelSize: Pixel size <= 0",
)


def _qt_message_handler(
    msg_type: QtMsgType, _context: object, message: str
) -> None:
    """Custom Qt message handler that filters known benign noise."""
    if any(pat in message for pat in _SUPPRESS):
        return
    # Critical / fatal messages still go to stderr so CI and devs see them.
    if msg_type in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
        print(f"[Qt] {message}", file=sys.stderr, flush=True)


qInstallMessageHandler(_qt_message_handler)


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv or sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName("Panha")
    app.setStyleSheet(DARK_STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()
