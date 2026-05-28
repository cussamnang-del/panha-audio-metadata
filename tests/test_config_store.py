"""Tests for ConfigStore (panha/metadata.json persistence)."""

from __future__ import annotations

from pathlib import Path

import pytest

from panha.config_store import ConfigStore, state_from_flat, state_to_flat


# ---------------------------------------------------------------------------
# Round-trip helpers
# ---------------------------------------------------------------------------

def _make_store(tmp_path: Path) -> ConfigStore:
    return ConfigStore(tmp_path / "metadata.json")


def test_load_last_state_returns_default_when_missing(tmp_path: Path):
    store = _make_store(tmp_path)
    state = store.load_last_state()
    assert state.enabled is True
    assert state.metadata.artist == ""


def test_save_and_reload_last_state(tmp_path: Path):
    from panha.dialogs.file_info_dialog import FileInformationState, TracklistOptions
    from panha.metadata import Metadata

    store = _make_store(tmp_path)
    state = FileInformationState(
        enabled=True,
        metadata=Metadata(artist="Panha", album="Test Album", year="2026", genre="Pop"),
        tracklist=TracklistOptions(uppercase=True, remove_track_number=False,
                                   cover_size=800, cover_height=600),
    )
    store.save_last_state(state)
    loaded = store.load_last_state()

    assert loaded.metadata.artist == "Panha"
    assert loaded.metadata.album == "Test Album"
    assert loaded.metadata.year == "2026"
    assert loaded.metadata.genre == "Pop"
    assert loaded.tracklist.uppercase is True
    assert loaded.tracklist.remove_track_number is False
    assert loaded.tracklist.cover_size == 800
    assert loaded.tracklist.cover_height == 600


def test_save_last_state_preserves_other_keys(tmp_path: Path):
    """Saving last_state must not erase templates or last_template."""
    import json
    from panha.dialogs.file_info_dialog import FileInformationState

    store = _make_store(tmp_path)
    # Pre-populate the file with templates.
    store.save_templates({"my_tpl": {"artist": "x"}})
    store.save_last_template("my_tpl")
    store.save_last_state(FileInformationState())

    doc = json.loads(store.path.read_text(encoding="utf-8"))
    assert "my_tpl" in doc["templates"]
    assert doc["last_template"] == "my_tpl"


def test_save_and_reload_last_template(tmp_path: Path):
    store = _make_store(tmp_path)
    assert store.load_last_template() == ""
    store.save_last_template("Rock Punch")
    assert store.load_last_template() == "Rock Punch"


def test_save_and_reload_templates(tmp_path: Path):
    store = _make_store(tmp_path)
    templates = {"my_preset": {"enabled": True, "metadata": {"artist": "A"}}}
    store.save_templates(templates)
    loaded = store.load_templates()
    assert loaded == templates


def test_corrupt_file_returns_defaults(tmp_path: Path):
    path = tmp_path / "metadata.json"
    path.write_text("{not valid json", encoding="utf-8")
    store = ConfigStore(path)
    state = store.load_last_state()
    assert state.enabled is True  # default


def test_state_flat_roundtrip(tmp_path: Path):
    """state_to_flat -> state_from_flat must be lossless for all basic fields."""
    from panha.dialogs.file_info_dialog import FileInformationState, TracklistOptions
    from panha.metadata import Metadata

    original = FileInformationState(
        enabled=False,
        metadata=Metadata(
            artist="Test Artist",
            album="My Album",
            year="2025",
            genre="Jazz",
            rating="4",
            cover_path="/covers/img.jpg",
            engineer="Eng",
            copyright="(c) 2025",
            software="DAW",
            source="SRC",
            comment="hello",
        ),
        tracklist=TracklistOptions(
            uppercase=True,
            remove_track_number=False,
            cover_size=400,
            cover_height=400,
        ),
    )
    flat = state_to_flat(original)
    restored = state_from_flat(flat)

    assert restored.enabled is False
    assert restored.metadata.artist == "Test Artist"
    assert restored.metadata.album == "My Album"
    assert restored.metadata.year == "2025"
    assert restored.metadata.genre == "Jazz"
    assert restored.metadata.rating == "4"
    assert restored.metadata.cover_path == "/covers/img.jpg"
    assert restored.metadata.engineer == "Eng"
    assert restored.metadata.copyright == "(c) 2025"
    assert restored.metadata.software == "DAW"
    assert restored.metadata.source == "SRC"
    assert restored.metadata.comment == "hello"
    assert restored.tracklist.uppercase is True
    assert restored.tracklist.remove_track_number is False
    assert restored.tracklist.cover_size == 400
    assert restored.tracklist.cover_height == 400


