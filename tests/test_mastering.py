"""Tests for the mastering filter-chain builder."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from panha.mastering import (
    ALL_SLIDERS,
    DYN_NAMES,
    EQ_BANDS,
    EQ_NAMES,
    FX_NAMES,
    OUT_NAMES,
    SLIDER_MAX,
    MasteringSettings,
    codec_args_for,
)
from panha.metadata import Metadata, write_metadata


def test_default_settings_are_inactive():
    assert MasteringSettings().is_active() is False
    assert MasteringSettings().to_filter_chain() == ""


def test_bypass_overrides_active_sliders():
    settings = MasteringSettings(bass=50, comp=30, bypass=True)
    assert settings.is_active() is False
    assert settings.to_filter_chain() == ""


def test_each_slider_becomes_active_alone():
    for name in ALL_SLIDERS:
        s = MasteringSettings(**{name: 50})
        assert s.is_active() is True, name
        chain = s.to_filter_chain()
        assert chain, f"{name}=50 produced empty filter chain"


def test_eq_band_emits_equalizer_at_band_frequency():
    for name, _label, hz in EQ_BANDS:
        s = MasteringSettings(**{name: 99})
        chain = s.to_filter_chain()
        assert f"equalizer=f={hz}" in chain, f"missing band {hz} for {name}"
        # Max slider should reach the documented +12 dB ceiling.
        assert "g=12.00" in chain


def test_compressor_threshold_is_linear_not_db():
    s = MasteringSettings(comp=99)
    chain = s.to_filter_chain()
    assert "acompressor=" in chain
    # The threshold parameter passed to ffmpeg must be a linear amplitude
    # in [0, 1], not a dB value. At slider=99 → -30 dB → ~0.0316.
    assert "threshold=0.0316" in chain


def test_limiter_limit_decreases_with_slider():
    low = MasteringSettings(limit=1).to_filter_chain()
    high = MasteringSettings(limit=99).to_filter_chain()
    assert "alimiter=" in low and "alimiter=" in high
    # Higher slider → lower limit threshold (more aggressive).
    low_value = float(low.split("limit=")[1].split(":")[0])
    high_value = float(high.split("limit=")[1].split(":")[0])
    assert high_value < low_value
    assert pytest.approx(high_value, abs=0.01) == 0.5


def test_gain_emits_volume_in_db():
    chain = MasteringSettings(gain=99).to_filter_chain()
    assert "volume=12.00dB" in chain


def test_chain_is_comma_separated_when_multiple_filters_active():
    s = MasteringSettings(bass=10, gain=10)
    chain = s.to_filter_chain()
    assert chain.count(",") == 1
    assert chain.startswith("equalizer=")
    assert chain.endswith("dB")


def test_codec_args_table_has_known_suffixes():
    for suffix in (".mp3", ".m4a", ".aac", ".ogg", ".flac", ".wav"):
        args = codec_args_for(suffix)
        assert args[0] == "-c:a"
        assert len(args) >= 2


def test_codec_args_falls_back_to_mp3():
    assert codec_args_for(".xyz") == codec_args_for(".mp3")


def test_slider_value_clamps_at_max():
    over = MasteringSettings(gain=SLIDER_MAX + 50)
    under = MasteringSettings(gain=-5)
    assert "volume=12.00dB" in over.to_filter_chain()
    # Negative input clamps to 0 → slider is inactive.
    assert under.to_filter_chain() == ""


def test_categories_collectively_cover_all_sliders():
    union = set(EQ_NAMES) | set(DYN_NAMES) | set(FX_NAMES) | set(OUT_NAMES)
    assert union == set(ALL_SLIDERS)


# -- end-to-end: write_metadata applies the chain ---------------------


def test_write_metadata_stream_copies_when_mastering_default(
    sample_mp3: Path, tmp_path: Path
):
    out = tmp_path / "out.mp3"
    write_metadata(sample_mp3, out, Metadata(title="copy"), mastering=MasteringSettings())
    info = _ffprobe_audio_stream(out)
    # Stream-copy preserves the source codec (libmp3lame).
    assert info["codec_name"] == "mp3"


def test_write_metadata_re_encodes_when_mastering_active(
    sample_mp3: Path, tmp_path: Path
):
    copied = tmp_path / "copied.mp3"
    mastered = tmp_path / "mastered.mp3"
    write_metadata(sample_mp3, copied, Metadata(title="copy"))
    write_metadata(
        sample_mp3, mastered, Metadata(title="mastered"),
        mastering=MasteringSettings(gain=40, bass=40),
    )
    assert copied.exists() and mastered.exists()
    # Both files remain MP3.
    assert _ffprobe_audio_stream(copied)["codec_name"] == "mp3"
    assert _ffprobe_audio_stream(mastered)["codec_name"] == "mp3"
    # Stream-copy preserves the source's audio bytes verbatim; re-encode
    # rewrites the audio frames so the hashes must differ.
    assert _ffmpeg_audio_md5(copied) != _ffmpeg_audio_md5(mastered)


def _ffprobe_audio_stream(path: Path) -> dict:
    import json
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_streams",
            "-of", "json",
            str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(proc.stdout)
    return data["streams"][0]


def _ffmpeg_audio_md5(path: Path) -> str:
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", str(path),
            "-vn", "-map", "0:a",
            "-f", "md5", "-",
        ],
        capture_output=True, text=True, check=True,
    )
    return proc.stdout.strip()
