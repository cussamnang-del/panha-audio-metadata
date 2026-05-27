import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@pytest.fixture(scope="session")
def ffmpeg_required() -> None:
    if not _ffmpeg_available():
        pytest.skip("ffmpeg/ffprobe not available on PATH")


@pytest.fixture
def sample_mp3(tmp_path: Path, ffmpeg_required) -> Path:
    """Synthesize a 1-second 440Hz MP3 file using ffmpeg."""
    out = tmp_path / "sample.mp3"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-codec:a", "libmp3lame", "-b:a", "64k", str(out),
        ],
        check=True,
    )
    assert out.exists() and out.stat().st_size > 0
    return out


@pytest.fixture
def sample_cover(tmp_path: Path, ffmpeg_required) -> Path:
    """Generate a small JPEG cover via ffmpeg."""
    out = tmp_path / "cover.jpg"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1",
            "-frames:v", "1", str(out),
        ],
        check=True,
    )
    assert out.exists() and out.stat().st_size > 0
    return out


@pytest.fixture(autouse=True)
def _qt_offscreen(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
