"""Audit pass — tests for previously-uncovered code paths.

Covers:
* config_store: nested-format branch, unknown-mastering-key resilience,
  mastering round-trip, exception-fallback in load_last_state
* detector: wildcard key branch in _gather_tag_blob
* export_settings_dialog: ValueError paths in parsed_sample_rate_hz /
  parsed_lufs_target
* ffmpeg_writer: overwrite=False, FileNotFoundError src, probe_duration
  ValueError/json-error paths
* presets: invalid preset entry guard
* templates: path property
* worker: parallel cancel-before-submit
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# config_store
# ---------------------------------------------------------------------------

class TestConfigStoreAudit:
    """Extra coverage for config_store paths missed by test_config_store.py."""

    def _store(self, tmp_path: Path):
        from panha.config_store import ConfigStore
        return ConfigStore(tmp_path / "metadata.json")

    # nested (FileInformationState.to_dict) format → line 119
    def test_state_from_flat_nested_format(self, tmp_path: Path):
        """When last_state was saved with FileInformationState.to_dict()
        (nested keys: 'metadata', 'tracklist', 'mastering') it must
        round-trip through state_from_flat correctly."""
        from panha.config_store import state_from_flat
        from panha.dialogs.file_info_dialog import FileInformationState
        from panha.metadata import Metadata

        original = FileInformationState(metadata=Metadata(artist="Nested Artist"))
        nested_dict = original.to_dict()  # produces 'metadata', 'tracklist', 'mastering'
        restored = state_from_flat(nested_dict)
        assert restored.metadata.artist == "Nested Artist"

    # unknown mastering key must NOT lose metadata → bug fix
    def test_load_last_state_survives_unknown_mastering_key(self, tmp_path: Path):
        """state_from_flat must silently drop unknown mastering keys rather
        than throwing TypeError and losing all user metadata."""
        import json as _json
        store = self._store(tmp_path)
        # Write a config with a bogus mastering key.
        store.path.write_text(_json.dumps({
            "templates": {},
            "last_template": "",
            "last_state": {
                "enable": True,
                "artist": "Safe Artist",
                "album": "",
                "year": "2026",
                "genre": "",
                "rating": "None",
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
                # "bogus_slider" is NOT a MasteringSettings field
                "mastering": {"bass": 30, "bogus_slider": 99},
            },
        }, indent=2), encoding="utf-8")
        loaded = store.load_last_state()
        # Artist MUST survive — the unknown key must be silently ignored.
        assert loaded.metadata.artist == "Safe Artist"
        # Known mastering field should still load.
        assert loaded.mastering.bass == 30

    # mastering values round-trip through flat save/load
    def test_mastering_round_trips_through_config_store(self, tmp_path: Path):
        from panha.config_store import ConfigStore
        from panha.dialogs.file_info_dialog import FileInformationState
        from panha.mastering import MasteringSettings
        from panha.metadata import Metadata

        store = ConfigStore(tmp_path / "m.json")
        state = FileInformationState(
            metadata=Metadata(artist="MasterTest"),
            mastering=MasteringSettings(bass=42, comp=55, bypass=True),
        )
        store.save_last_state(state)
        loaded = store.load_last_state()
        assert loaded.metadata.artist == "MasterTest"
        assert loaded.mastering.bass == 42
        assert loaded.mastering.comp == 55
        assert loaded.mastering.bypass is True

    # exception-fallback path → lines 179-182
    def test_load_last_state_falls_back_on_corrupt_last_state_value(self, tmp_path: Path):
        """If last_state is present but contains data that can't be
        decoded at all, load_last_state must return a default rather
        than propagating the exception."""
        store = self._store(tmp_path)
        store.path.write_text(json.dumps({
            "templates": {},
            "last_template": "",
            "last_state": "this is a string not a dict",
        }, indent=2), encoding="utf-8")
        state = store.load_last_state()
        # Must be the default — no crash.
        assert state.metadata.artist == ""


# ---------------------------------------------------------------------------
# detector: wildcard key branch
# ---------------------------------------------------------------------------

class TestDetectorWildcardKey:
    """_gather_tag_blob must include values whose *key* contains 'comment',
    'description', etc. even when the key isn't in _TAG_FIELDS."""

    def test_wildcard_comment_key_is_scanned(self, tmp_path: Path):
        """A key like 'comment-eng' (not in _TAG_FIELDS) must still be
        included in the blob so Suno markers in it are detected."""
        from panha.detector import _classify

        # 'comment-eng' is NOT in _TAG_FIELDS but contains 'comment'.
        tags = {"comment-eng": "Visit suno.com/song/abc123"}
        result = _classify(tags, "unknownsong.mp3")
        assert result.is_ai is True
        assert result.platform == "Suno"

    def test_wildcard_txxx_key_is_scanned(self, tmp_path: Path):
        from panha.detector import _classify

        tags = {"txxx:custom_url": "https://suno.ai/song/xyz"}
        result = _classify(tags, "song.mp3")
        assert result.is_ai is True

    def test_empty_value_in_wildcard_key_is_skipped(self, tmp_path: Path):
        from panha.detector import _classify

        # Empty value must not add noise to the blob.
        tags = {"comment-eng": ""}
        result = _classify(tags, "clean.mp3")
        assert result.is_ai is False


