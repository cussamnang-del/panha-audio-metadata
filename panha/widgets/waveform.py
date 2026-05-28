"""Decorative animated waveform shown at the bottom of the main window."""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget


class WaveformView(QWidget):
    """A purely decorative animated sine-wave waveform.

    Used as a visual cue while a batch export is running; matches the
    aesthetic of the reference UI without doing any real audio analysis.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._tick)
        self._active = False

    def setActive(self, active: bool) -> None:  # noqa: N802 (Qt-style camelCase API)
        self._active = active
        if active:
            self._timer.start()
        else:
            self._timer.stop()
            self.update()

    def _tick(self) -> None:
        self._phase += 0.18
        if self._phase > math.tau * 16:
            self._phase = 0.0
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        mid = h / 2

        # background fill
        painter.fillRect(self.rect(), QColor("#0d1726"))

        gradient = QLinearGradient(0, 0, w, 0)
        gradient.setColorAt(0.0, QColor("#1f5fcf"))
        gradient.setColorAt(1.0, QColor("#5fa8ff"))
        pen = QPen(gradient, 1.5)
        painter.setPen(pen)

        path = QPainterPath()
        step = 2
        amplitude = h * 0.32
        if not self._active:
            amplitude *= 0.45
        for x in range(0, w + 1, step):
            t = x / max(w, 1)
            value = (
                math.sin(t * math.tau * 3 + self._phase)
                + 0.55 * math.sin(t * math.tau * 7 - self._phase * 1.3)
                + 0.30 * math.sin(t * math.tau * 11 + self._phase * 0.7)
            )
            y = mid + value * amplitude * 0.35
            if x == 0:
                path.moveTo(QPointF(x, y))
            else:
                path.lineTo(QPointF(x, y))
        painter.drawPath(path)