# ---------------------------------------------------------------------------
# SUNO Bypass: build_items uses panha/metadata.json as metadata source
# ---------------------------------------------------------------------------

def test_build_items_suno_bypass_reads_from_config_store(tmp_path: Path):
    """When suno_bypass=True, build_items must read artist/album from
    the ConfigStore (panha/metadata.json), not from the passed-in state."""
    from panha.dialogs.export_settings_dialog import ExportSettings
    from panha.dialogs.file_info_dialog import FileInformationState
    from panha.metadata import Metadata
    from panha.widgets.worker import build_items

    src = tmp_path / "song.mp3"
    src.write_bytes(b"")

    # Live UI state has "UI Artist" (should be ignored in SUNO Bypass mode)
    ui_state = FileInformationState(metadata=Metadata(artist="UI Artist"))

    # JSON store has "JSON Artist" (should WIN in SUNO Bypass mode)
    store = _make_store(tmp_path)
    store.save_last_state(
        FileInformationState(metadata=Metadata(artist="JSON Artist", album="JSON Album"))
    )

    export = ExportSettings(suno_bypass=True)
    items = build_items(
        [str(src)], str(tmp_path / "out"), ui_state,
        export=export, config_store=store,
    )

    assert len(items) == 1
    assert items[0].metadata.artist == "JSON Artist"
    assert items[0].metadata.album == "JSON Album"
    assert items[0].strip_source_metadata is True


def test_build_items_no_suno_bypass_uses_ui_state(tmp_path: Path):
    """Without SUNO Bypass, build_items must use the live UI state."""
    from panha.dialogs.export_settings_dialog import ExportSettings
    from panha.dialogs.file_info_dialog import FileInformationState
    from panha.metadata import Metadata
    from panha.widgets.worker import build_items

    src = tmp_path / "song.mp3"
    src.write_bytes(b"")

    ui_state = FileInformationState(metadata=Metadata(artist="UI Artist"))

    store = _make_store(tmp_path)
    store.save_last_state(
        FileInformationState(metadata=Metadata(artist="JSON Artist"))
    )

    export = ExportSettings(suno_bypass=False)
    items = build_items(
        [str(src)], str(tmp_path / "out"), ui_state,
        export=export, config_store=store,
    )

    assert items[0].metadata.artist == "UI Artist"
    assert items[0].strip_source_metadata is False


def test_build_items_suno_bypass_sets_strip_source_metadata(tmp_path: Path):
    """SUNO Bypass must always set strip_source_metadata=True."""
    from panha.dialogs.export_settings_dialog import ExportSettings
    from panha.dialogs.file_info_dialog import FileInformationState
    from panha.metadata import Metadata
    from panha.widgets.worker import build_items

    src = tmp_path / "track.mp3"
    src.write_bytes(b"")
    store = _make_store(tmp_path)
    store.save_last_state(FileInformationState(metadata=Metadata(artist="A")))

    items = build_items(
        [str(src)], str(tmp_path / "out"),
        FileInformationState(),
        export=ExportSettings(suno_bypass=True),
        config_store=store,
    )
    assert items[0].strip_source_metadata is True
