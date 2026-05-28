"""Setting Console mastering panel — the 13-slider grid from X-MIXM."""

from __future__ import annotations

import dataclasses

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..mastering import (
    DYN_NAMES,
    EQ_BANDS,
    FX_NAMES,
    OUT_NAMES,
    SLIDER_MAX,
    SLIDER_MIN,
    MasteringSettings,
)


@dataclasses.dataclass
class _SliderSpec:
    attr: str
    label: str
    category: str  # "EQ", "VOCAL", "DYN", "FX", "OUT"


# Category badge shown above each slider. EQ band ordering matches the
# X-MIXM reference where odd-indexed bands carry the "VOCAL" badge.
SLIDER_SPECS: tuple[_SliderSpec, ...] = (
    _SliderSpec(EQ_BANDS[0][0], EQ_BANDS[0][1], "EQ"),
    _SliderSpec(EQ_BANDS[1][0], EQ_BANDS[1][1], "VOCAL"),
    _SliderSpec(EQ_BANDS[2][0], EQ_BANDS[2][1], "EQ"),
    _SliderSpec(EQ_BANDS[3][0], EQ_BANDS[3][1], "VOCAL"),
    _SliderSpec(EQ_BANDS[4][0], EQ_BANDS[4][1], "EQ"),
    _SliderSpec(EQ_BANDS[5][0], EQ_BANDS[5][1], "EQ"),
    _SliderSpec(DYN_NAMES[0], "Comp", "DYN"),
    _SliderSpec(DYN_NAMES[1], "Limit", "DYN"),
    _SliderSpec(DYN_NAMES[2], "Sat", "DYN"),
    _SliderSpec(FX_NAMES[0], "Verb", "FX"),
    _SliderSpec(FX_NAMES[1], "Echo", "FX"),
    _SliderSpec(OUT_NAMES[0], "Width", "OUT"),
    _SliderSpec(OUT_NAMES[1], "Gain", "OUT"),
)


class _SliderColumn(QFrame):
    """A single vertical strip: category badge, value, slider, label."""

    value_changed = pyqtSignal(str, int)

    def __init__(self, spec: _SliderSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spec = spec
        self.setObjectName("mixerColumn")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.badge = QLabel(spec.category)
        self.badge.setObjectName("mixerBadge")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.readout = QLabel("0")
        self.readout.setObjectName("mixerReadout")
        self.readout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.slider = QSlider(Qt.Orientation.Vertical)
        self.slider.setObjectName("mixerSlider")
        self.slider.setRange(SLIDER_MIN, SLIDER_MAX)
        self.slider.setValue(0)
        self.slider.setMinimumHeight(120)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(5)
        self.slider.valueChanged.connect(self._emit_value_changed)

        self.name = QLabel(spec.label)
        self.name.setObjectName("mixerName")
        self.name.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        layout.addWidget(self.badge)
        layout.addWidget(self.readout)
        layout.addWidget(self.slider, 1, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.name)

    @property
    def attr(self) -> str:
        return self._spec.attr

    def value(self) -> int:
        return int(self.slider.value())

    def set_value(self, value: int) -> None:
        self.slider.setValue(int(value))

    def _emit_value_changed(self, value: int) -> None:
        self.readout.setText(str(value))
        self.value_changed.emit(self._spec.attr, int(value))


class MasteringPanel(QWidget):
    """The horizontal strip of 13 mastering sliders.

    Emits :attr:`changed` with a fresh :class:`MasteringSettings` whenever
    any slider moves or the bypass flag is toggled.
    """

    changed = pyqtSignal(MasteringSettings)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = MasteringSettings()
        self._columns: dict[str, _SliderColumn] = {}

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        grid_host = QFrame()
        grid_host.setObjectName("mixerGrid")
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(0)

        for col, spec in enumerate(SLIDER_SPECS):
            column = _SliderColumn(spec)
            column.value_changed.connect(self._on_column_changed)
            grid.addWidget(column, 0, col)
            self._columns[spec.attr] = column

        outer.addWidget(grid_host, 1)

    # -- public API ----------------------------------------------------

    def settings(self) -> MasteringSettings:
        return dataclasses.replace(self._settings)

    def set_settings(self, settings: MasteringSettings) -> None:
        self._settings = dataclasses.replace(settings)
        for attr, column in self._columns.items():
            column.slider.blockSignals(True)
            column.set_value(getattr(self._settings, attr))
            column.readout.setText(str(getattr(self._settings, attr)))
            column.slider.blockSignals(False)
        self.setEnabled(not self._settings.bypass)
        self.changed.emit(self.settings())

    def set_bypass(self, bypass: bool) -> None:
        if self._settings.bypass == bypass:
            return
        self._settings.bypass = bool(bypass)
        self.setEnabled(not self._settings.bypass)
        self.changed.emit(self.settings())

    # -- private -------------------------------------------------------

    def _on_column_changed(self, attr: str, value: int) -> None:
        setattr(self._settings, attr, int(value))
        self.changed.emit(self.settings())
