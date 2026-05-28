"""Persistent application config backed by ``panha/metadata.json``.

All user-editable state lives in one file so the app restores exactly
where the user left off after a restart:

* ``last_state``    — serialised :class:`~panha.dialogs.file_info_dialog.FileInformationState`
* ``last_template`` — name of the currently-selected mastering template
* ``templates``     — user-created template payloads (keyed by name)

The "SUNO Bypass" export option reads ``last_state`` at export time so
the metadata applied to every output file comes from this JSON file
rather than from a separate in-memory copy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Location of the config file: same directory as this module.
CONFIG_PATH: Path = Path(__file__).with_name("metadata.json")


# ---------------------------------------------------------------------------
# Low-level document helpers
# ---------------------------------------------------------------------------

def _default_doc() -> dict[str, Any]:
    return {
        "templates": {},
        "last_template": "",
        "last_state": {
            "enable": True,
            "artist": "",
            "album": "",
            "year": "2026",
            "genre": "",
            "rating": "None",
            "rating_min": 3,
            "rating_max": 5,
            "cover_path": "",
            "engineer": "",
            "copyright": "",
            "software": "",
            "source": "",
            "comment": "",
            "upper": False,
            "remove_track_number": True,
            "cover_w": 1600,
            "cover_h": 1600,
            "mastering": {},
        },
    }


def _read_doc(path: Path) -> dict[str, Any]:
    """Load the JSON document, returning a fresh default on any error."""
    if not path.exists():
        return _default_doc()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_doc()
    return data if isinstance(data, dict) else _default_doc()


def _write_doc(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# State <-> flat-dict conversion (matches the panha/metadata.json schema)
# ---------------------------------------------------------------------------

def state_to_flat(state: Any) -> dict[str, Any]:
    """Encode a :class:`FileInformationState` into the flat ``last_state`` dict."""
    import dataclasses
    mastering_dict: dict[str, Any] = {}
    if state.mastering is not None:
        mastering_dict = dataclasses.asdict(state.mastering)
    return {
        "enable": state.enabled,
        "artist": state.metadata.artist,
        "album": state.metadata.album,
        "year": state.metadata.year,
        "genre": state.metadata.genre,
        "rating": state.metadata.rating or "None",
        "rating_min": 3,
        "rating_max": 5,
        "cover_path": state.metadata.cover_path,
        "engineer": state.metadata.engineer,
        "copyright": state.metadata.copyright,
        "software": state.metadata.software,
        "source": state.metadata.source,
        "comment": state.metadata.comment,
        "upper": state.tracklist.uppercase,
        "remove_track_number": state.tracklist.remove_track_number,
        "cover_w": state.tracklist.cover_size,
        "cover_h": state.tracklist.cover_height,
        "mastering": mastering_dict,
    }


def state_from_flat(raw: dict[str, Any]) -> Any:
    """Decode a flat ``last_state`` dict into a :class:`FileInformationState`.

    Supports both the flat legacy schema and the nested
    ``FileInformationState.to_dict()`` format so hand-edited files
    and old exports keep loading correctly.
    """
    from .dialogs.file_info_dialog import FileInformationState, TracklistOptions
    from .mastering import MasteringSettings
    from .metadata import Metadata

    # --- nested (FileInformationState.to_dict) format ---
    if "metadata" in raw or "tracklist" in raw:
        return FileInformationState.from_dict(raw)

    # --- flat format (the schema in panha/metadata.json) ---
    rating = raw.get("rating", "")
    if rating == "None":
        rating = ""

    meta = Metadata(
        artist=str(raw.get("artist", "")),
        album=str(raw.get("album", "")),
        year=str(raw.get("year", "")),
        genre=str(raw.get("genre", "")),
        rating=rating,
        cover_path=str(raw.get("cover_path", "")),
        engineer=str(raw.get("engineer", "")),
        copyright=str(raw.get("copyright", "")),
        software=str(raw.get("software", "")),
        source=str(raw.get("source", "")),
        comment=str(raw.get("comment", "")),
    )
    tracklist = TracklistOptions(
        uppercase=bool(raw.get("upper", False)),
        remove_track_number=bool(raw.get("remove_track_number", True)),
        cover_size=int(raw.get("cover_w", 1600)),
        cover_height=int(raw.get("cover_h", 1600)),
    )
    mastering_raw = raw.get("mastering") or {}
    if mastering_raw:
        # Guard against hand-edited JSON containing unknown keys: only pass
        # field names that MasteringSettings actually declares so we never
        # raise TypeError and silently discard the user's entire state.
        import dataclasses as _dc
        _valid = {f.name for f in _dc.fields(MasteringSettings)}
        mastering_raw = {k: v for k, v in mastering_raw.items() if k in _valid}
    mastering = MasteringSettings(**mastering_raw) if mastering_raw else MasteringSettings()
    return FileInformationState(
        enabled=bool(raw.get("enable", True)),
        metadata=meta,
        tracklist=tracklist,
        mastering=mastering,
    )


# ---------------------------------------------------------------------------
# ConfigStore — the public API used by MainWindow and build_items
# ---------------------------------------------------------------------------

class ConfigStore:
    """Read/write helper for ``panha/metadata.json``.

    All writes are atomic: the existing document is loaded first so
    unrelated keys (e.g. ``rating_min`` / ``rating_max``) are never
    accidentally removed.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else CONFIG_PATH

    # -- last_state --------------------------------------------------------

    def load_last_state(self) -> Any:
        """Return the persisted :class:`FileInformationState`, or a default."""
        doc = _read_doc(self.path)
        raw = doc.get("last_state")
        if isinstance(raw, dict) and raw:
            try:
                return state_from_flat(raw)
            except Exception:
                pass
        from .dialogs.file_info_dialog import FileInformationState
        return FileInformationState()

    def save_last_state(self, state: Any) -> None:
        """Persist ``state`` into the ``last_state`` key of the document."""
        doc = _read_doc(self.path)
        doc["last_state"] = state_to_flat(state)
        _write_doc(self.path, doc)

    # -- last_template -----------------------------------------------------

    def load_last_template(self) -> str:
        doc = _read_doc(self.path)
        return str(doc.get("last_template", ""))

    def save_last_template(self, name: str) -> None:
        doc = _read_doc(self.path)
        doc["last_template"] = str(name or "")
        _write_doc(self.path, doc)

    # -- templates ---------------------------------------------------------

    def load_templates(self) -> dict[str, dict]:
        doc = _read_doc(self.path)
        templates = doc.get("templates")
        return dict(templates) if isinstance(templates, dict) else {}

    def save_templates(self, templates: dict[str, dict]) -> None:
        doc = _read_doc(self.path)
        doc["templates"] = dict(templates)
        _write_doc(self.path, doc)
