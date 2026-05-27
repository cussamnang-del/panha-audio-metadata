"""Tests for the ffmpeg metadata writer."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from panha.metadata import (
    Metadata,
    format_duration,
    probe_duration_seconds,
    read_metadata,
    resolve_cover_path,
    write_metadata,
)


def test_metadata_dataclass_defaults():
    m = Metadata()
    assert m.title == ""
    assert m.to_ffmpeg_args() == []


def test_metadata_to_ffmpeg_args_skips_empty_fields():
    m = Metadata(title="Hello", artist="World", year="", comment="ok")
    args = m.to_ffmpeg_args()
    assert "-metadata" in args
    assert "title=Hello" in args
    assert "artist=World" in args
    assert "comment=ok" in args
    assert "date=" not in args
    assert all("year" not in a for a in args)


def test_metadata_software_uses_standard_ffmpeg_keys_only():
    """Regression: ``TSSE`` is a raw ID3 frame name, not a valid ffmpeg
    -metadata key, and it must not leak into the command line.
    """
    args = Metadata(software="PanhaApp v1").to_ffmpeg_args()
    assert "encoder=PanhaApp v1" in args
    assert "encoded_by=PanhaApp v1" in args
    assert not any(a.startswith("TSSE=") for a in args)


def test_format_duration():
    assert format_duration(0) == "--:--"
    assert format_duration(-1) == "--:--"
    assert format_duration(65) == "1:05"
    assert format_duration(125) == "2:05"
    assert format_duration(3725) == "1:02:05"


def test_probe_duration_seconds(sample_mp3: Path):
    duration = probe_duration_seconds(sample_mp3)
    assert 0.5 <= duration <= 2.5


def test_probe_duration_missing_file(tmp_path: Path):
    assert probe_duration_seconds(tmp_path / "nope.mp3") == 0.0


def test_write_metadata_basic_fields(sample_mp3: Path, tmp_path: Path):
    out = tmp_path / "tagged.mp3"
    meta = Metadata(
        title="My Song", artist="Panha", album="Echoes",
        year="2026", genre="Lo-fi", comment="hello world",
    )
    result = write_metadata(sample_mp3, out, meta)
    assert Path(result).exists()
    tags = read_metadata(out)
    assert tags.get("title") == "My Song"
    assert tags.get("artist") == "Panha"
    assert tags.get("album") == "Echoes"
    assert "2026" in tags.get("date", "")
    assert tags.get("genre") == "Lo-fi"
    assert tags.get("comment") == "hello world"


def test_write_metadata_overwrites_existing(sample_mp3: Path, tmp_path: Path):
    out = tmp_path / "tagged.mp3"
    write_metadata(sample_mp3, out, Metadata(title="first"))
    write_metadata(sample_mp3, out, Metadata(title="second"))
    tags = read_metadata(out)
    assert tags.get("title") == "second"


def test_write_metadata_in_place(sample_mp3: Path):
    write_metadata(sample_mp3, sample_mp3, Metadata(title="in-place"))
    tags = read_metadata(sample_mp3)
    assert tags.get("title") == "in-place"


def test_write_metadata_embeds_cover(
    sample_mp3: Path, sample_cover: Path, tmp_path: Path
):
    import json

    out = tmp_path / "with-cover.mp3"
    meta = Metadata(title="Cover Test", cover_path=str(sample_cover))
    write_metadata(sample_mp3, out, meta)

    # ffprobe should report a video stream with attached_pic disposition.
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_streams",
            "-of", "json",
            str(out),
        ],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(proc.stdout)
    video_streams = [s for s in data["streams"] if s.get("codec_type") == "video"]
    assert video_streams, "expected a video stream for cover art"
    assert any(
        s.get("disposition", {}).get("attached_pic") == 1 for s in video_streams
    ), "expected attached_pic disposition on cover stream"


def test_write_metadata_missing_source(tmp_path: Path, ffmpeg_required):
    with pytest.raises(FileNotFoundError):
        write_metadata(tmp_path / "does-not-exist.mp3", tmp_path / "out.mp3", Metadata())


def test_resolve_cover_path_passthrough_for_file(sample_cover: Path):
    assert resolve_cover_path(str(sample_cover)) == str(sample_cover)


def test_resolve_cover_path_picks_first_image_in_folder(
    tmp_path: Path, sample_cover: Path
):
    # Drop the cover (and a decoy non-image) into a folder; resolution
    # must skip the .txt and return the .jpg.
    folder = tmp_path / "art"
    folder.mkdir()
    (folder / "readme.txt").write_text("not an image")
    target = folder / "cover.jpg"
    target.write_bytes(sample_cover.read_bytes())
    assert resolve_cover_path(str(folder)) == str(target)


def test_resolve_cover_path_empty_inputs(tmp_path: Path):
    assert resolve_cover_path("") == ""
    assert resolve_cover_path(str(tmp_path / "nope")) == ""
    empty = tmp_path / "empty_dir"
    empty.mkdir()
    assert resolve_cover_path(str(empty)) == ""


def test_write_metadata_embeds_cover_when_cover_path_is_a_folder(
    sample_mp3: Path, sample_cover: Path, tmp_path: Path
):
    """Regression: the dialog's 'Folder' button populates ``cover_path``
    with a directory; the writer must resolve that to the first image
    inside instead of silently dropping the cover.
    """
    import json

    folder = tmp_path / "covers"
    folder.mkdir()
    (folder / "art.jpg").write_bytes(sample_cover.read_bytes())

    out = tmp_path / "with-folder-cover.mp3"
    write_metadata(
        sample_mp3, out, Metadata(title="folder cover", cover_path=str(folder))
    )

    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(out)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(proc.stdout)
    assert any(
        s.get("codec_type") == "video"
        and s.get("disposition", {}).get("attached_pic") == 1
        for s in data["streams"]
    ), "cover should be embedded when cover_path is a directory"


def test_write_metadata_does_not_inherit_stdin(
    sample_mp3: Path, sample_cover: Path, tmp_path: Path, monkeypatch
):
    """ffmpeg must run with stdin=DEVNULL so a backgrounded app does not
    get its ffmpeg children frozen by SIGTTIN when they try to read the
    inherited terminal."""
    captured: dict[str, object] = {}
    real_popen = subprocess.Popen

    def fake_popen(cmd, *args, **kwargs):
        captured["cmd"] = list(cmd)
        captured["stdin"] = kwargs.get("stdin")
        return real_popen(cmd, *args, **kwargs)

    from panha.metadata import ffmpeg_writer

    monkeypatch.setattr(ffmpeg_writer.subprocess, "Popen", fake_popen)

    out = tmp_path / "out.mp3"
    write_metadata(
        sample_mp3, out, Metadata(title="x", cover_path=str(sample_cover))
    )

    assert captured["stdin"] == subprocess.DEVNULL
    assert "-nostdin" in captured["cmd"]


def test_write_metadata_terminates_ffmpeg_on_cancel(
    sample_mp3: Path, tmp_path: Path, monkeypatch
):
    """When cancel_check flips to True mid-export, write_metadata must
    terminate the ffmpeg child and raise MetadataWriteCancelledError rather
    than blocking until ffmpeg finishes on its own.
    """
    from panha.metadata import MetadataWriteCancelledError, ffmpeg_writer

    real_popen = subprocess.Popen
    started: list[subprocess.Popen] = []

    def slow_popen(cmd, *args, **kwargs):
        # Replace the real ffmpeg command with a long-running sleep so we
        # can race the cancel against it deterministically.
        proc = real_popen(
            ["sh", "-c", "sleep 30"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        started.append(proc)
        return proc

    monkeypatch.setattr(ffmpeg_writer.subprocess, "Popen", slow_popen)

    cancelled = {"value": False}
    poll_count = {"n": 0}

    def cancel_check() -> bool:
        # Trip cancel after the first poll (≈100ms in) so we know the
        # child actually started.
        poll_count["n"] += 1
        if poll_count["n"] >= 1:
            cancelled["value"] = True
        return cancelled["value"]

    out = tmp_path / "out.mp3"
    with pytest.raises(MetadataWriteCancelledError):
        write_metadata(
            sample_mp3, out, Metadata(title="cancel-me"),
            cancel_check=cancel_check,
            poll_interval=0.05,
            terminate_grace=2.0,
        )

    # The slow_popen child must be terminated (returncode set) and the
    # destination file must NOT exist because we never reached os.replace.
    assert started, "ffmpeg child was not started"
    assert started[0].poll() is not None, "ffmpeg child was never terminated"
    assert not out.exists(), "destination should not exist on cancel"


def test_write_metadata_cancel_check_unused_when_never_true(
    sample_mp3: Path, tmp_path: Path
):
    """Passing a cancel_check that always returns False must not change
    the normal success path."""
    out = tmp_path / "ok.mp3"
    write_metadata(
        sample_mp3, out, Metadata(title="ok"),
        cancel_check=lambda: False,
        poll_interval=0.05,
    )
    assert out.exists()


def test_write_metadata_sample_rate_override(
    sample_mp3: Path, tmp_path: Path
):
    """sample_rate_hz must add `-ar <hz>` and force a re-encode."""
    out = tmp_path / "ar.mp3"
    write_metadata(
        sample_mp3, out, Metadata(title="ar"), sample_rate_hz=22050
    )
    # ffprobe the resulting file and confirm sample rate matches.
    import json
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-select_streams", "a",
         "-of", "json", str(out)],
        capture_output=True, text=True, check=True,
    )
    streams = json.loads(proc.stdout)["streams"]
    assert streams, "no audio stream in output"
    assert int(streams[0]["sample_rate"]) == 22050


def test_write_metadata_lufs_target_adds_loudnorm(
    sample_mp3: Path, tmp_path: Path, monkeypatch
):
    """lufs_target_lufs must inject a loudnorm filter and re-encode."""
    captured: dict[str, object] = {}
    real_popen = subprocess.Popen

    def capturing_popen(cmd, *args, **kwargs):
        captured.setdefault("cmd", list(cmd))
        return real_popen(cmd, *args, **kwargs)

    from panha.metadata import ffmpeg_writer
    monkeypatch.setattr(ffmpeg_writer.subprocess, "Popen", capturing_popen)

    out = tmp_path / "loud.mp3"
    write_metadata(
        sample_mp3, out, Metadata(title="loud"), lufs_target_lufs=-14.0
    )

    cmd = captured["cmd"]
    assert "-af" in cmd
    af = cmd[cmd.index("-af") + 1]
    assert "loudnorm=I=-14.0" in af
    # And the codec must NOT be the stream-copy shortcut.
    assert "copy" not in cmd[cmd.index("-af"):]


def test_write_metadata_codec_args_override(
    sample_mp3: Path, tmp_path: Path
):
    """codec_args_override replaces the format-default codec args
    entirely (used by WAV bit-depth selection)."""
    out = tmp_path / "out.wav"
    write_metadata(
        sample_mp3, out, Metadata(title="wavout"),
        codec_args_override=["-c:a", "pcm_s16le"],
    )
    import json
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-select_streams", "a",
         "-of", "json", str(out)],
        capture_output=True, text=True, check=True,
    )
    streams = json.loads(proc.stdout)["streams"]
    assert streams[0]["codec_name"] == "pcm_s16le"


def test_write_metadata_cover_max_size_emits_scale_filter(
    sample_mp3: Path, sample_cover: Path, tmp_path: Path, monkeypatch
):
    """Regression: the File Information Cover Size / Height spinboxes
    used to be silently ignored. When cover_max_size is provided, the
    ffmpeg invocation must include a per-stream scale filter on the
    cover input so the embedded artwork is actually resized.
    """
    captured: dict[str, list[str]] = {}
    real_popen = subprocess.Popen

    def capturing_popen(cmd, *args, **kwargs):
        captured.setdefault("cmd", list(cmd))
        return real_popen(cmd, *args, **kwargs)

    from panha.metadata import ffmpeg_writer
    monkeypatch.setattr(ffmpeg_writer.subprocess, "Popen", capturing_popen)

    out = tmp_path / "scaled.mp3"
    write_metadata(
        sample_mp3, out,
        Metadata(title="scaled", cover_path=str(sample_cover)),
        cover_max_size=(320, 240),
    )

    cmd = captured["cmd"]
    assert "-filter:v:0" in cmd, f"missing -filter:v:0 in {cmd}"
    scale_arg = cmd[cmd.index("-filter:v:0") + 1]
    assert scale_arg.startswith("scale=320:240")
    assert "force_original_aspect_ratio=decrease" in scale_arg


def test_write_metadata_no_scale_filter_when_cover_max_size_omitted(
    sample_mp3: Path, sample_cover: Path, tmp_path: Path, monkeypatch
):
    """When cover_max_size is None we must not inject a video filter --
    that's the historical zero-loss behavior callers rely on."""
    captured: dict[str, list[str]] = {}
    real_popen = subprocess.Popen

    def capturing_popen(cmd, *args, **kwargs):
        captured.setdefault("cmd", list(cmd))
        return real_popen(cmd, *args, **kwargs)

    from panha.metadata import ffmpeg_writer
    monkeypatch.setattr(ffmpeg_writer.subprocess, "Popen", capturing_popen)

    out = tmp_path / "unchanged.mp3"
    write_metadata(
        sample_mp3, out,
        Metadata(title="unchanged", cover_path=str(sample_cover)),
    )

    cmd = captured["cmd"]
    assert "-filter:v:0" not in cmd
    assert not any(arg.startswith("scale=") for arg in cmd)


