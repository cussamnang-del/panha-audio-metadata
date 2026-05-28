"""Factory mastering presets bundled with the app.

The presets live in :data:`PRESETS_PATH` (``panha/presets.json``) as a
plain JSON dictionary of named slider values, originally authored for a
sister mixer that used different attribute names and a slightly wider
value range. This module owns three pieces of glue so the same JSON
file can drop straight into the Template Preset selector:

1. :data:`_PRESET_KEY_TO_ATTR` — maps the JSON keys (``vocal_clear``,
   ``compress``, ``reverb``, ...) onto the canonical
   :class:`~panha.mastering.MasteringSettings` attribute names
   (``clear``, ``comp``, ``verb``, ...).
2. :func:`_scale_value` — rescales each value into the
   ``[SLIDER_MIN, SLIDER_MAX]`` (0..99) integer range that the slider
   grid renders.
3. :func:`load_factory_presets` — returns each preset as a
   :class:`~panha.dialogs.file_info_dialog.FileInformationState` so the
   existing Template-combo plumbing can serve it without special casing.

Factory presets are read-only: they show up in the Template combo but
the Remove / Delete buttons silently refuse to wipe them (see
:meth:`~panha.templates.TemplateStore.delete`).
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from .mastering import SLIDER_MAX, SLIDER_MIN, MasteringSettings

# Resolved at import time so callers can override (e.g. for tests) by
# assigning to ``panha.presets.PRESETS_PATH`` before invoking the loader.
PRESETS_PATH: Path = Path(__file__).with_name("presets.json")

# Translation table from the JSON's slider keys to the canonical
# MasteringSettings attributes. Keys not in this dict are silently
# ignored so future preset files can add experimental fields without
# breaking the loader.
_PRESET_KEY_TO_ATTR: dict[str, str] = {
    "gain": "gain",
    "bass": "bass",
    "vocal_deep": "deep",
    "deep": "deep",
    "mid": "mid",
    "vocal_clear": "clear",
    "clear": "clear",
    "treble": "treble",
    "presence": "pres",
    "pres": "pres",
    "compress": "comp",
    "comp": "comp",
    "limit": "limit",
    "saturate": "sat",
    "sat": "sat",
    "reverb": "verb",
    "verb": "verb",
    "echo": "echo",
    "stereo": "width",
    "width": "width",
}

# EQ-style sliders are authored on a dB-like scale (-12 .. +12) in the
# JSON, while the slider grid stores 0..99 (boost-only). Multiplying by
# ``_DB_TO_SLIDER`` and clamping negatives to 0 maps the +0..+12 dB
# half of the JSON range onto the full slider travel.
_EQ_LIKE_ATTRS: frozenset[str] = frozenset({
    "bass", "deep", "mid", "clear", "treble", "pres", "gain",
})
_DB_TO_SLIDER: float = SLIDER_MAX / 12.0


def _scale_value(attr: str, raw: Any) -> int:
    """Convert a raw preset value into the slider's 0..99 integer range.

    ``raw`` may be ``int`` or ``float``; anything else is treated as 0.
    Negative inputs are clamped to 0 since the current mastering chain
    is boost-only.
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return SLIDER_MIN
    if value < 0:
        value = 0.0
    if attr in _EQ_LIKE_ATTRS:
        scaled = int(round(value * _DB_TO_SLIDER))
    else:
        scaled = int(round(value))
    return max(SLIDER_MIN, min(SLIDER_MAX, scaled))


def _preset_payload_to_mastering(payload: dict[str, Any]) -> MasteringSettings:
    """Turn one JSON entry into a :class:`MasteringSettings`."""
    settings = MasteringSettings()
    for key, raw in payload.items():
        attr = _PRESET_KEY_TO_ATTR.get(str(key).lower())
        if attr is None:
            continue
        setattr(settings, attr, _scale_value(attr, raw))
    return settings


def _read_presets_file(path: Path | None = None) -> dict[str, Any]:
    """Best-effort read of the presets JSON. Returns ``{}`` on failure.

    Tries the explicit ``path`` first, then falls back to the
    package-data file via :mod:`importlib.resources` so editable installs
    *and* wheel installs both work.
    """
    candidate = path or PRESETS_PATH
    try:
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    # Wheel-install fallback — the file lives inside the importable
    # ``panha`` package, so ask importlib for it.
    try:
        with resources.files("panha").joinpath("presets.json").open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, ModuleNotFoundError, OSError, json.JSONDecodeError):
        return {}


def load_factory_presets(path: Path | None = None) -> dict[str, dict]:
    """Return ``{name: payload}`` where each payload is a serialised
    :class:`~panha.dialogs.file_info_dialog.FileInformationState`.

    The serialised shape matches what the Template combo already
    consumes (``FileInformationState.to_dict()``) — metadata and
    tracklist stay at their defaults so applying a factory preset
    only touches the mastering chain.
    """
    # Import here to avoid a circular import at module load:
    # file_info_dialog imports MasteringSettings from .mastering, and we
    # don't want presets.py to be on its critical path.
    from .dialogs.file_info_dialog import FileInformationState

    raw = _read_presets_file(path)
    if not isinstance(raw, dict):
        return {}
    presets = raw.get("presets")
    if not isinstance(presets, dict):
        return {}

    out: dict[str, dict] = {}
    for name, payload in presets.items():
        if not isinstance(name, str) or not isinstance(payload, dict):
            continue
        mastering = _preset_payload_to_mastering(payload)
        state = FileInformationState(mastering=mastering)
        out[name] = state.to_dict()
    return out


def factory_preset_names(path: Path | None = None) -> list[str]:
    """Sorted list of factory preset names."""
    return sorted(load_factory_presets(path).keys())


def is_factory_preset(name: str, path: Path | None = None) -> bool:
    """True when ``name`` matches a bundled preset (case-sensitive)."""
    return name in load_factory_presets(path)


def get_factory_preset(name: str, path: Path | None = None) -> dict | None:
    """Return the serialised state for a factory preset, or ``None``."""
    return load_factory_presets(path).get(name)
