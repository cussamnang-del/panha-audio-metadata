"""AI Music Detector dialog.

Lets the user drop or pick audio files and shows a table with the
filename, source platform, detection confidence and a human/AI verdict.

Detection runs in a background ``QRunnable`` (see :mod:`panha.detector`)
so dragging in dozens of files doesn't freeze the UI. The detector is
heuristic — it looks for Suno-style fingerprints in the file's metadata
(URLs, encoder strings, custom ID3 frames) and falls back to ``HUMAN``
when no markers are found.

The :meth:`AIDetectorDialog.set_row_result` API is preserved so a future
ML-based backend can fill in richer values without restructuring the UI.
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QDragEnterEvent, QDropEvent, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..detector import (
    VERDICT_AI,
    VERDICT_HUMAN,
    VERDICT_UNKNOWN,
    DetectorResult,
    schedule_detection,
)

SUPPORTED_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac"}
_PLACEHOLDER = "\u2014"  # em dash
_ANALYZING = "Analyzing\u2026"

_COLOR_AI = QColor("#ff5252")        # red — matches reference screenshot
_COLOR_HUMAN = QColor("#5fa8ff")     # accent blue — matches HUMAN-MADE screenshot
_COLOR_UNKNOWN = QColor("#8aa0c0")   # muted blue-gray
_COLOR_ANALYZING = QColor("#5fa8ff") # accent blue

# Verdict-string vocab used by :meth:`AIDetectorDialog.set_row_result`
# and :meth:`_render_row` so callers can push raw strings (legacy paths,
# tests, external detectors) without us missing the AI/Human classification.
# The strings are matched after ``.strip().lower()``.
_AI_VERDICT_STRINGS = frozenset({
    "ai",
    "ai-generated",
    "ai generated",
    "suno",
    "suno ai",
    "suno-ai",
    "udio",
    "boomy",
    "aiva",
    "mubert",
    "stable audio",
    "musicgen",
})
_HUMAN_VERDICT_STRINGS = frozenset({
    "human",
    "human-made",
    "human made",
    "human-written",
    "original",
    "real",
})


@dataclasses.dataclass
class DetectorRow:
    """Per-file row state shown in the detector table."""

    path: str
    platform: str = _PLACEHOLDER
    confidence: str = _PLACEHOLDER
    verdict: str = _PLACEHOLDER
    is_ai: bool = False
    analyzing: bool = True
    tooltip: str = ""

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)


class AIDetectorDialog(QDialog):
    """Modal-less dialog that lists files queued for AI analysis."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        schedule_fn: Callable[..., object] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI Music Detector")
        self.setModal(False)
        self.setAcceptDrops(True)
        self.resize(720, 460)

        self._rows: list[DetectorRow] = []
        # Allow tests to inject a synchronous detection scheduler so they
        # don't have to spin up a real QThreadPool.
        self._schedule_fn = schedule_fn or schedule_detection
        self._build_ui()
        self._refresh_table()

    # -- ui -------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)

        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        self.lbl_title = QLabel("AI Music Detector")
        self.lbl_title.setObjectName("aiDetectorTitle")
        self.lbl_subtitle = QLabel(
            "Drop audio files \u2014 analyzes AI automatically"
        )
        self.lbl_subtitle.setObjectName("aiDetectorSubtitle")
        title_block.addWidget(self.lbl_title)
        title_block.addWidget(self.lbl_subtitle)
        header.addLayout(title_block, 1)

        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("aiDetectorClose")
        self.btn_close.setMinimumWidth(96)
        self.btn_close.clicked.connect(self.close)
        header.addWidget(self.btn_close, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        self.header_divider = self._build_divider()
        root.addWidget(self.header_divider)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.btn_add = QPushButton("Add Files")
        self.btn_add.setObjectName("aiDetectorPrimary")
        self.btn_add.setMinimumWidth(108)
        self.btn_add.clicked.connect(self._on_add_files)
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setObjectName("aiDetectorSecondary")
        self.btn_clear.setMinimumWidth(96)
        self.btn_clear.clicked.connect(self._on_clear)
        actions.addWidget(self.btn_add)
        actions.addWidget(self.btn_clear)
        actions.addStretch(1)
        root.addLayout(actions)

        self.table_divider = self._build_divider()
        root.addWidget(self.table_divider)

        self.table = QTableWidget(0, 4)
        self.table.setObjectName("aiDetectorTable")
        self.table.setHorizontalHeaderLabels(
            ["Filename", "Platform", "Confidence", "Human or AI"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        header_view = self.table.horizontalHeader()
        header_view.setHighlightSections(False)
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table, 1)

    @staticmethod
    def _build_divider() -> QFrame:
        divider = QFrame()
        divider.setObjectName("aiDetectorDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        divider.setFixedHeight(1)
        return divider

    # -- public API ----------------------------------------------------

    def rows(self) -> list[DetectorRow]:
        return list(self._rows)

    def add_paths(self, paths: list[str]) -> int:
        """Add the given audio files; returns the number actually added.

        Newly added files are immediately scheduled for background AI
        detection. Their analysis columns show ``"Analyzing\u2026"`` until
        the result lands.
        """
        existing = {row.path for row in self._rows}
        added: list[str] = []
        for raw in paths:
            path = os.path.abspath(raw)
            if path in existing:
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext not in SUPPORTED_EXTS:
                continue
            if not os.path.isfile(path):
                continue
            self._rows.append(DetectorRow(path=path))
            existing.add(path)
            added.append(path)
        if added:
            self._refresh_table()
            for path in added:
                self._schedule_fn(path, self._on_detection_finished)
        return len(added)

    def set_row_result(
        self,
        index: int,
        *,
        platform: str | None = None,
        confidence: str | None = None,
        verdict: str | None = None,
    ) -> None:
        """Update a row's analysis columns directly.

        Kept for backward compatibility with callers that have their own
        detector and want to push raw display strings. The richer
        :meth:`apply_detection_result` is preferred for in-app detection.

        The ``verdict`` string is matched against
        :data:`_AI_VERDICT_STRINGS` / :data:`_HUMAN_VERDICT_STRINGS`
        after lowercasing, so callers can pass any of the canonical
        strings (``"AI"``, ``"Suno AI"``, ``"HUMAN-MADE"``, ...).
        Both the platform label and verdict are also inspected — that
        way a caller writing ``platform="Suno"`` plus ``verdict="AI"``
        is recognised as AI even if the verdict string itself was
        ambiguous.
        """
        if not (0 <= index < len(self._rows)):
            return
        row = self._rows[index]
        row.analyzing = False
        if platform is not None:
            row.platform = platform
        if confidence is not None:
            row.confidence = confidence
        if verdict is not None:
            row.verdict = verdict
            row.is_ai = self._verdict_is_ai(verdict, platform=platform or row.platform)
        self._refresh_table()

    @staticmethod
    def _verdict_is_ai(verdict: str, *, platform: str = "") -> bool:
        """Heuristic: is this verdict / platform combo an AI label?

        The detector backend emits canonical ``VERDICT_AI`` /
        ``VERDICT_HUMAN`` strings, but :meth:`set_row_result` is also
        called from tests and external code that pass raw strings like
        ``"AI"``, ``"Suno AI"``, ``"Human"``. Centralising the match
        here keeps the dialog's colouring and the ``is_ai`` flag in
        agreement.
        """
        verdict_norm = (verdict or "").strip().lower()
        if verdict_norm in _AI_VERDICT_STRINGS or verdict_norm == VERDICT_AI.lower():
            return True
        if verdict_norm in _HUMAN_VERDICT_STRINGS or verdict_norm == VERDICT_HUMAN.lower():
            return False
        platform_norm = (platform or "").strip().lower()
        # If the platform column screams "Suno" / "Udio" / ..., the row
        # is AI even if the verdict string is something ambiguous like
        # "detected" or empty.
        if any(
            ai_label in platform_norm
            for ai_label in ("suno", "udio", "boomy", "aiva", "mubert", "musicgen", "stable audio")
        ):
            return True
        return False

    def apply_detection_result(self, index: int, result: DetectorResult) -> None:
        """Apply a :class:`DetectorResult` to the row at ``index``."""
        if not (0 <= index < len(self._rows)):
            return
        row = self._rows[index]
        row.analyzing = False
        row.platform = result.platform_text
        row.confidence = result.confidence_text
        row.verdict = result.verdict
        row.is_ai = result.is_ai
        row.tooltip = result.reason
        self._refresh_table()

    # -- slots ---------------------------------------------------------

    def _on_add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add audio files",
            str(Path.home()),
            "Audio (*.mp3 *.wav *.flac *.m4a *.ogg *.aac)",
        )
        if files:
            self.add_paths(list(files))

    def _on_clear(self) -> None:
        self._rows.clear()
        self._refresh_table()

    def _on_detection_finished(self, path: str, result: DetectorResult) -> None:
        for idx, row in enumerate(self._rows):
            if row.path == path:
                self.apply_detection_result(idx, result)
                return

    # -- table ---------------------------------------------------------

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self._rows))
        for row_idx, row in enumerate(self._rows):
            self._render_row(row_idx, row)

    def _render_row(self, row_idx: int, row: DetectorRow) -> None:
        # Filename column: plain white text, full path on hover.
        name_item = QTableWidgetItem(row.filename)
        name_item.setToolTip(row.path)
        self.table.setItem(row_idx, 0, name_item)

        if row.analyzing:
            self._render_analyzing_cell(row_idx, 1)
            self._render_analyzing_cell(row_idx, 2)
            self._render_analyzing_cell(row_idx, 3)
            return

        # Pick the colour scheme from the verdict so AI-generated rows
        # match the red-on-dark look of the reference screenshot, and
        # human-detected rows show the calmer blue accent. We check
        # ``is_ai`` first so any caller that explicitly flagged the
        # row (e.g. via the detector backend or a raw "Suno" string in
        # set_row_result) wins over text-based heuristics.
        if row.is_ai or row.verdict == VERDICT_AI:
            colour = _COLOR_AI
        elif row.verdict == VERDICT_HUMAN:
            colour = _COLOR_HUMAN
        elif row.verdict == VERDICT_UNKNOWN:
            colour = _COLOR_UNKNOWN
        else:
            # Backward-compat strings ("AI", "Human", "Suno AI", ...)
            # routed through set_row_result; the shared verdict-string
            # sets keep this branch in sync with ``_verdict_is_ai``.
            verdict_lower = row.verdict.strip().lower()
            if verdict_lower in _AI_VERDICT_STRINGS:
                colour = _COLOR_AI
            elif verdict_lower in _HUMAN_VERDICT_STRINGS:
                colour = _COLOR_HUMAN
            else:
                colour = _COLOR_UNKNOWN

        platform_item = self._make_coloured_item(row.platform, colour)
        confidence_item = self._make_coloured_item(row.confidence, colour)
        verdict_item = self._make_coloured_item(row.verdict, colour, bold=True)

        if row.tooltip:
            for item in (platform_item, confidence_item, verdict_item):
                item.setToolTip(row.tooltip)

        self.table.setItem(row_idx, 1, platform_item)
        self.table.setItem(row_idx, 2, confidence_item)
        self.table.setItem(row_idx, 3, verdict_item)

    def _render_analyzing_cell(self, row_idx: int, col: int) -> None:
        item = QTableWidgetItem(_ANALYZING)
        item.setForeground(QBrush(_COLOR_ANALYZING))
        font = item.font()
        font.setItalic(True)
        item.setFont(font)
        item.setToolTip("Analyzing audio metadata for AI fingerprints\u2026")
        self.table.setItem(row_idx, col, item)

    @staticmethod
    def _make_coloured_item(
        text: str, colour: QColor, *, bold: bool = False
    ) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setForeground(QBrush(colour))
        # PyQt's QTableWidgetItem.font() returns a *copy*, so we have to
        # build the QFont once and assign it back. Doing it in one place
        # avoids the bold-on-copy-then-discarded bug.
        font = QFont(item.font())
        font.setBold(bold)
        font.setItalic(False)
        item.setFont(font)
        return item

    # -- drag & drop ---------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        mime = event.mimeData()
        if mime is not None and mime.hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        # Without an explicit dragMoveEvent some window managers refuse
        # to deliver the drop, so accept it here too.
        mime = event.mimeData()
        if mime is not None and mime.hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        mime = event.mimeData()
        if mime is None or not mime.hasUrls():
            event.ignore()
            return
        paths: list[str] = []
        for url in mime.urls():
            if url.isLocalFile():
                paths.append(url.toLocalFile())
        if paths:
            self.add_paths(paths)
            event.acceptProposedAction()
        else:
            event.ignore()
