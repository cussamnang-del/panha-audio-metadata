"""Persistence for batch templates.

Templates are stored as a JSON object keyed by name in
``~/.panha_templates.json``. The value for each name is the serialised
:class:`~panha.dialogs.file_info_dialog.FileInformationState`.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_TEMPLATES_PATH = Path.home() / ".panha_templates.json"


class TemplateStore:
    """Thin read/write wrapper around the templates JSON file."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_TEMPLATES_PATH

    def load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, templates: dict[str, dict]) -> None:
        self.path.write_text(
            json.dumps(templates, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def names(self) -> list[str]:
        return sorted(self.load().keys())

    def get(self, name: str) -> dict | None:
        return self.load().get(name)

    def upsert(self, name: str, payload: dict) -> None:
        templates = self.load()
        templates[name] = payload
        self.save(templates)

    def delete(self, name: str) -> bool:
        templates = self.load()
        if name not in templates:
            return False
        del templates[name]
        self.save(templates)
        return True
