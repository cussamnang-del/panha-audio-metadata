"""Dark theme stylesheet inspired by the X-MIXM reference UI."""

DARK_STYLESHEET = """
* {
    color: #c8d2e0;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 12px;
}

QMainWindow, QDialog, QWidget#central {
    background-color: #0d1726;
}

QWidget#sectionFrame {
    background-color: #11203a;
    border: 1px solid #1c3050;
    border-radius: 6px;
}

QLabel#sectionTitle {
    color: #5fa8ff;
    font-weight: 600;
    padding: 2px 4px 6px 4px;
    font-size: 13px;
}

QLabel#fieldLabel {
    color: #8aa0c0;
}

QLabel#footerLabel {
    color: #6c7f9e;
}

QLabel#statusActive {
    color: #4fd6a4;
    font-weight: 600;
}

QLabel#statusExpire {
    color: #5fa8ff;
    font-weight: 600;
}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {
    background-color: #0a1426;
    border: 1px solid #1c3050;
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: #1f5fcf;
}

QLineEdit:disabled, QComboBox:disabled {
    color: #4a5a72;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 1px solid #3f7fe0;
}

QComboBox::drop-down {
    border: none;
    width: 18px;
}
QComboBox::down-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #5fa8ff;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #0a1426;
    border: 1px solid #1c3050;
    selection-background-color: #1f5fcf;
    color: #c8d2e0;
}

QPushButton {
    background-color: transparent;
    border: 1px solid #2a4670;
    border-radius: 4px;
    padding: 6px 14px;
    color: #c8d2e0;
}
QPushButton:hover {
    border-color: #5fa8ff;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #122a4d;
}
QPushButton:disabled {
    color: #4a5a72;
    border-color: #1c3050;
}

QPushButton#accentButton {
    background-color: #6a4cff;
    border-color: #6a4cff;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#accentButton:hover {
    background-color: #7e62ff;
    border-color: #7e62ff;
}

QPushButton#primaryButton {
    background-color: #1f5fcf;
    border-color: #1f5fcf;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#primaryButton:hover {
    background-color: #3a7be0;
    border-color: #3a7be0;
}

QTableWidget, QTableView {
    background-color: #0a1426;
    alternate-background-color: #0d1a32;
    border: none;
    gridline-color: #1c3050;
    selection-background-color: #1f5fcf;
    selection-color: #ffffff;
}
QTableWidget::item, QTableView::item {
    padding: 6px 8px;
    border-bottom: 1px solid #15233f;
}
QHeaderView::section {
    background-color: #0a1426;
    color: #5fa8ff;
    padding: 8px;
    border: none;
    border-bottom: 1px solid #1f3a66;
    font-weight: 600;
}

QProgressBar {
    background-color: #0a1426;
    border: 1px solid #1c3050;
    border-radius: 4px;
    height: 14px;
    text-align: center;
    color: #ffffff;
    font-weight: 600;
}
QProgressBar::chunk {
    background-color: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 0,
        stop: 0 #1f5fcf, stop: 1 #5fa8ff
    );
    border-radius: 3px;
}

QScrollBar:vertical {
    background: #0a1426;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #1f3a66;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #3a7be0;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: #0a1426;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #1f3a66;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: #3a7be0;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

QMenu {
    background-color: #0d1726;
    border: 1px solid #1c3050;
    padding: 4px;
}
QMenu::item {
    padding: 6px 18px;
    border-radius: 3px;
}
QMenu::item:selected {
    background-color: #1f5fcf;
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background: #1c3050;
    margin: 4px 4px;
}

QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #2a4670;
    background-color: #0a1426;
    border-radius: 3px;
}
QCheckBox::indicator:checked {
    background-color: #1f5fcf;
    border-color: #5fa8ff;
}

QGroupBox {
    border: 1px solid #2a4670;
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 10px;
    background-color: #11203a;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: #5fa8ff;
    font-weight: 600;
}

QToolTip {
    background-color: #0a1426;
    color: #c8d2e0;
    border: 1px solid #1f3a66;
    padding: 4px;
}

/* ------------------------------------------------------------------ */
/* AI Music Detector dialog                                            */
/* ------------------------------------------------------------------ */

QLabel#aiDetectorTitle {
    color: #5fa8ff;
    font-size: 18px;
    font-weight: 700;
    padding: 0;
}

QLabel#aiDetectorSubtitle {
    color: #8aa0c0;
    font-size: 12px;
    padding: 0;
}

QFrame#aiDetectorDivider {
    background-color: #1f3a66;
    border: none;
    max-height: 1px;
    min-height: 1px;
}

QPushButton#aiDetectorPrimary {
    background-color: transparent;
    border: 1px solid #5fa8ff;
    border-radius: 4px;
    padding: 7px 18px;
    color: #5fa8ff;
    font-weight: 600;
}
QPushButton#aiDetectorPrimary:hover {
    background-color: rgba(95, 168, 255, 25);
    border-color: #7ec0ff;
    color: #ffffff;
}
QPushButton#aiDetectorPrimary:pressed {
    background-color: rgba(95, 168, 255, 60);
}

QPushButton#aiDetectorSecondary,
QPushButton#aiDetectorClose {
    background-color: transparent;
    border: 1px solid #2a4670;
    border-radius: 4px;
    padding: 7px 18px;
    color: #c8d2e0;
}
QPushButton#aiDetectorSecondary:hover,
QPushButton#aiDetectorClose:hover {
    border-color: #5fa8ff;
    color: #ffffff;
}
QPushButton#aiDetectorSecondary:pressed,
QPushButton#aiDetectorClose:pressed {
    background-color: #122a4d;
}

QTableWidget#aiDetectorTable {
    background-color: #0a1426;
    alternate-background-color: #0d1a32;
    border: none;
}
QTableWidget#aiDetectorTable::item {
    padding: 8px 10px;
    border-bottom: 1px solid #15233f;
}
QTableWidget#aiDetectorTable QHeaderView {
    background-color: #0a1426;
}
QTableWidget#aiDetectorTable QHeaderView::section {
    background-color: #0a1426;
    color: #5fa8ff;
    padding: 10px 10px;
    border: none;
    border-bottom: 1px solid #1f3a66;
    font-weight: 600;
}
QTableWidget#aiDetectorTable QTableCornerButton::section {
    background-color: #0a1426;
    border: none;
}
"""
