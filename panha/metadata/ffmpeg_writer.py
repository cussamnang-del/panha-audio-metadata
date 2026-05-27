"""ffmpeg-based ID3 metadata writer for MP3 files.

Uses ffmpeg via subprocess to write standard ID3v2 tags and embed cover art.
Falls back to in-place rename atomically by writing to a temporary file
next to the source and replacing it on success.

When a non-default :class:`~panha.mastering.MasteringSettings` is supplied
the audio is re-encoded with the corresponding filter chain instead of
stream-copied; otherwise ``-c:a copy`` is preserved for zero-loss tagging.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from ..mastering import MasteringSettings, codec_args_for


class FfmpegNotFoundError(RuntimeError):
    pass


class MetadataWriteError(RuntimeError):
    pass


class MetadataWriteCancelledError(RuntimeError):
    """Raised when ``cancel_check`` returns True mid-export.

    Distinct from :class:`MetadataWriteError` so callers (notably the
    batch worker) can report "Cancelled" rather than "Error: ...".
    """


@dataclasses.dataclass
class Metadata:
    """Metadata to write to an audio file.

    Fields map to standard ID3v2 frames where possible.
    Empty / None fields are left untouched on the file.
    """

    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    year: str = ""
    genre: str = ""
    track: str = ""
    rating: str = ""
    comment: str = ""
    description: str = ""
    engineer: str = ""
    copyright: str = ""
    software: str = ""
    source: str = ""
    cover_path: str = ""

    def to_ffmpeg_args(self) -> list[str]:
        """Build the list of ``-metadata KEY=VALUE`` args for ffmpeg.

        Only non-empty fields are emitted, so existing tags for blank fields
        are preserved.
        """
        mapping: dict[str, str] = {
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "album_artist": self.album_artist,
            "date": self.year,
            "genre": self.genre,
            "track": self.track,
            "rating": self.rating,
            "comment": self.comment,
            "description": self.description,
            "engineer": self.engineer,
            "copyright": self.copyright,
            "encoder": self.software,
            "encoded_by": self.software,
            "source": self.source,
        }
        args: list[str] = []
        for key, value in mapping.items():
            if value:
                args.extend(["-metadata", f"{key}={value}"])
        return args


def _resolve_ffmpeg(binary: str | None = None) -> str:
    candidate = binary or os.environ.get("PANHA_FFMPEG") or "ffmpeg"
    path = shutil.which(candidate)
    if not path:
        raise FfmpegNotFoundError(
            f"ffmpeg binary not found (looked for {candidate!r}). "
            "Install ffmpeg or set PANHA_FFMPEG."
        )
    return path


def _resolve_ffprobe(binary: str | None = None) -> str:
    candidate = binary or os.environ.get("PANHA_FFPROBE") or "ffprobe"
    path = shutil.which(candidate)
    if not path:
        raise FfmpegNotFoundError(
            f"ffprobe binary not found (looked for {candidate!r}). "
            "Install ffmpeg or set PANHA_FFPROBE."
        )
    return path


COVER_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def resolve_cover_path(cover_path: str | os.PathLike[str]) -> str:
    """Return a usable image file path for ``cover_path``.

    If ``cover_path`` points directly at a file it is returned unchanged.
    If it points at a directory, the first image (alphabetical, by
    :data:`COVER_IMAGE_SUFFIXES`) inside that directory is returned. The
    empty string is returned when no usable image can be located.
    """
    if not cover_path:
        return ""
    p = Path(cover_path)
    if p.is_file():
        return str(p)
    if p.is_dir():
        for child in sorted(p.iterdir()):
            if child.is_file() and child.suffix.lower() in COVER_IMAGE_SUFFIXES:
                return str(child)
    return ""


def probe_duration_seconds(path: str | os.PathLike[str], *, ffprobe: str | None = None) -> float:
    """Return the duration of an audio file in seconds, or 0.0 on failure."""
    try:
        bin_path = _resolve_ffprobe(ffprobe)
    except FfmpegNotFoundError:
        return 0.0
    try:
        out = subprocess.run(
            [
                bin_path,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(path),
            ],
            capture_output=True, text=True, check=True, timeout=20,
        )
        data = json.loads(out.stdout or "{}")
        return float(data.get("format", {}).get("duration", 0.0))
    except (subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return 0.0


def format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "--:--"
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def write_metadata(
    src: str | os.PathLike[str],
    dst: str | os.PathLike[str],
    meta: Metadata,
    *,
    mastering: MasteringSettings | None = None,
    ffmpeg: str | None = None,
    overwrite: bool = True,
    cancel_check: Callable[[], bool] | None = None,
    poll_interval: float = 0.1,
    terminate_grace: float = 2.0,
    sample_rate_hz: int | None = None,
    lufs_target_lufs: float | None = None,
    codec_args_override: list[str] | None = None,
    force_re_encode: bool = False,
    cover_max_size: tuple[int, int] | None = None,
) -> str:
    """Write ``meta`` to ``src`` and save the result at ``dst``.

    ``src`` and ``dst`` may point to the same file; the function writes
    through a temporary file and atomically replaces ``dst`` only on
    success.

    Audio is stream-copied (``-c:a copy``) when no mastering chain,
    LUFS target, codec override, sample-rate change or explicit
    ``force_re_encode`` is requested -- so tagging stays zero-loss for
    the common case. Re-encoding kicks in automatically when:

    * a non-bypassed :class:`MasteringSettings` is supplied, or
    * ``lufs_target_lufs`` is set (prepended as ``loudnorm=I=<n>:...``), or
    * ``codec_args_override`` is given (e.g. WAV bit-depth selection), or
    * ``sample_rate_hz`` is set (added as ``-ar <hz>``), or
    * ``force_re_encode=True``.

    Returns the absolute path to the written file.
    """
    src_path = Path(src).resolve()
    dst_path = Path(dst).resolve()
    if not src_path.exists():
        raise FileNotFoundError(src_path)
    if dst_path.exists() and not overwrite:
        raise FileExistsError(dst_path)

    ffmpeg_bin = _resolve_ffmpeg(ffmpeg)

    cover_file = resolve_cover_path(meta.cover_path) if meta.cover_path else ""
    has_cover = bool(cover_file)

    filter_parts: list[str] = []
    if lufs_target_lufs is not None:
        # ffmpeg loudnorm: integration target, true-peak ceiling, LRA.
        # The TP/LRA values mirror EBU R128 'broadcast' defaults and
        # are the same regardless of the chosen target LUFS so users
        # can A/B different targets without surprising re-clipping.
        filter_parts.append(
            f"loudnorm=I={lufs_target_lufs}:TP=-1.5:LRA=11"
        )
    mastering_chain = (
        mastering.to_filter_chain() if mastering is not None else ""
    )
    if mastering_chain:
        filter_parts.append(mastering_chain)
    filter_chain = ",".join(filter_parts)

    re_encode = (
        bool(filter_chain)
        or force_re_encode
        or codec_args_override is not None
        or sample_rate_hz is not None
    )

    cmd: list[str] = [
        ffmpeg_bin,
        "-y",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src_path),
    ]
    if has_cover:
        cmd.extend(["-i", cover_file])
        cmd.extend(["-map", "0:a", "-map", "1"])
    else:
        cmd.extend(["-map", "0:a"])

    if re_encode:
        if codec_args_override is not None:
            cmd.extend(codec_args_override)
        else:
            cmd.extend(codec_args_for(dst_path.suffix))
        if sample_rate_hz is not None:
            cmd.extend(["-ar", str(int(sample_rate_hz))])
        if filter_chain:
            cmd.extend(["-af", filter_chain])
    else:
        cmd.extend(["-c:a", "copy"])

    if has_cover:
        if cover_max_size is not None:
            max_w, max_h = cover_max_size
            if max_w > 0 and max_h > 0:
                cmd.extend([
                    "-filter:v:0",
                    f"scale={int(max_w)}:{int(max_h)}"
                    ":flags=lanczos:force_original_aspect_ratio=decrease",
                ])
        cmd.extend([
            "-c:v", "mjpeg",
            "-disposition:v", "attached_pic",
            "-metadata:s:v", "title=Album cover",
            "-metadata:s:v", "comment=Cover (front)",
        ])

    cmd.extend(["-id3v2_version", "3"])
    cmd.extend(meta.to_ffmpeg_args())

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = dst_path.suffix or ".mp3"
    with tempfile.NamedTemporaryFile(
        prefix=".panha_", suffix=suffix, dir=str(dst_path.parent), delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)

    cmd.append(str(tmp_path))

    try:
        _run_ffmpeg(
            cmd,
            src_path=src_path,
            cancel_check=cancel_check,
            poll_interval=poll_interval,
            terminate_grace=terminate_grace,
        )
        os.replace(tmp_path, dst_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    return str(dst_path)


def _run_ffmpeg(
    cmd: list[str],
    *,
    src_path: Path,
    cancel_check: Callable[[], bool] | None,
    poll_interval: float,
    terminate_grace: float,
) -> None:
    """Run ffmpeg in a subprocess, supporting cooperative cancellation.

    Uses :class:`subprocess.Popen` (not ``subprocess.run``) so the parent
    can ``terminate()`` the ffmpeg child when ``cancel_check`` returns
    True. ``stdin`` is set to ``DEVNULL`` so a backgrounded app does not
    get its ffmpeg children frozen by SIGTTIN when they try to read the
    inherited terminal.
    """
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        while True:
            try:
                stdout, stderr = proc.communicate(timeout=poll_interval)
                break
            except subprocess.TimeoutExpired:
                if cancel_check is not None and cancel_check():
                    _terminate_ffmpeg(proc, grace=terminate_grace)
                    raise MetadataWriteCancelledError(
                        f"export cancelled for {src_path}"
                    ) from None
    except BaseException:
        # Make sure the child is reaped even on Ctrl-C / unexpected errors.
        if proc.poll() is None:
            _terminate_ffmpeg(proc, grace=terminate_grace)
        raise

    if proc.returncode != 0:
        raise MetadataWriteError(
            f"ffmpeg failed (rc={proc.returncode}) for {src_path}: "
            f"{(stderr or '').strip() or (stdout or '').strip()}"
        )


def _terminate_ffmpeg(proc: subprocess.Popen, *, grace: float) -> None:
    """Best-effort terminate -> kill of an ffmpeg child."""
    try:
        proc.terminate()
    except OSError:
        return
    try:
        proc.communicate(timeout=grace)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            return
        try:
            proc.communicate(timeout=grace)
        except subprocess.TimeoutExpired:
            pass


def read_metadata(
    src: str | os.PathLike[str], *, ffprobe: str | None = None
) -> dict[str, str]:
    """Best-effort read of tags from ``src`` using ffprobe."""
    try:
        bin_path = _resolve_ffprobe(ffprobe)
    except FfmpegNotFoundError:
        return {}
    try:
        out = subprocess.run(
            [bin_path, "-v", "error", "-show_format", "-of", "json", str(src)],
            capture_output=True, text=True, check=True, timeout=20,
        )
        data = json.loads(out.stdout or "{}")
        tags = data.get("format", {}).get("tags", {})
        return {str(k).lower(): str(v) for k, v in tags.items()}
    except (subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return {}