def test_write_metadata_force_re_encode_alone(
    sample_mp3: Path, tmp_path: Path, monkeypatch
):
    """force_re_encode=True must drop the `-c:a copy` shortcut even
    when no filter chain / codec override / sample-rate is supplied."""
    captured: dict[str, object] = {}
    real_popen = subprocess.Popen

    def capturing_popen(cmd, *args, **kwargs):
        captured.setdefault("cmd", list(cmd))
        return real_popen(cmd, *args, **kwargs)

    from panha.metadata import ffmpeg_writer
    monkeypatch.setattr(ffmpeg_writer.subprocess, "Popen", capturing_popen)

    out = tmp_path / "fre.mp3"
    write_metadata(
        sample_mp3, out, Metadata(title="fre"), force_re_encode=True
    )

    cmd = captured["cmd"]
    # When re-encoding via the default codec args for .mp3, libmp3lame
    # is used. The `copy` literal must not appear.
    assert "-c:a" in cmd
    assert "libmp3lame" in cmd
    assert "copy" not in cmd


def test_export_settings_helpers_translate_dialog_strings():
    """ExportSettings parser methods are the single source of truth that
    UI strings map to writer-friendly values."""
    from panha.dialogs.export_settings_dialog import ExportSettings

    es = ExportSettings(
        format="WAV", sample_rate="48000 Hz", bit_depth="24-bit",
        lufs_target="-14 LUFS",
    )
    assert es.output_suffix_for(".mp3") == ".wav"
    assert es.parsed_sample_rate_hz() == 48000
    assert es.parsed_lufs_target() == -14.0
    assert es.codec_args_override() == ["-c:a", "pcm_s24le"]

    # Default state: everything is a no-op (preserve source, no LUFS).
    default = ExportSettings()
    assert default.output_suffix_for(".flac") == ".flac"
    assert default.output_suffix_for("") == ".mp3"
    assert default.parsed_sample_rate_hz() is None
    assert default.parsed_lufs_target() is None
    assert default.codec_args_override() is None

    # MP3-as-target: no bit-depth codec override (bit depth is WAV-only).
    mp3 = ExportSettings(format="MP3", bit_depth="32-bit")
    assert mp3.output_suffix_for(".wav") == ".mp3"
    assert mp3.codec_args_override() is None
