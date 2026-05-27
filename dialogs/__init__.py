"""Modal dialogs used by the main window."""

from .ai_detector_dialog import AIDetectorDialog
from .config_dialog import ConfigDialog
from .export_settings_dialog import ExportSettings, ExportSettingsDialog
from .file_info_dialog import FileInformationDialog

__all__ = [
    "AIDetectorDialog",
    "ConfigDialog",
    "ExportSettings",
    "ExportSettingsDialog",
    "FileInformationDialog",
]