# ---------------------------------------------------------------------------
# export_settings_dialog: ValueError paths
# ---------------------------------------------------------------------------

class TestExportSettingsEdgeCases:
    """Malformed string values must return None, not raise."""

    def test_parsed_sample_rate_hz_non_numeric(self):
        from panha.dialogs.export_settings_dialog import ExportSettings
        s = ExportSettings(sample_rate="abc Hz")
        assert s.parsed_sample_rate_hz() is None

    def test_parsed_sample_rate_hz_empty_string(self):
        from panha.dialogs.export_settings_dialog import ExportSettings
        s = ExportSettings(sample_rate="")
        # Empty string is not PRESERVE_SOURCE_SAMPLE_RATE so falls to try/except.
        assert s.parsed_sample_rate_hz() is None

    def test_parsed_lufs_target_non_numeric(self):
        from panha.dialogs.export_settings_dialog import ExportSettings
        s = ExportSettings(lufs_target="bad LUFS")
        assert s.parsed_lufs_target() is None

    def test_parsed_lufs_target_empty_string(self):
        from panha.dialogs.export_settings_dialog import ExportSettings
        s = ExportSettings(lufs_target="")
        assert s.parsed_lufs_target() is None


# ---------------------------------------------------------------------------
# ffmpeg_writer: overwrite=False and missing src
# ---------------------------------------------------------------------------

class TestFfmpegWriterEdgeCases:
    def test_write_metadata_raises_file_not_found_for_missing_src(self, tmp_path: Path):
        from panha.metadata import Metadata, write_metadata
        with pytest.raises(FileNotFoundError):
            write_metadata(
                tmp_path / "missing.mp3",
                tmp_path / "out.mp3",
                Metadata(),
            )

    def test_write_metadata_raises_file_exists_when_overwrite_false(
        self, tmp_path: Path, monkeypatch
    ):
        from panha.metadata import Metadata, write_metadata

        src = tmp_path / "src.mp3"
        src.write_bytes(b"dummy")
        dst = tmp_path / "dst.mp3"
        dst.write_bytes(b"existing")

        with pytest.raises(FileExistsError):
            write_metadata(src, dst, Metadata(), overwrite=False)

    def test_probe_duration_returns_zero_on_json_decode_error(
        self, tmp_path: Path, monkeypatch
    ):
        """probe_duration_seconds must return 0.0 when ffprobe output is
        not valid JSON (json.JSONDecodeError path, lines 145-146)."""
        import subprocess
        from panha.metadata import probe_duration_seconds

        fake_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="not json", stderr=""
        )
        monkeypatch.setattr(
            "panha.metadata.ffmpeg_writer.subprocess.run",
            lambda *a, **k: fake_result,
        )
        monkeypatch.setattr(
            "panha.metadata.ffmpeg_writer._resolve_ffprobe",
            lambda *a, **k: "ffprobe",
        )
        src = tmp_path / "song.mp3"
        src.write_bytes(b"")
        assert probe_duration_seconds(str(src)) == 0.0

    def test_probe_duration_returns_zero_when_ffprobe_not_found(
        self, tmp_path: Path, monkeypatch
    ):
        """probe_duration_seconds must catch FfmpegNotFoundError and
        return 0.0 instead of propagating."""
        from panha.metadata import FfmpegNotFoundError, probe_duration_seconds
        monkeypatch.setattr(
            "panha.metadata.ffmpeg_writer._resolve_ffprobe",
            lambda *a, **k: (_ for _ in ()).throw(
                FfmpegNotFoundError("not found")
            ),
        )
        assert probe_duration_seconds("anything.mp3") == 0.0


