"""Main application window for Panha Audio Meta Data.

Layout is modelled on the X-MIXM reference design:

    [ header ]
    [ Batch Queue table + progress ]
    [ Setting Console: template row + 13-slider mastering grid ]
    [ Waveform footer ]
    [ Transport bar (prev/play/next/BYPASS + scrubber) ]
    [ Status bar: license + footer + CPU/RAM ]

Operational actions (Add Files / Add Folder / Output / Start / Stop /
File Information / Export Settings) live behind the **Config** button in
the Setting Console and the queue's right-click context menu, so the
main surface stays focused on mixing.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __app_name__, __version__
from .dialogs import (
    AIDetectorDialog,
    ConfigDialog,
    ExportSettings,
    ExportSettingsDialog,
    FileInformationDialog,
)
from .dialogs.file_info_dialog import FileInformationState
from .mastering import MasteringSettings
from .metadata import format_duration
from .templates import TemplateStore
from .widgets import MasteringPanel, SystemStatsWidget, TransportBar, WaveformView
from .widgets.worker import BatchWorker, build_items, schedule_probe, start_worker

SUPPORTED_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac"}
_NEW_TEMPLATE_PLACEHOLDER = "Default"


@dataclasses.dataclass
class QueueRow:
    path: str
    duration_seconds: float
    status: str = "Pending"

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    @property
    def file_type(self) -> str:
        return os.path.splitext(self.path)[1].lstrip(".").upper() or "FILE"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(__app_name__)
        self.resize(1240, 820)
        self.setWindowIcon(self._make_icon())

        self._rows: list[QueueRow] = []
        self._info_state = FileInformationState()
        self._export_settings = ExportSettings()
        self._output_dir: str = str(Path.home() / "PanhaExports")
        self._export_settings.output_dir = self._output_dir
        self._worker: BatchWorker | None = None
        self._thread: QThread | None = None
        self._templates = TemplateStore()
        self._current_template_name: str = ""
        self._config_dialog: ConfigDialog | None = None
        self._ai_dialog: AIDetectorDialog | None = None

        self._build_ui()
        self._refresh_template_combo()
        self._update_buttons()

    # -- icon -----------------------------------------------------------

    def _make_icon(self) -> QIcon:
        # Render a "musical-note like" glyph so we don't ship a binary asset.
        pm = QPixmap(64, 64)
        pm.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#5fa8ff"))
        f = QFont()
        f.setBold(True)
        f.setPointSize(36)
        painter.setFont(f)
        painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "\u266B")
        painter.end()
        return QIcon(pm)

    # -- ui -------------------------------------------------------------

    def _section_frame(self, title: str | None = None) -> tuple[QWidget, QVBoxLayout]:
        frame = QWidget()
        frame.setObjectName("sectionFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 14)
        layout.setSpacing(8)
        if title:
            label = QLabel(title)
            label.setObjectName("sectionTitle")
            layout.addWidget(label)
        return frame, layout

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addLayout(self._build_header())
        root.addWidget(self._build_queue_section(), 1)
        root.addWidget(self._build_setting_console())
        root.addWidget(self._build_waveform_section())
        root.addWidget(self._build_transport_section())

        self._build_status_bar()

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(8)
        logo = QLabel("\u266B")
        logo.setStyleSheet("color:#5fa8ff;font-size:22px;font-weight:700;")
        title = QLabel(__app_name__)
        title.setStyleSheet(
            "color:#c8d2e0;font-size:16px;font-weight:600;letter-spacing:1px;"
        )
        header.addWidget(logo)
        header.addWidget(title)
        header.addStretch(1)
        return header

    def _build_queue_section(self) -> QWidget:
        queue_frame, queue_layout = self._section_frame("Batch Queue")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Filename", "Duration", "Type", "Status"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.currentCellChanged.connect(self._on_current_row_changed)
        queue_layout.addWidget(self.table, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        queue_layout.addWidget(self.progress)
        return queue_frame

    def _build_setting_console(self) -> QWidget:
        frame, layout = self._section_frame("Setting Console")

        # Template row -------------------------------------------------
        tpl_row = QHBoxLayout()
        tpl_row.setSpacing(8)
        tpl_row.addWidget(QLabel("Template:"))

        self.cmb_template = QComboBox()
        self.cmb_template.setEditable(False)
        self.cmb_template.setObjectName("templateCombo")
        self.cmb_template.currentIndexChanged.connect(self._on_template_changed)
        tpl_row.addWidget(self.cmb_template, 1)

        self.btn_save_as = QPushButton("Save As")
        self.btn_save_as.clicked.connect(self._on_template_save_as)
        self.btn_update = QPushButton("Update")
        self.btn_update.clicked.connect(self._on_template_update)
        self.btn_remove_template = QPushButton("Remove")
        self.btn_remove_template.clicked.connect(self._on_template_remove)
        self.btn_reset_all = QPushButton("Reset all")
        self.btn_reset_all.clicked.connect(self._on_reset_all)
        self.btn_config = QPushButton("Config")
        self.btn_config.clicked.connect(self._on_open_config)
        self.btn_analyze_ai = QPushButton("\u270D Analyze AI")
        self.btn_analyze_ai.setObjectName("accentButton")
        self.btn_analyze_ai.clicked.connect(self._on_analyze_ai)

        for btn in (
            self.btn_save_as,
            self.btn_update,
            self.btn_remove_template,
            self.btn_reset_all,
            self.btn_config,
            self.btn_analyze_ai,
        ):
            tpl_row.addWidget(btn)

        layout.addLayout(tpl_row)

        # Slider grid --------------------------------------------------
        self.mastering_panel = MasteringPanel()
        self.mastering_panel.changed.connect(self._on_mastering_changed)
        layout.addWidget(self.mastering_panel)

        return frame

    def _build_waveform_section(self) -> QWidget:
        wave_frame = QFrame()
        wave_frame.setObjectName("sectionFrame")
        wave_layout = QVBoxLayout(wave_frame)
        wave_layout.setContentsMargins(14, 8, 14, 8)
        self.waveform = WaveformView()
        wave_layout.addWidget(self.waveform)
        return wave_frame

    def _build_transport_section(self) -> QWidget:
        host = QFrame()
        host.setObjectName("sectionFrame")
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(8, 4, 8, 4)
        self.transport = TransportBar()
        self.transport.prev_requested.connect(self._on_transport_prev)
        self.transport.next_requested.connect(self._on_transport_next)
        self.transport.bypass_changed.connect(self._on_transport_bypass)
        host_layout.addWidget(self.transport)
        return host

    def _build_status_bar(self) -> None:
        status = QStatusBar()
        self.setStatusBar(status)
        self.status_active = QLabel("Status: Active")
        self.status_active.setObjectName("statusActive")
        status.addWidget(self.status_active)
        status.addPermanentWidget(
            QLabel(f"\u00A9 {self._year()} Panha \u2022 v{__version__}")
        )
        self.system_stats = SystemStatsWidget()
        status.addPermanentWidget(self.system_stats)

    # -- helpers --------------------------------------------------------

    def _year(self) -> int:
        return datetime.now().year

    def _update_buttons(self) -> None:
        running = self._worker is not None
        has_rows = bool(self._rows)
        has_template = self._current_template_name != ""
        self.btn_update.setEnabled(has_template and not running)
        self.btn_remove_template.setEnabled(has_template and not running)
        self.btn_save_as.setEnabled(not running)
        self.btn_reset_all.setEnabled(not running)
        self.btn_config.setEnabled(True)
        self.btn_analyze_ai.setEnabled(has_rows and not running)
        if self._config_dialog is not None:
            self._config_dialog.set_export_running(running)

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self._rows))
        for row_idx, row in enumerate(self._rows):
            for col, value in enumerate((
                row.filename,
                format_duration(row.duration_seconds),
                row.file_type,
                row.status,
            )):
                item = QTableWidgetItem(value)
                if col == 3:
                    if row.status == "Done":
                        item.setForeground(Qt.GlobalColor.green)
                    elif row.status.startswith("Error"):
                        item.setForeground(Qt.GlobalColor.red)
                    elif row.status == "Processing":
                        item.setForeground(Qt.GlobalColor.cyan)
                self.table.setItem(row_idx, col, item)
        self._update_buttons()

    def _update_row_status(
        self, idx: int, status: str, *, tooltip: str = ""
    ) -> None:
        if 0 <= idx < len(self._rows):
            self._rows[idx].status = status
            item = QTableWidgetItem(status)
            if status == "Done":
                item.setForeground(Qt.GlobalColor.green)
            elif status.startswith("Error"):
                item.setForeground(Qt.GlobalColor.red)
            elif status == "Processing":
                item.setForeground(Qt.GlobalColor.cyan)
            if tooltip:
                item.setToolTip(tooltip)
            self.table.setItem(idx, 3, item)

    def _add_paths(self, paths: list[str]) -> None:
        existing = {row.path for row in self._rows}
        added: list[str] = []
        for raw in paths:
            path = os.path.abspath(raw)
            if path in existing:
                continue
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext not in SUPPORTED_EXTS:
                continue
            # Probing duration is a synchronous ffprobe call; defer it to
            # the global thread pool so adding a folder of hundreds of
            # files doesn't freeze the UI.
            self._rows.append(QueueRow(path=path, duration_seconds=0.0))
            existing.add(path)
            added.append(path)
        if added:
            self._refresh_table()
            if self.table.currentRow() < 0 and self._rows:
                self.table.setCurrentCell(0, 0)
            for path in added:
                schedule_probe(path, self._on_probe_finished)

    def _on_probe_finished(self, path: str, duration: float) -> None:
        for idx, row in enumerate(self._rows):
            if row.path == path:
                row.duration_seconds = duration
                item = QTableWidgetItem(format_duration(duration))
                self.table.setItem(idx, 1, item)
                break

    # -- template combo -------------------------------------------------

    def _refresh_template_combo(self) -> None:
        names = self._templates.names()
        self.cmb_template.blockSignals(True)
        self.cmb_template.clear()
        self.cmb_template.addItem(_NEW_TEMPLATE_PLACEHOLDER)
        for name in names:
            self.cmb_template.addItem(name)
        if self._current_template_name:
            idx = self.cmb_template.findText(self._current_template_name)
            self.cmb_template.setCurrentIndex(max(0, idx))
        else:
            self.cmb_template.setCurrentIndex(0)
        self.cmb_template.blockSignals(False)
        self._update_buttons()

    def _apply_state(self, state: FileInformationState) -> None:
        self._info_state = state
        self.mastering_panel.blockSignals(True)
        self.mastering_panel.set_settings(state.mastering)
        self.mastering_panel.blockSignals(False)
        self.transport.set_bypass(state.mastering.bypass)

    # -- slots: template row -------------------------------------------

    def _on_template_changed(self, index: int) -> None:
        if index <= 0:
            self._current_template_name = ""
            self._update_buttons()
            return
        name = self.cmb_template.itemText(index)
        payload = self._templates.get(name)
        if payload is None:
            return
        self._apply_state(FileInformationState.from_dict(payload))
        self._current_template_name = name
        self._update_buttons()

    def _on_template_save_as(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Template", "Template name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        try:
            self._templates.upsert(name, self._info_state.to_dict())
        except OSError as exc:
            QMessageBox.warning(self, "Templates", f"Failed to save: {exc}")
            return
        self._current_template_name = name
        self._refresh_template_combo()

    def _on_template_update(self) -> None:
        if not self._current_template_name:
            return
        try:
            self._templates.upsert(
                self._current_template_name, self._info_state.to_dict()
            )
        except OSError as exc:
            QMessageBox.warning(self, "Templates", f"Failed to save: {exc}")
            return
        QMessageBox.information(
            self, "Templates",
            f"Template '{self._current_template_name}' updated.",
        )

    def _on_template_remove(self) -> None:
        if not self._current_template_name:
            return
        reply = QMessageBox.question(
            self, "Delete Template",
            f"Delete template '{self._current_template_name}'?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._templates.delete(self._current_template_name)
        except OSError as exc:
            QMessageBox.warning(self, "Templates", f"Failed to delete: {exc}")
            return
        self._current_template_name = ""
        self._refresh_template_combo()

    def _on_reset_all(self) -> None:
        self._apply_state(FileInformationState())
        self._current_template_name = ""
        self.cmb_template.setCurrentIndex(0)
        self._update_buttons()

    def _on_open_config(self) -> None:
        if self._config_dialog is None:
            dlg = ConfigDialog(self)
            dlg.add_files_requested.connect(self._on_add_files)
            dlg.add_folder_requested.connect(self._on_add_folder)
            dlg.output_folder_requested.connect(self._on_pick_output)
            dlg.file_information_requested.connect(self._on_open_info_dialog)
            dlg.export_settings_requested.connect(self._on_open_export_dialog)
            dlg.start_export_requested.connect(self._on_start_export)
            dlg.stop_export_requested.connect(self._on_stop_export)
            self._config_dialog = dlg
        self._config_dialog.set_export_running(self._worker is not None)
        self._config_dialog.show()
        self._config_dialog.raise_()
        self._config_dialog.activateWindow()

    def _on_analyze_ai(self) -> None:
        if self._ai_dialog is None:
            self._ai_dialog = AIDetectorDialog(self)
        # Seed the dialog with the queue's current files so the user
        # doesn't have to re-pick them.
        self._ai_dialog.add_paths([row.path for row in self._rows])
        self._ai_dialog.show()
        self._ai_dialog.raise_()
        self._ai_dialog.activateWindow()

    # -- slots: mastering / transport ----------------------------------

    def _on_mastering_changed(self, settings: MasteringSettings) -> None:
        self._info_state.mastering = settings

    def _on_transport_bypass(self, bypass: bool) -> None:
        self._info_state.mastering.bypass = bool(bypass)
        self.mastering_panel.set_bypass(bypass)

    def _on_transport_prev(self) -> None:
        row = self.table.currentRow()
        if row > 0:
            self.table.setCurrentCell(row - 1, 0)

    def _on_transport_next(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._rows) - 1:
            self.table.setCurrentCell(row + 1, 0)

    def _on_current_row_changed(
        self, row: int, _col: int, _prev_row: int, _prev_col: int
    ) -> None:
        if 0 <= row < len(self._rows):
            self.transport.load_source(self._rows[row].path)
        else:
            self.transport.load_source(None)

    # -- slots: batch actions ------------------------------------------

    def _on_add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add audio files",
            str(Path.home()),
            "Audio (*.mp3 *.wav *.flac *.m4a *.ogg *.aac)",
        )
        if files:
            self._add_paths(files)

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Add folder", str(Path.home())
        )
        if not folder:
            return
        candidates: list[str] = []
        for root_dir, _dirs, files in os.walk(folder):
            for name in files:
                if os.path.splitext(name)[1].lower() in SUPPORTED_EXTS:
                    candidates.append(os.path.join(root_dir, name))
        candidates.sort()
        self._add_paths(candidates)

    def _on_remove_selected(self) -> None:
        if self._worker is not None:
            QMessageBox.information(
                self, "Export in progress",
                "Stop the current export before removing rows.",
            )
            return
        rows = sorted(
            {idx.row() for idx in self.table.selectedIndexes()}, reverse=True
        )
        for r in rows:
            if 0 <= r < len(self._rows):
                del self._rows[r]
        self._refresh_table()

    def _on_clear(self) -> None:
        if self._worker is not None:
            QMessageBox.information(
                self, "Export in progress",
                "Stop the current export before clearing the queue.",
            )
            return
        self._rows.clear()
        self._refresh_table()
        self.progress.setValue(0)
        self.transport.load_source(None)

    def _on_open_info_dialog(self) -> None:
        dlg = FileInformationDialog(self._info_state, parent=self)
        if dlg.exec() == FileInformationDialog.DialogCode.Accepted:
            new_state = dlg.collect_state()
            # The dialog now round-trips mastering via the state it was
            # constructed with, but we re-apply the live slider panel
            # state defensively in case the user moved sliders before
            # opening the dialog and the panel is the source of truth.
            new_state.mastering = self.mastering_panel.settings()
            self._apply_state(new_state)

    def _on_open_export_dialog(self) -> None:
        dlg = ExportSettingsDialog(self._export_settings, parent=self)
        if dlg.exec() == ExportSettingsDialog.DialogCode.Accepted:
            self._export_settings = dlg.collect()

    def _on_pick_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose output folder",
            self._output_dir or str(Path.home()),
        )
        if folder:
            self._output_dir = folder
            self._export_settings.output_dir = folder

    def _on_open_output(self) -> None:
        out = Path(self._output_dir)
        out.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(out)])
            elif sys.platform.startswith("win"):
                os.startfile(str(out))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(out)])
        except (OSError, subprocess.SubprocessError):
            QMessageBox.information(self, "Output Folder", str(out))

    def _on_start_export(self) -> None:
        if not self._rows:
            QMessageBox.information(
                self, "Nothing to export", "Add some files first."
            )
            return
        if not self._info_state.enabled:
            reply = QMessageBox.question(
                self,
                "Info Injection disabled",
                "Info Injection is currently disabled in File Information.\n"
                "Continue without writing metadata?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        sources = [row.path for row in self._rows]
        items = build_items(
            sources,
            self._output_dir,
            self._info_state,
            export=self._export_settings,
        )
        for idx in range(len(self._rows)):
            self._update_row_status(idx, "Pending")
        self.progress.setValue(0)
        worker, thread = start_worker(
            items, max_threads=self._export_settings.max_threads
        )
        worker.progress.connect(self._on_progress)
        worker.item_done.connect(self._on_item_done)
        worker.item_failed.connect(self._on_item_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self._thread = thread
        self.waveform.setActive(True)
        self._update_buttons()

    def _on_stop_export(self) -> None:
        if self._worker:
            self._worker.cancel()

    def _on_progress(self, done: int, total: int) -> None:
        pct = int(done * 100 / max(total, 1))
        self.progress.setValue(pct)

    def _on_item_done(self, idx: int, status: str) -> None:
        self._update_row_status(idx, status)

    def _on_item_failed(self, idx: int, message: str) -> None:
        # Truncate the inline status so it fits the column, but keep the
        # full ffmpeg error on the cell tooltip so users can diagnose.
        truncated = message if len(message) <= 60 else f"{message[:60]}\u2026"
        self._update_row_status(
            idx, f"Error: {truncated}", tooltip=message
        )

    def _on_worker_finished(self) -> None:
        self._worker = None
        self._thread = None
        self.waveform.setActive(False)
        self.progress.setValue(100)
        self._update_buttons()

    # -- context menu --------------------------------------------------

    def _on_context_menu(self, pos) -> None:
        menu = QMenu(self)
        act_select_all = QAction("Select all", self)
        act_select_all.triggered.connect(self.table.selectAll)
        act_add_files = QAction("Add files", self)
        act_add_files.triggered.connect(self._on_add_files)
        act_add_folder = QAction("Add folder", self)
        act_add_folder.triggered.connect(self._on_add_folder)
        act_remove = QAction("Remove selected", self)
        act_remove.triggered.connect(self._on_remove_selected)
        act_clear = QAction("Clear all", self)
        act_clear.triggered.connect(self._on_clear)
        act_start = QAction("\u25B6  START EXPORT", self)
        act_start.triggered.connect(self._on_start_export)
        act_stop = QAction("\u25A0  STOP EXPORT", self)
        act_stop.triggered.connect(self._on_stop_export)
        act_open = QAction("Open output", self)
        act_open.triggered.connect(self._on_open_output)
        menu.addAction(act_select_all)
        menu.addAction(act_add_files)
        menu.addAction(act_add_folder)
        menu.addSeparator()
        menu.addAction(act_remove)
        menu.addAction(act_clear)
        menu.addSeparator()
        menu.addAction(act_start)
        menu.addAction(act_stop)
        menu.addSeparator()
        menu.addAction(act_open)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker:
            self._worker.cancel()
        # write_metadata polls cancel_check every 100ms and grants the
        # ffmpeg child up to 2s to exit gracefully (then kill -9), so
        # 6s is a comfortable upper bound for a clean shutdown. We fall
        # back to QThread.terminate() if the worker is wedged so the app
        # doesn't hang on close.
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            if not self._thread.wait(6000):
                self._thread.terminate()
                self._thread.wait(1000)
        self.transport.stop()
        self.system_stats.stop()
        if self._ai_dialog is not None:
            self._ai_dialog.close()
        if self._config_dialog is not None:
            self._config_dialog.close()
        super().closeEvent(event)
