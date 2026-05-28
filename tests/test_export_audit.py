"""Audit tests for the full export pipeline.

Verifies:
1.  Mastering chain is ALWAYS taken from the live UI state (not from JSON)
    regardless of whether SUNO Bypass is on or off.
2.  When SUNO Bypass is ON, only the *metadata fields* come from the JSON
    store; mastering and tracklist options still come from the live UI.
3.  force_re_encode is True whenever the mastering chain is active, so
    the filter graph is always invoked.
4.  The SUNO Bypass metadata (artist/album/genre from panha/metadata.json)
    is correctly applied to the BatchItem.
5.  When SUNO Bypass is OFF, the live UI metadata is used unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from panha.dialogs.export_settings_dialog import ExportSettings
from panha.dialogs.file_info_dialog import FileInformationState, TracklistOptions
from panha.mastering import MasteringSettings
from panha.metadata import Metadata
from panha.widgets.worker import build_items


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _store(tmp_path: Path, *, artist: str = "JSON Artist", bass: int = 0):
    """Write a minimal config JSON and return a ConfigStore pointing to it."""
    from panha.config_store import ConfigStore
    store = ConfigStore(tmp_path / "metadata.json")
    from panha.dialogs.file_info_dialog import FileInformationState
    state = FileInformationState(
        metadata=Metadata(artist=artist, album="JSON Album", genre="R&B"),
        mastering=MasteringSettings(bass=bass),  # mastering in JSON (must be ignored)
    )
    store.save_last_state(state)
    return store


def _src(tmp_path: Path, name: str = "song.wav") -> Path:
    p = tmp_path / name
    p.write_bytes(b"")
    return p


# ---------------------------------------------------------------------------
# 1. Mastering is always from live UI — SUNO Bypass ON
# ---------------------------------------------------------------------------

def test_mastering_always_from_ui_when_suno_bypass_on(tmp_path: Path):
    """build_items must take mastering from state.mastering (live UI), NOT from
    JSON, even when SUNO Bypass is enabled."""
    src = _src(tmp_path)
    # Live UI has bass=50 engaged
    ui_mastering = MasteringSettings(bass=50, bypass=False)
    ui_state = FileInformationState(
        metadata=Metadata(artist="UI Artist"),
        mastering=ui_mastering,
    )
    # JSON has bass=0 (default / different from UI)
    cs = _store(tmp_path, artist="JSON Artist", bass=0)

    items = build_items(
        [str(src)], str(tmp_path / "out"), ui_state,
        export=ExportSettings(suno_bypass=True),
        config_store=cs,
    )
    assert len(items) == 1
    item = items[0]
    # Mastering must come from live UI (bass=50), NOT from JSON (bass=0)
    assert item.mastering.bass == 50, (
        f"Expected bass=50 from UI, got bass={item.mastering.bass} (came from JSON)"
    )
    # And metadata must come from JSON
    assert item.metadata.artist == "JSON Artist"


# ---------------------------------------------------------------------------
# 2. Mastering is always from live UI — SUNO Bypass OFF
# ---------------------------------------------------------------------------

def test_mastering_from_ui_when_suno_bypass_off(tmp_path: Path):
    """Without SUNO Bypass mastering and metadata both come from live UI."""
    src = _src(tmp_path)
    ui_mastering = MasteringSettings(comp=42, bypass=False)
    ui_state = FileInformationState(
        metadata=Metadata(artist="My Artist"),
        mastering=ui_mastering,
    )
    cs = _store(tmp_path, artist="JSON Artist", bass=99)

    items = build_items(
        [str(src)], str(tmp_path / "out"), ui_state,
        export=ExportSettings(suno_bypass=False),
        config_store=cs,
    )
    item = items[0]
    assert item.mastering.comp == 42
    assert item.metadata.artist == "My Artist"   # UI, not JSON


# ---------------------------------------------------------------------------
# 3. force_re_encode is True when mastering chain is active
# ---------------------------------------------------------------------------

def test_force_re_encode_true_when_mastering_active(tmp_path: Path):
    """If any mastering slider is non-zero (and bypass is off), force_re_encode
    must be True so the filter graph is invoked."""
    src = _src(tmp_path)
    ui_state = FileInformationState(
        metadata=Metadata(artist="A"),
        mastering=MasteringSettings(verb=30, bypass=False),
    )
    # Use Same-as-source format so no other re-encode trigger applies
    from panha.dialogs.export_settings_dialog import (
        PRESERVE_SOURCE_FORMAT,
        PRESERVE_SOURCE_SAMPLE_RATE,
    )
    export = ExportSettings(
        format=PRESERVE_SOURCE_FORMAT,
        sample_rate=PRESERVE_SOURCE_SAMPLE_RATE,
        suno_bypass=False,
    )
    items = build_items([str(src)], str(tmp_path / "out"), ui_state, export=export)
    assert items[0].force_re_encode is True, (
        "force_re_encode must be True when mastering verb=30 is active"
    )


def test_force_re_encode_false_when_mastering_bypassed(tmp_path: Path):
    """If mastering BYPASS is on, the chain is inactive → force_re_encode
    should be False (assuming no other trigger applies)."""
    src = _src(tmp_path)
    ui_state = FileInformationState(
        metadata=Metadata(artist="A"),
        mastering=MasteringSettings(bass=50, bypass=True),  # bypassed!
    )
    from panha.dialogs.export_settings_dialog import (
        PRESERVE_SOURCE_FORMAT,
        PRESERVE_SOURCE_SAMPLE_RATE,
    )
    export = ExportSettings(
        format=PRESERVE_SOURCE_FORMAT,
        sample_rate=PRESERVE_SOURCE_SAMPLE_RATE,
        suno_bypass=False,
    )
    items = build_items([str(src)], str(tmp_path / "out"), ui_state, export=export)
    assert items[0].force_re_encode is False, (
        "Bypassed mastering must NOT trigger force_re_encode"
    )


# ---------------------------------------------------------------------------
# 4. Tracklist options always come from live UI even when SUNO Bypass is ON
# ---------------------------------------------------------------------------

def test_tracklist_always_from_ui_with_suno_bypass(tmp_path: Path):
    """Tracklist options (uppercase, cover size) must come from the live UI
    regardless of SUNO Bypass state."""
    src = _src(tmp_path, "01. Song Title.wav")
    ui_tracklist = TracklistOptions(
        uppercase=True,
        remove_track_number=True,
        cover_size=800,
        cover_height=600,
    )
    ui_state = FileInformationState(
        metadata=Metadata(artist="UI Artist"),
        tracklist=ui_tracklist,
    )
    cs = _store(tmp_path, artist="JSON Artist")

    items = build_items(
        [str(src)], str(tmp_path / "out"), ui_state,
        export=ExportSettings(suno_bypass=True),
        config_store=cs,
    )
    item = items[0]
    # Filename should be UPPERCASE and track number stripped
    target_stem = Path(item.target).stem
    assert target_stem == "SONG TITLE", (
        f"Expected uppercase + track-stripped stem, got '{target_stem}'"
    )
    # Cover size from UI (800×600), NOT from JSON (which defaults to 3000×3000)
    assert item.cover_max_size == (800, 600), (
        f"Expected UI cover size (800, 600), got {item.cover_max_size}"
    )


# ---------------------------------------------------------------------------
# 5. SUNO Bypass metadata fields come from JSON
# ---------------------------------------------------------------------------

def test_suno_bypass_metadata_from_json(tmp_path: Path):
    """When SUNO Bypass is on, the embedded metadata (artist/album/genre)
    must come from the JSON config store, not from the live UI state."""
    src = _src(tmp_path)
    ui_state = FileInformationState(
        metadata=Metadata(artist="UI Artist", album="UI Album", genre="Pop"),
    )
    cs = _store(tmp_path, artist="JSON Artist")

    items = build_items(
        [str(src)], str(tmp_path / "out"), ui_state,
        export=ExportSettings(suno_bypass=True),
        config_store=cs,
    )
    meta = items[0].metadata
    assert meta.artist == "JSON Artist"
    assert meta.album == "JSON Album"
    assert meta.genre == "R&B"


# ---------------------------------------------------------------------------
# 6. strip_source_metadata follows suno_bypass
# ---------------------------------------------------------------------------

def test_strip_source_metadata_only_when_suno_bypass(tmp_path: Path):
    src = _src(tmp_path)
    ui_state = FileInformationState(metadata=Metadata(artist="A"))
    cs = _store(tmp_path)

    items_on = build_items(
        [str(src)], str(tmp_path / "out"), ui_state,
        export=ExportSettings(suno_bypass=True), config_store=cs,
    )
    items_off = build_items(
        [str(src)], str(tmp_path / "out"), ui_state,
        export=ExportSettings(suno_bypass=False), config_store=cs,
    )
    assert items_on[0].strip_source_metadata is True
    assert items_off[0].strip_source_metadata is False