# ---------------------------------------------------------------------------
# presets: invalid preset entry guard (line 152)
# ---------------------------------------------------------------------------

class TestPresetsInvalidEntry:
    def test_load_factory_presets_skips_non_string_name(self, tmp_path: Path):
        """A preset entry whose name is not a string must be silently
        ignored rather than crashing load_factory_presets."""
        import panha.presets as presets_mod

        bad_json = {
            "presets": {
                "ValidPreset": {"bass": 2, "compress": 50, "limit": 85},
                123: {"bass": 1},           # non-string name — must be skipped
            }
        }
        tmp_file = tmp_path / "presets.json"
        tmp_file.write_text(json.dumps(bad_json), encoding="utf-8")

        old_path = presets_mod.PRESETS_PATH
        try:
            presets_mod.PRESETS_PATH = tmp_file
            result = presets_mod.load_factory_presets(tmp_file)
        finally:
            presets_mod.PRESETS_PATH = old_path

        assert "ValidPreset" in result
        # The integer key must have been silently skipped.
        assert 123 not in result

    def test_load_factory_presets_skips_non_dict_payload(self, tmp_path: Path):
        """A preset entry whose payload is not a dict must also be skipped."""
        import panha.presets as presets_mod

        bad_json = {
            "presets": {
                "GoodPreset": {"bass": 3},
                "BadPayload": "this is a string not a dict",
            }
        }
        tmp_file = tmp_path / "presets.json"
        tmp_file.write_text(json.dumps(bad_json), encoding="utf-8")

        result = presets_mod.load_factory_presets(tmp_file)
        assert "GoodPreset" in result
        assert "BadPayload" not in result


# ---------------------------------------------------------------------------
# templates: path property (line 44)
# ---------------------------------------------------------------------------

class TestTemplateStorePath:
    def test_path_property_returns_config_store_path(self, tmp_path: Path):
        from panha.templates import TemplateStore
        p = tmp_path / "my_config.json"
        store = TemplateStore(p)
        assert store.path == p


# ---------------------------------------------------------------------------
# worker: parallel cancel-before-submit (lines 84-87)
# ---------------------------------------------------------------------------

class TestWorkerParallelCancelBeforeSubmit:
    """When cancel() is called before _run_parallel submits a future,
    the item must be emitted as 'Cancelled' and progress must tick."""

    def test_parallel_cancel_during_submission(self, tmp_path: Path):
        pytest.importorskip("PyQt6")
        from PyQt6.QtWidgets import QApplication
        from panha.metadata import Metadata
        from panha.widgets.worker import BatchItem, BatchWorker

        _app = QApplication.instance() or QApplication([])

        src = tmp_path / "in.mp3"
        src.write_bytes(b"")
        items = [
            BatchItem(
                source=str(src),
                target=str(tmp_path / f"out{i}.mp3"),
                metadata=Metadata(title=f"t{i}"),
            )
            for i in range(3)
        ]

        done: list[tuple[int, str]] = []
        progress_ticks: list[tuple[int, int]] = []
        finished = [False]

        worker = BatchWorker(items, max_threads=4)
        worker.item_done.connect(lambda i, s: done.append((i, s)))
        worker.progress.connect(lambda d, t: progress_ticks.append((d, t)))
        worker.finished.connect(lambda: finished.__setitem__(0, True))

        # Cancel before run() so _run_parallel never submits any future.
        worker.cancel()
        worker.run()
        _app.processEvents()

        assert finished[0] is True
        assert all(s == "Cancelled" for _, s in done)
        # Progress must tick to total (3/3) so the bar doesn't stall.
        assert progress_ticks[-1] == (3, 3)
