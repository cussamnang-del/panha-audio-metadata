"""Tests for the batch worker."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import QThreadPool  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from panha.metadata import FfmpegNotFoundError, Metadata  # noqa: E402
from panha.widgets.worker import BatchItem, BatchWorker, schedule_probe  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _drain_signals(worker: BatchWorker):
    """Collect emissions from a worker run synchronously on the test thread.

    When ``max_threads > 1`` the BatchWorker emits from pool threads, so
    we drain Qt's queued events after run() returns to make sure all
    cross-thread signals are delivered before assertions.
    """
    done: list[tuple[int, str]] = []
    failed: list[tuple[int, str]] = []
    progress: list[tuple[int, int]] = []
    finished = [False]
    worker.item_done.connect(lambda i, s: done.append((i, s)))
    worker.item_failed.connect(lambda i, m: failed.append((i, m)))
    worker.progress.connect(lambda i, t: progress.append((i, t)))
    worker.finished.connect(lambda: finished.__setitem__(0, True))
    worker.run()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    return done, failed, progress, finished[0]


def test_worker_reports_ffmpeg_not_found_instead_of_crashing(
    qapp, monkeypatch, tmp_path: Path
):
    """Regression: a missing ffmpeg binary raises FfmpegNotFoundError,
    which subclasses RuntimeError. The worker thread must surface that
    as an item failure rather than dying silently.
    """
    src = tmp_path / "in.mp3"
    src.write_bytes(b"not really an mp3")
    dst = tmp_path / "out.mp3"

    def boom(*_args, **_kwargs):
        raise FfmpegNotFoundError("ffmpeg not installed")

    monkeypatch.setattr("panha.metadata.ffmpeg_writer._resolve_ffmpeg", boom)

    item = BatchItem(source=str(src), target=str(dst), metadata=Metadata(title="x"))
    worker = BatchWorker([item])
    done, failed, progress, finished = _drain_signals(worker)

    assert finished is True
    assert done == []
    assert len(failed) == 1
    assert failed[0][0] == 0
    assert "ffmpeg" in failed[0][1].lower()
    assert progress == [(1, 1)]


def test_worker_cancels_remaining_items(qapp, tmp_path: Path):
    src = tmp_path / "in.mp3"
    src.write_bytes(b"not really an mp3")
    items = [
        BatchItem(source=str(src), target=str(tmp_path / f"o{i}.mp3"),
                  metadata=Metadata())
        for i in range(3)
    ]
    worker = BatchWorker(items)
    worker.cancel()
    done, failed, progress, finished = _drain_signals(worker)

    assert finished is True
    assert failed == []
    assert [s for _, s in done] == ["Cancelled", "Cancelled", "Cancelled"]
    # Progress must still tick to total for cancelled items so the bar
    # doesn't get stuck partway.
    assert progress == [(1, 3), (2, 3), (3, 3)]


def test_schedule_probe_runs_off_thread_and_emits_result(qapp, tmp_path: Path):
    """schedule_probe must defer the probe to a worker and report back
    via signal so the UI thread doesn't block on ffprobe."""
    pool = QThreadPool()
    pool.setMaxThreadCount(2)

    received: list[tuple[str, float]] = []

    def fake_probe(path: str) -> float:
        return 1.5 if path.endswith("a.mp3") else 2.25

    a = str(tmp_path / "a.mp3")
    b = str(tmp_path / "b.mp3")
    schedule_probe(a, lambda p, d: received.append((p, d)), pool=pool, probe_fn=fake_probe)
    schedule_probe(b, lambda p, d: received.append((p, d)), pool=pool, probe_fn=fake_probe)

    # Wait for both tasks to finish, draining the Qt event queue so
    # queued signal connections deliver.
    pool.waitForDone(5000)
    qapp.processEvents()

    assert sorted(received) == [(a, 1.5), (b, 2.25)]


