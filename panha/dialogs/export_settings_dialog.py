"""Export settings dialog (format, sample rate, bit depth, threads)."""

from __future__ import annotations

import dataclasses

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

PRESERVE_SOURCE_FORMAT = "Same as source"
FORMATS = [PRESERVE_SOURCE_FORMAT, "MP3", "WAV", "FLAC", "M4A", "OGG"]
PRESERVE_SOURCE_SAMPLE_RATE = "Same as source"
SAMPLE_RATES = [
    PRESERVE_SOURCE_SAMPLE_RATE,
    "22050 Hz",
    "44100 Hz",
    "48000 Hz",
    "96000 Hz",
]
BIT_DEPTHS = ["16-bit", "24-bit", "32-bit"]
LUFS_TARGETS = ["Off", "-23 LUFS", "-16 LUFS", "-14 LUFS", "-9 LUFS"]

_FORMAT_SUFFIXES = {
    "MP3": ".mp3",
    "WAV": ".wav",
    "FLAC": ".flac",
    "M4A": ".m4a",
    "OGG": ".ogg",
}

_WAV_BIT_DEPTH_CODECS = {
    "16-bit": ["-c:a", "pcm_s16le"],
    "24-bit": ["-c:a", "pcm_s24le"],
    "32-bit": ["-c:a", "pcm_s32le"],
}


@dataclasses.dataclass
class ExportSettings:
    format: str = PRESERVE_SOURCE_FORMAT
    sample_rate: str = PRESERVE_SOURCE_SAMPLE_RATE
    bit_depth: str = "24-bit"
    max_threads: int = 4
    suno_bypass: bool = False
    vocal_clarity: bool = False
    soft_clip: bool = False
    lufs_target: str = "Off"
    output_dir: str = ""

    # -- Parsing helpers consumed by build_items / write_metadata. --
    # Keeping them on the dataclass means the UI strings stay in one
    # place and tests can exercise the same translation the writer uses.

    def output_suffix_for(self, source_suffix: str) -> str:
        """Suffix to use for the output file, preserving source when asked."""
        if self.format == PRESERVE_SOURCE_FORMAT:
            return source_suffix or ".mp3"
        return _FORMAT_SUFFIXES.get(self.format.upper(), source_suffix or ".mp3")

    def parsed_sample_rate_hz(self) -> int | None:
        """Integer Hz value, or None to leave the source rate untouched."""
        if self.sample_rate == PRESERVE_SOURCE_SAMPLE_RATE:
            return None
        try:
            return int(self.sample_rate.split()[0])
        except (ValueError, IndexError):
            return None

    def parsed_lufs_target(self) -> float | None:
        """LUFS integration target for ``loudnorm``; None when 'Off'."""
        if not self.lufs_target or self.lufs_target == "Off":
            return None
        try:
            return float(self.lufs_target.split()[0])
        except (ValueError, IndexError):
            return None

    def codec_args_override(self) -> list[str] | None:
        """Explicit ``-c:a ...`` args for the chosen format.

        Only WAV has a user-selectable codec (the bit depth); for every
        other format we let :func:`panha.mastering.codec_args_for` pick
        the default codec from the output suffix.
        """
        if self.format.upper() == "WAV":
            return list(_WAV_BIT_DEPTH_CODECS.get(self.bit_depth, ["-c:a", "pcm_s24le"]))
        return None


class ExportSettingsDialog(QDialog):
    """Modal export configuration."""

    def __init__(
        self, settings: ExportSettings | None = None, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setWindowTitle("Export Settings")
        self.setModal(True)
        self.setFixedWidth(360)
        self._settings = settings or ExportSettings()
        self._build_ui()
        self._load(self._settings)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("Export Settings")
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size:15px;")
        root.addWidget(title)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#1c3050;background:#1c3050;max-height:1px;")
        root.addWidget(line)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        self.cmb_format = QComboBox()
        self.cmb_format.addItems(FORMATS)
        self.cmb_format.currentTextChanged.connect(self._on_format_changed)
        self.cmb_sample = QComboBox()
        self.cmb_sample.addItems(SAMPLE_RATES)
        self.cmb_bitdepth = QComboBox()
        self.cmb_bitdepth.addItems(BIT_DEPTHS)
        self.cmb_bitdepth.setToolTip(
            "Bit depth applies to WAV exports only. For other formats the "
            "codec's default sample format is used."
        )
        self.spn_threads = QSpinBox()
        self.spn_threads.setRange(1, 32)
        self.spn_threads.setValue(4)
        form.addRow("Format", self.cmb_format)
        form.addRow("Sample Rate", self.cmb_sample)
        form.addRow("Bit Depth", self.cmb_bitdepth)
        form.addRow("Max Threads", self.spn_threads)
        root.addLayout(form)

        self._add_section_header(root, "Processing Options")
        self.chk_suno = QCheckBox("SUNO Bypass")
        self.chk_vocal = QCheckBox("Vocal Clarity Boost")
        self.chk_softclip = QCheckBox("Soft Clip Ceiling")
        for w in (self.chk_suno, self.chk_vocal, self.chk_softclip):
            root.addWidget(w)

        self._add_section_header(root, "Mastering Target")
        master_layout = QFormLayout()
        master_layout.setHorizontalSpacing(12)
        master_layout.setVerticalSpacing(8)
        self.cmb_lufs = QComboBox()
        self.cmb_lufs.addItems(LUFS_TARGETS)
        master_layout.addRow("LUFS Target", self.cmb_lufs)
        root.addLayout(master_layout)

        root.addSpacing(4)

        self.btn_start = QPushButton("\u25B6  Start Export")
        self.btn_start.setObjectName("primaryButton")
        self.btn_start.clicked.connect(self.accept)
        root.addWidget(self.btn_start)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        root.addWidget(self.btn_cancel)

    def _add_section_header(self, layout: QVBoxLayout, text: str) -> None:
        """Inline section header — small cyan label above a thin divider."""
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        label.setStyleSheet("font-size:11px;color:#5fa8ff;")
        layout.addSpacing(2)
        layout.addWidget(label)
        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setStyleSheet("color:#1c3050;background:#1c3050;max-height:1px;")
        layout.addWidget(rule)

    def _load(self, s: ExportSettings) -> None:
        for combo, value in (
            (self.cmb_format, s.format),
            (self.cmb_sample, s.sample_rate),
            (self.cmb_bitdepth, s.bit_depth),
            (self.cmb_lufs, s.lufs_target),
        ):
            idx = combo.findText(value)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        self.spn_threads.setValue(s.max_threads)
        self.chk_suno.setChecked(s.suno_bypass)
        self.chk_vocal.setChecked(s.vocal_clarity)
        self.chk_softclip.setChecked(s.soft_clip)
        self._on_format_changed(self.cmb_format.currentText())

    def _on_format_changed(self, fmt: str) -> None:
        """Bit depth is meaningful only for WAV; gray it out otherwise."""
        self.cmb_bitdepth.setEnabled(fmt.upper() == "WAV")

    def collect(self) -> ExportSettings:
        return ExportSettings(
            format=self.cmb_format.currentText(),
            sample_rate=self.cmb_sample.currentText(),
            bit_depth=self.cmb_bitdepth.currentText(),
            max_threads=int(self.spn_threads.value()),
            suno_bypass=self.chk_suno.isChecked(),
            vocal_clarity=self.chk_vocal.isChecked(),
            soft_clip=self.chk_softclip.isChecked(),
            lufs_target=self.cmb_lufs.currentText(),
            output_dir=self._settings.output_dir,
        )
