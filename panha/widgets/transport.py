"""Transport bar with in-app audio preview (QMediaPlayer)."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)


@contextlib.contextmanager
def _quiet_c_stderr():
    """Temporarily redirect C-level fd 2 (stderr) to devnull.

    Qt multimedia's embedded FFmpeg writes ``Input #0, <format>, from
    '<path>':`` and stream info to the process's C stderr (fd 2) via
    ``av_log``.  This bypasses Qt's logging framework entirely so
    ``QT_LOGGING_RULES`` has no effect on it.

    We redirect fd 2 around ``QMediaPlayer.setSource()`` which is when
    FFmpeg opens/probes the container.  The redirect is restored in the
    ``finally`` block so our own Python-level error output is unaffected
    once the call returns.  On failure (e.g. read-only fds) we yield
    without redirecting — a no-op is always safe.
    """
    devnull_fd: int | None = None
    saved_fd: int | None = None
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        saved_fd = os.dup(2)
        os.dup2(devnull_fd, 2)
    except OSError:
        # Can't redirect — yield without suppression (never fatal)
        if devnull_fd is not None:
            try:
                os.close(devnull_fd)
            except OSError:
                pass
        yield
        return
    try:
        yield
    finally:
        try:
            if saved_fd is not None:
                os.dup2(saved_fd, 2)
                os.close(saved_fd)
            if devnull_fd is not None:
                os.close(devnull_fd)
        except OSError:
            pass


def _format_ms(ms: int) -> str:
    if ms <= 0:
        return "0:00"
    seconds = ms // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"


class TransportBar(QWidget):
    """Compact playback transport: prev / play / next + BYPASS + scrubber.

    Emits :attr:`prev_requested` / :attr:`next_requested` so the parent
    window can advance the currently-selected queue row. Emits
    :attr:`bypass_changed` whenever the BYPASS button is toggled.
    """

    prev_requested = pyqtSignal()
    next_requested = pyqtSignal()
    bypass_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("transportBar")

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_state)

        self._user_seeking = False
        self._bypass = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self.btn_prev = QPushButton("\u23ee")
        self.btn_prev.setObjectName("transportBtn")
        self.btn_prev.setToolTip("Previous (select previous queue row)")
        self.btn_prev.clicked.connect(self.prev_requested.emit)

        self.btn_play = QPushButton("\u25b6")
        self.btn_play.setObjectName("transportPlay")
        self.btn_play.setToolTip("Play / Pause")
        self.btn_play.clicked.connect(self.toggle_play)

        self.btn_next = QPushButton("\u23ed")
        self.btn_next.setObjectName("transportBtn")
        self.btn_next.setToolTip("Next (select next queue row)")
        self.btn_next.clicked.connect(self.next_requested.emit)

        self.btn_bypass = QPushButton("BYPASS")
        self.btn_bypass.setObjectName("transportBypass")
        self.btn_bypass.setCheckable(True)
        self.btn_bypass.setToolTip(
            "Disable the mastering chain. When pressed, exports use "
            "stream-copy and the slider panel is dimmed."
        )
        self.btn_bypass.toggled.connect(self._on_bypass_toggled)

        self.lbl_position = QLabel("0:00")
        self.lbl_position.setObjectName("transportTime")
        self.lbl_duration = QLabel("0:00")
        self.lbl_duration.setObjectName("transportTime")

        self.scrubber = QSlider(Qt.Orientation.Horizontal)
        self.scrubber.setObjectName("transportScrubber")
        self.scrubber.setRange(0, 0)
        self.scrubber.sliderPressed.connect(self._on_seek_start)
        self.scrubber.sliderReleased.connect(self._on_seek_end)

        layout.addWidget(self.btn_prev)
        layout.addWidget(self.btn_play)
        layout.addWidget(self.btn_next)
        layout.addWidget(self.btn_bypass)
        layout.addWidget(self.lbl_position)
        layout.addWidget(self.scrubber, 1)
        layout.addWidget(self.lbl_duration)

    # -- public API ----------------------------------------------------

    def load_source(self, path: str | Path | None) -> None:
        """Load ``path`` for preview. Pass ``None`` to clear."""
        if not path:
            self._player.stop()
            self._player.setSource(QUrl())
            self.lbl_position.setText("0:00")
            self.lbl_duration.setText("0:00")
            self.scrubber.setRange(0, 0)
            return
        url = QUrl.fromLocalFile(str(Path(path).resolve()))
        # Suppress FFmpeg's raw "Input #0, wav, from '...'" log that Qt
        # multimedia writes directly to C stderr (fd 2) when opening a file.
        with _quiet_c_stderr():
            self._player.setSource(url)

    def toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def stop(self) -> None:
        self._player.stop()

    def is_bypassed(self) -> bool:
        return self._bypass

    def set_bypass(self, bypass: bool) -> None:
        """Programmatically set BYPASS state without re-emitting if unchanged."""
        if self.btn_bypass.isChecked() != bool(bypass):
            self.btn_bypass.setChecked(bool(bypass))

    # -- player callbacks ---------------------------------------------

    def _on_position(self, ms: int) -> None:
        if not self._user_seeking:
            self.scrubber.setValue(int(ms))
        self.lbl_position.setText(_format_ms(int(ms)))

    def _on_duration(self, ms: int) -> None:
        self.scrubber.setRange(0, max(0, int(ms)))
        self.lbl_duration.setText(_format_ms(int(ms)))

    def _on_state(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("\u23f8")
        else:
            self.btn_play.setText("\u25b6")

    def _on_seek_start(self) -> None:
        self._user_seeking = True

    def _on_seek_end(self) -> None:
        self._user_seeking = False
        self._player.setPosition(int(self.scrubber.value()))

    def _on_bypass_toggled(self, checked: bool) -> None:
        self._bypass = bool(checked)
        self.bypass_changed.emit(self._bypass)
