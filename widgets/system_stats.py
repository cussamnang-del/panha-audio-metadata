"""Status-bar widget showing CPU and RAM usage.

The widget polls :mod:`psutil` at a configurable interval (default 1 s)
via a single :class:`QTimer` so it remains cheap even when many copies
exist. Polling stops automatically when the widget is destroyed.
"""

from __future__ import annotations

import psutil
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget


class SystemStatsWidget(QWidget):
    """Label pair that displays current CPU and RAM utilisation."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        interval_ms: int = 1000,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("systemStats")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._cpu_label = QLabel("CPU: --%")
        self._cpu_label.setObjectName("statusStat")
        self._ram_label = QLabel("RAM: --%")
        self._ram_label.setObjectName("statusStat")

        layout.addWidget(self._cpu_label)
        layout.addWidget(self._ram_label)

        # Prime psutil so the first reading isn't always 0.0.
        psutil.cpu_percent(interval=None)

        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    def cpu_text(self) -> str:
        return self._cpu_label.text()

    def ram_text(self) -> str:
        return self._ram_label.text()

    def stop(self) -> None:
        self._timer.stop()

    def _refresh(self) -> None:
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        self._cpu_label.setText(f"CPU: {cpu:.0f}%")
        self._ram_label.setText(f"RAM: {ram:.0f}%")
