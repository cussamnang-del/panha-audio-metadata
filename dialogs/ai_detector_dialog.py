"""AI Music Detector dialog.

Lets the user drop or pick audio files and shows a table with the
filename, source platform, detection confidence and a human/AI verdict.

The detection backend itself is *not* implemented yet — there's no
shared service to call into. Every row therefore starts with placeholder
``\u2014`` values and surfaces an "AI detection not implemented yet" tooltip
on the analysis columns so the UI is honest about its current state.

The dialog is designed so a real analyser can be plugged in later by
calling :meth:`AIDetectorDialog.set_row_result` for each file from a
background worker — no UI restructuring required.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
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

SUPPORTED_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac"}
_PLACEHOLDER = "\u2014"  # em dash
_PLACEHOLDER_TOOLTIP = "AI detection is not implemented yet."


@dataclasses.dataclass
class DetectorRow:
    """Per-file row state shown in the detector table."""

    path: str
    platform: str = _PLACEHOLDER
    confidence: str = _PLACEHOLDER
    verdict: str = _PLACEHOLDER

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)


class AIDetectorDialog(QDialog):
    """Modal-less dialog that lists files queued for AI analysis."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI Music Detector")
        self.setModal(False)
        self.setAcceptDrops(True)
        self.resize(720, 460)

        self._rows: list[DetectorRow] = []
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
        """Add the given audio files; returns the number actually added."""
        existing = {row.path for row in self._rows}
        added = 0
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
            added += 1
        if added:
            self._refresh_table()
        return added

    def set_row_result(
        self,
        index: int,
        *,
        platform: str | None = None,
        confidence: str | None = None,
        verdict: str | None = None,
    ) -> None:
        """Update the per-file analysis fields. Used by a future backend."""
        if not (0 <= index < len(self._rows)):
            return
        row = self._rows[index]
        if platform is not None:
            row.platform = platform
        if confidence is not None:
            row.confidence = confidence
        if verdict is not None:
            row.verdict = verdict
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

    # -- table ---------------------------------------------------------

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self._rows))
        for row_idx, row in enumerate(self._rows):
            cells = (row.filename, row.platform, row.confidence, row.verdict)
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setToolTip(row.path)
                elif value == _PLACEHOLDER:
                    item.setToolTip(_PLACEHOLDER_TOOLTIP)
                if col == 3 and value.lower() == "ai":
                    item.setForeground(Qt.GlobalColor.red)
                elif col == 3 and value.lower() == "human":
                    item.setForeground(Qt.GlobalColor.green)
                self.table.setItem(row_idx, col, item)

    # -- drag & drop ---------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
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
