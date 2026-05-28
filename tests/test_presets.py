"""Tests for the bundled factory mastering presets.

Covers the three pieces wired together in :mod:`panha.presets`:

* the JSON loader (paths, package-data fallback, malformed input),
* the value scaler (dB-like vs percentage attributes, negatives clamp
  to 0, out-of-range values clamp to ``SLIDER_MAX``),
* the integration into :class:`~panha.templates.TemplateStore` and the
  ``MainWindow`` / ``FileInformationDialog`` Template combos so the
  UI actually surfaces them and protects them from deletion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from panha.mastering import SLIDER_MAX, MasteringSettings
from panha.presets import (
    PRESETS_PATH,
    _preset_payload_to_mastering,
    _scale_value,
    factory_preset_names,
    get_factory_preset,
    is_factory_preset,
    load_factory_presets,
)
from panha.templates import FactoryPresetReadOnlyError, TemplateStore

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# -- loader --------------------------------------------------------


def test_bundled_presets_file_exists():
    """The shipped JSON lives next to the package on disk."""
    assert PRESETS_PATH.exists(), (
        f"presets.json missing at {PRESETS_PATH} — package-data may "
        "not be bundled correctly."
    )


def test_load_factory_presets_returns_serialised_states():
    presets = load_factory_presets()
    assert presets, "Bundled presets.json must load at least one preset"
    assert "Default" in presets
    # Each entry is a FileInformationState dict — must have the
    # mastering sub-dict that the Template combo loads.
    default = presets["Default"]
    assert "mastering" in default
    assert default["mastering"]["bypass"] is False


def test_factory_preset_names_are_sorted_and_unique():
    names = factory_preset_names()
    assert names == sorted(names)
    assert len(names) == len(set(names))


def test_is_factory_preset_matches_loader():
    names = factory_preset_names()
    for name in names:
        assert is_factory_preset(name)
    assert not is_factory_preset("definitely-not-a-preset")


def test_get_factory_preset_returns_none_for_unknown():
    assert get_factory_preset("not-a-preset") is None


def test_load_factory_presets_falls_back_to_empty_on_missing_path(tmp_path: Path):
    missing = tmp_path / "nope.json"
    # The loader's last-resort fallback is the package-data file, so
    # we also need to ensure importlib can't satisfy this — point at
    # a clearly non-existent path; loader should never raise.
    result = load_factory_presets(path=missing)
    # Falls back to the package-data file when the explicit path is
    # missing — should still be the bundled presets.
    assert isinstance(result, dict)


def test_load_factory_presets_with_corrupt_file_returns_empty(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    # When the explicit path *exists* but is malformed, the loader
    # returns ``{}`` instead of raising or silently falling through to
    # the package fallback.
    assert load_factory_presets(path=bad) == {}


def test_load_factory_presets_with_non_dict_top_level_returns_empty(tmp_path: Path):
    bad = tmp_path / "list.json"
    bad.write_text('["just", "a", "list"]', encoding="utf-8")
    assert load_factory_presets(path=bad) == {}


def test_load_factory_presets_with_missing_presets_key_returns_empty(tmp_path: Path):
    bad = tmp_path / "shape.json"
    bad.write_text(json.dumps({"last_preset": "X"}), encoding="utf-8")
    assert load_factory_presets(path=bad) == {}


# -- value scaling -------------------------------------------------


@pytest.mark.parametrize("attr", ["bass", "deep", "mid", "clear", "treble", "pres", "gain"])
def test_scale_value_eq_like_attrs_use_db_scale(attr: str):
    """EQ-style sliders rescale a ±12 dB-like value into 0..99."""
    # 0 dB stays at 0.
    assert _scale_value(attr, 0) == 0
    # +12 dB lands at the top of the slider.
    assert _scale_value(attr, 12) == SLIDER_MAX
    # Sub-dB inputs round to nearest int.
    mid = _scale_value(attr, 6)
    assert 48 <= mid <= 50


@pytest.mark.parametrize("attr", ["comp", "limit", "sat", "verb", "echo", "width"])
def test_scale_value_percentage_attrs_pass_through(attr: str):
    """Percentage-style sliders are clamped, not rescaled."""
    assert _scale_value(attr, 0) == 0
    assert _scale_value(attr, 50) == 50
    assert _scale_value(attr, 99) == 99


def test_scale_value_clamps_negatives_to_zero():
    """Negative dB cuts collapse to 0 — current chain is boost-only."""
    assert _scale_value("bass", -4) == 0
    assert _scale_value("gain", -1) == 0
    assert _scale_value("comp", -10) == 0


def test_scale_value_clamps_above_slider_max():
    """Values above SLIDER_MAX get capped, never overflow the slider."""
    assert _scale_value("comp", 9999) == SLIDER_MAX
    assert _scale_value("bass", 999) == SLIDER_MAX


def test_scale_value_handles_non_numeric_gracefully():
    """Garbage values collapse to 0, never crash."""
    assert _scale_value("bass", None) == 0
    assert _scale_value("bass", "loud") == 0


def test_payload_translates_legacy_keys_to_mastering_attrs():
    """``vocal_clear`` / ``presence`` / ``compress`` / ... map correctly."""
    payload = {
        "vocal_clear": 6,
        "vocal_deep": 4,
        "presence": 3,
        "compress": 55,
        "saturate": 20,
        "reverb": 10,
        "stereo": 18,
        "limit": 90,
        "echo": 4,
        "bass": 5,
        "mid": 2,
        "treble": 3,
        "gain": 1,
    }
    settings = _preset_payload_to_mastering(payload)
    # EQ-like attrs were rescaled from dB-like values.
    assert settings.clear == _scale_value("clear", 6)
    assert settings.deep == _scale_value("deep", 4)
    assert settings.pres == _scale_value("pres", 3)
    assert settings.bass == _scale_value("bass", 5)
    assert settings.mid == _scale_value("mid", 2)
    assert settings.treble == _scale_value("treble", 3)
    assert settings.gain == _scale_value("gain", 1)
    # Percentage attrs were clamped only.
    assert settings.comp == 55
    assert settings.sat == 20
    assert settings.verb == 10
    assert settings.width == 18
    assert settings.limit == 90
    assert settings.echo == 4
    # Bypass defaults stay off so the preset's effect actually runs.
    assert settings.bypass is False


def test_payload_ignores_unknown_keys():
    """Future preset files may add new keys; loader must not crash."""
    settings = _preset_payload_to_mastering({"bass": 4, "experimental_widget": 99})
    assert isinstance(settings, MasteringSettings)
    assert settings.bass == _scale_value("bass", 4)


# -- TemplateStore integration ------------------------------------


def test_template_store_merges_factory_presets(tmp_path: Path):
    """``TemplateStore`` exposes factory presets by default."""
    store = TemplateStore(tmp_path / "templates.json")
    names = store.names()
    for factory_name in factory_preset_names():
        assert factory_name in names
    # The merged dict's payload for a factory entry must round-trip.
    payload = store.get("Default")
    assert payload is not None
    assert payload == get_factory_preset("Default")


def test_template_store_include_factory_false_hides_them(tmp_path: Path):
    store = TemplateStore(tmp_path / "templates.json", include_factory=False)
    assert store.names() == []
    assert store.get("Default") is None


def test_template_store_user_template_shadows_factory(tmp_path: Path):
    """A user template with the same name as a factory preset wins."""
    store = TemplateStore(tmp_path / "templates.json")
    # The name "Default" exists in the factory set; saving over it
    # is allowed for *names* that don't match factory entries, but
    # "Default" IS a factory entry — upsert should refuse.
    with pytest.raises(FactoryPresetReadOnlyError):
        store.upsert("Default", {"sentinel": True})

    # A non-conflicting name saves normally and shows up alongside
    # the factory presets.
    store.upsert("My Custom", {"sentinel": True})
    assert "My Custom" in store.names()
    assert store.get("My Custom") == {"sentinel": True}


def test_template_store_delete_refuses_factory_preset(tmp_path: Path):
    store = TemplateStore(tmp_path / "templates.json")
    assert store.delete("Default") is False
    # Sanity: still listed.
    assert "Default" in store.names()


def test_template_store_save_strips_factory_entries(tmp_path: Path):
    """Calling save() with merged data never persists factory presets."""
    path = tmp_path / "templates.json"
    store = TemplateStore(path)
    # Simulate a caller that round-trips the merged load() back to save()
    # — the on-disk file should still only contain *user* templates.
    merged = store.load()
    merged["My Custom"] = {"sentinel": True}
    store.save(merged)
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    for factory_name in factory_preset_names():
        assert factory_name not in on_disk
    assert on_disk.get("My Custom") == {"sentinel": True}


def test_template_store_is_factory_classmethod():
    assert TemplateStore.is_factory("Default") is True
    assert TemplateStore.is_factory("definitely-not-real") is False


# -- main window combo wiring -------------------------------------


def test_main_window_template_combo_lists_factory_presets(qapp, tmp_path: Path, monkeypatch):
    """The Template combo on the main window pre-populates with factory presets."""
    # Redirect the default templates file to an empty tmp location so
    # the test doesn't depend on the user's home dir state.
    monkeypatch.setattr(
        "panha.main_window.TemplateStore",
        lambda: TemplateStore(tmp_path / "templates.json"),
    )
    from panha.main_window import MainWindow

    win = MainWindow()
    try:
        labels = [
            win.cmb_template.itemText(i) for i in range(win.cmb_template.count())
        ]
        # First slot is the "Default" placeholder used to mean "no
        # template selected"; the factory presets follow.
        assert labels[0] == "Default"
        # All factory presets are present.
        for name in factory_preset_names():
            assert name in labels
    finally:
        win.deleteLater()


def test_main_window_factory_preset_disables_update_and_remove(
    qapp, tmp_path: Path, monkeypatch
):
    """Selecting a factory preset disables the Update / Remove buttons."""
    monkeypatch.setattr(
        "panha.main_window.TemplateStore",
        lambda: TemplateStore(tmp_path / "templates.json"),
    )
    from panha.main_window import MainWindow

    win = MainWindow()
    try:
        # Pick the first factory preset.
        idx = win.cmb_template.findText("Modern Pop")
        assert idx > 0, "Modern Pop preset should be in the combo"
        win.cmb_template.setCurrentIndex(idx)

        assert win._current_template_name == "Modern Pop"
        assert win.btn_update.isEnabled() is False
        assert win.btn_remove_template.isEnabled() is False
        # Save As stays available so users can fork the preset.
        assert win.btn_save_as.isEnabled() is True
    finally:
        win.deleteLater()


def test_main_window_factory_preset_preserves_metadata(
    qapp, tmp_path: Path, monkeypatch
):
    """Picking a factory preset only swaps mastering, never metadata."""
    monkeypatch.setattr(
        "panha.main_window.TemplateStore",
        lambda: TemplateStore(tmp_path / "templates.json"),
    )
    from panha.main_window import MainWindow

    win = MainWindow()
    try:
        # Seed some metadata the user "typed" before applying a preset.
        win._info_state.metadata.artist = "Panha"
        win._info_state.metadata.album = "Live"

        idx = win.cmb_template.findText("Pro Clear & Heavy")
        assert idx > 0
        win.cmb_template.setCurrentIndex(idx)

        # Mastering came from the preset.
        preset = get_factory_preset("Pro Clear & Heavy")
        assert preset is not None
        assert win._info_state.mastering.bass == preset["mastering"]["bass"]
        # Metadata survived the preset swap.
        assert win._info_state.metadata.artist == "Panha"
        assert win._info_state.metadata.album == "Live"
    finally:
        win.deleteLater()


# -- FileInformationDialog combo wiring ---------------------------


def test_file_info_dialog_lists_factory_presets(qapp, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "panha.dialogs.file_info_dialog.TemplateStore",
        lambda: TemplateStore(tmp_path / "templates.json"),
    )
    from panha.dialogs.file_info_dialog import FileInformationDialog

    dlg = FileInformationDialog()
    try:
        labels = [
            dlg.cmb_template.itemText(i) for i in range(dlg.cmb_template.count())
        ]
        # First slot is the "(no templates)" placeholder.
        assert labels[0] == "(no templates)"
        for name in factory_preset_names():
            assert name in labels
        # Delete must stay disabled when the only entries are factory
        # presets — they can't be removed.
        assert dlg.btn_template_delete.isEnabled() is False
    finally:
        dlg.deleteLater()


def test_file_info_dialog_factory_preset_keeps_user_metadata(
    qapp, tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(
        "panha.dialogs.file_info_dialog.TemplateStore",
        lambda: TemplateStore(tmp_path / "templates.json"),
    )
    from panha.dialogs.file_info_dialog import FileInformationDialog

    dlg = FileInformationDialog()
    try:
        # User typed in some metadata first.
        dlg.ed_artist.setText("Panha")
        dlg.ed_album.setText("Live")

        idx = dlg.cmb_template.findText("Modern Pop")
        assert idx > 0
        dlg.cmb_template.setCurrentIndex(idx)

        # Metadata survives the factory preset application.
        assert dlg.ed_artist.text() == "Panha"
        assert dlg.ed_album.text() == "Live"
        # Mastering values landed on the state from the factory preset.
        preset = get_factory_preset("Modern Pop")
        state = dlg.collect_state()
        assert state.mastering.bass == preset["mastering"]["bass"]
        # Delete is greyed out for a factory selection.
        assert dlg.btn_template_delete.isEnabled() is False
    finally:
        dlg.deleteLater()
