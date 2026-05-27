"""Aggregated 'Config' dialog — replaces the old toolbar.

The X-MIXM layout reserves a single ``Config`` button in the Setting
Console header. This dialog gathers every batch-level action (add files,
add folder, pick output folder, edit metadata template, start/stop the
export) into one place so the main window can stay visually clean.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ConfigDialog(QDialog):
    """Action launcher dialog.

    Emits one of the named action signals when the corresponding button
    is clicked. The parent window wires them to its existing handlers.
    The dialog itself is non-modal so multiple clicks (e.g., Add Files →
    Add Folder) don't require reopening.
    """

    add_files_requested = pyqtSignal()
    add_folder_requested = pyqtSignal()
    output_folder_requested = pyqtSignal()
    file_information_requested = pyqtSignal()
    export_settings_requested = pyqtSignal()
    start_export_requested = pyqtSignal()
    stop_export_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Config")
        self.setModal(False)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        heading = QLabel("Batch Actions")
        heading.setObjectName("sectionTitle")
        heading.setStyleSheet("font-size:14px;")
        layout.addWidget(heading)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        def add(row: int, col: int, text: str, signal: pyqtSignal) -> QPushButton:
            btn = QPushButton(text)
            btn.setObjectName("configActionBtn")
            btn.setMinimumHeight(34)
            btn.clicked.connect(signal.emit)
            grid.addWidget(btn, row, col)
            return btn

        self.btn_add_files = add(0, 0, "Add Files", self.add_files_requested)
        self.btn_add_folder = add(0, 1, "Add Folder", self.add_folder_requested)
        self.btn_output = add(1, 0, "Output Folder", self.output_folder_requested)
        self.btn_file_info = add(1, 1, "File Information", self.file_information_requested)
        self.btn_export_settings = add(2, 0, "Export Settings", self.export_settings_requested)
        # The Start / Stop pair is the most operationally important — give
        # it its own row so it doesn't get lost.
        self.btn_start = QPushButton("Start Export")
        self.btn_start.setObjectName("configStartBtn")
        self.btn_start.setMinimumHeight(36)
        self.btn_start.clicked.connect(self.start_export_requested.emit)
        self.btn_stop = QPushButton("Stop Export")
        self.btn_stop.setObjectName("configStopBtn")
        self.btn_stop.setMinimumHeight(36)
        self.btn_stop.clicked.connect(self.stop_export_requested.emit)
        grid.addWidget(self.btn_start, 3, 0)
        grid.addWidget(self.btn_stop, 3, 1)

        layout.addLayout(grid)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons, alignment=Qt.AlignmentFlag.AlignRight)

    def set_export_running(self, running: bool) -> None:
        """Enable/disable Start vs Stop based on worker state."""
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