def test_schedule_probe_reports_zero_when_probe_raises(qapp, tmp_path: Path):
    """A probe failure must surface as duration=0.0, never propagate."""
    pool = QThreadPool()
    pool.setMaxThreadCount(1)

    received: list[tuple[str, float]] = []

    def boom(_path: str) -> float:
        raise RuntimeError("ffprobe explosion")

    path = str(tmp_path / "x.mp3")
    schedule_probe(path, lambda p, d: received.append((p, d)), pool=pool, probe_fn=boom)
    pool.waitForDone(5000)
    qapp.processEvents()

    assert received == [(path, 0.0)]


def test_worker_emits_cancelled_when_write_metadata_raises_cancelled(
    qapp, monkeypatch, tmp_path: Path
):
    """When write_metadata raises MetadataWriteCancelledError mid-batch, the
    worker must surface it as a 'Cancelled' done event (not 'Error: ...').
    """
    from panha.metadata import MetadataWriteCancelledError

    src = tmp_path / "in.mp3"
    src.write_bytes(b"not really an mp3")

    def boom(*_args, **kwargs):
        # Sanity check: BatchWorker must pass cancel_check through.
        assert "cancel_check" in kwargs
        raise MetadataWriteCancelledError("cancelled mid-export")

    monkeypatch.setattr("panha.widgets.worker.write_metadata", boom)

    item = BatchItem(
        source=str(src), target=str(tmp_path / "out.mp3"),
        metadata=Metadata(title="x"),
    )
    worker = BatchWorker([item])
    done, failed, progress, finished = _drain_signals(worker)

    assert finished is True
    assert failed == []
    assert done == [(0, "Cancelled")]
    assert progress == [(1, 1)]


def test_build_items_passes_export_settings_through(tmp_path: Path):
    """build_items must read the ExportSettings dialog state and stamp
    each BatchItem with sample_rate/LUFS/codec overrides and the
    target suffix dictated by the chosen format.
    """
    from panha.dialogs.export_settings_dialog import ExportSettings
    from panha.dialogs.file_info_dialog import (
        FileInformationState,
        TracklistOptions,
    )
    from panha.widgets.worker import build_items

    src = tmp_path / "01. Song.mp3"
    src.write_bytes(b"")
    state = FileInformationState(
        metadata=Metadata(artist="A"),
        tracklist=TracklistOptions(uppercase=False, remove_track_number=False),
    )
    export = ExportSettings(
        format="WAV",
        sample_rate="48000 Hz",
        bit_depth="24-bit",
        max_threads=2,
        lufs_target="-14 LUFS",
    )

    items = build_items([str(src)], str(tmp_path / "out"), state, export=export)
    assert len(items) == 1
    item = items[0]

    # Output suffix flips to .wav because the user asked for WAV format.
    assert Path(item.target).suffix == ".wav"
    # The new writer kwargs are populated from the dialog values.
    assert item.sample_rate_hz == 48000
    assert item.lufs_target_lufs == -14.0
    assert item.codec_args_override == ["-c:a", "pcm_s24le"]
    # Format change forces re-encode even though mastering is default.
    assert item.force_re_encode is True


def test_build_items_preserves_source_format_by_default(tmp_path: Path):
    """The default ExportSettings (Format='Same as source', no LUFS,
    no sample-rate override) must not change behavior vs. pre-wiring:
    output suffix matches the source and no force_re_encode."""
    from panha.dialogs.export_settings_dialog import ExportSettings
    from panha.dialogs.file_info_dialog import FileInformationState
    from panha.widgets.worker import build_items

    src = tmp_path / "song.flac"
    src.write_bytes(b"")
    state = FileInformationState(metadata=Metadata(artist="A"))

    items = build_items(
        [str(src)], str(tmp_path / "out"), state, export=ExportSettings()
    )
    item = items[0]
    assert Path(item.target).suffix == ".flac"
    assert item.sample_rate_hz is None
    assert item.lufs_target_lufs is None
    assert item.codec_args_override is None
    assert item.force_re_encode is False


def test_worker_parallel_runs_items_concurrently(qapp, monkeypatch, tmp_path: Path):
    """With max_threads > 1 the batch worker must process items
    concurrently. We assert this by measuring how many items overlap in
    a write_metadata stub that records its enter/exit times."""
    import threading
    import time

    src = tmp_path / "in.mp3"
    src.write_bytes(b"")
    items = [
        BatchItem(
            source=str(src), target=str(tmp_path / f"out{i}.mp3"),
            metadata=Metadata(title=f"x{i}"),
        )
        for i in range(4)
    ]

    in_flight = 0
    max_overlap = 0
    lock = threading.Lock()

    def slow_write(*_args, **_kwargs):
        nonlocal in_flight, max_overlap
        with lock:
            in_flight += 1
            max_overlap = max(max_overlap, in_flight)
        time.sleep(0.2)
        with lock:
            in_flight -= 1

    monkeypatch.setattr("panha.widgets.worker.write_metadata", slow_write)

    worker = BatchWorker(items, max_threads=4)
    done, failed, progress, finished = _drain_signals(worker)

    assert finished is True
    assert failed == []
    assert sorted(done) == [(i, "Done") for i in range(4)]
    # At least two items must have been processed simultaneously; the
    # exact peak depends on scheduler timing but must be > 1 to prove
    # the executor isn't running sequentially.
    assert max_overlap >= 2, f"expected overlap > 1, saw {max_overlap}"
    # Progress should still reach total even if completion order != input order.
    assert progress[-1] == (4, 4)


def test_worker_sequential_when_max_threads_is_one(qapp, monkeypatch, tmp_path: Path):
    """max_threads=1 must take the simple sequential codepath, preserving
    the historical (index, total) progress order."""
    src = tmp_path / "in.mp3"
    src.write_bytes(b"")
    items = [
        BatchItem(
            source=str(src), target=str(tmp_path / f"out{i}.mp3"),
            metadata=Metadata(title=f"x{i}"),
        )
        for i in range(3)
    ]
    monkeypatch.setattr(
        "panha.widgets.worker.write_metadata", lambda *a, **k: None
    )

    worker = BatchWorker(items, max_threads=1)
    done, failed, progress, finished = _drain_signals(worker)

    assert finished is True
    assert failed == []
    assert done == [(0, "Done"), (1, "Done"), (2, "Done")]
    assert progress == [(1, 3), (2, 3), (3, 3)]


def test_build_items_threads_cover_max_size(tmp_path: Path):
    """Regression: the Cover Size / Height spinboxes were silently ignored.
    build_items must forward state.tracklist.cover_size/cover_height to
    each BatchItem so write_metadata can scale the embedded cover.
    """
    from panha.dialogs.export_settings_dialog import ExportSettings
    from panha.dialogs.file_info_dialog import (
        FileInformationState,
        TracklistOptions,
    )
    from panha.widgets.worker import build_items

    src = tmp_path / "song.mp3"
    src.write_bytes(b"")
    state = FileInformationState(
        metadata=Metadata(artist="A"),
        tracklist=TracklistOptions(cover_size=800, cover_height=600),
    )
    items = build_items(
        [str(src)], str(tmp_path / "out"), state, export=ExportSettings()
    )
    assert items[0].cover_max_size == (800, 600)


def test_build_items_disables_cover_resize_when_size_zero(tmp_path: Path):
    from panha.dialogs.export_settings_dialog import ExportSettings
    from panha.dialogs.file_info_dialog import (
        FileInformationState,
        TracklistOptions,
    )
    from panha.widgets.worker import build_items

    src = tmp_path / "song.mp3"
    src.write_bytes(b"")
    state = FileInformationState(
        metadata=Metadata(),
        tracklist=TracklistOptions(cover_size=0, cover_height=0),
    )
    items = build_items(
        [str(src)], str(tmp_path / "out"), state, export=ExportSettings()
    )
    assert items[0].cover_max_size is None
