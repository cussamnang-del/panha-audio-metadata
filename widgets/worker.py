"""Background worker that writes metadata to a batch of files."""

from __future__ import annotations

import concurrent.futures
import dataclasses
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, QThread, QThreadPool, pyqtSignal

from ..dialogs.export_settings_dialog import ExportSettings
from ..dialogs.file_info_dialog import FileInformationState
from ..mastering import MasteringSettings
from ..metadata import (
    FfmpegNotFoundError,
    Metadata,
    MetadataWriteCancelledError,
    MetadataWriteError,
    probe_duration_seconds,
    write_metadata,
)


@dataclasses.dataclass
class BatchItem:
    source: str
    target: str
    metadata: Metadata
    mastering: MasteringSettings = dataclasses.field(default_factory=MasteringSettings)
    sample_rate_hz: int | None = None
    lufs_target_lufs: float | None = None
    codec_args_override: list[str] | None = None
    force_re_encode: bool = False
    cover_max_size: tuple[int, int] | None = None


class BatchWorker(QObject):
    progress = pyqtSignal(int, int)  # completed, total
    item_done = pyqtSignal(int, str)  # index, status text
    item_failed = pyqtSignal(int, str)  # index, error message
    finished = pyqtSignal()

    def __init__(
        self,
        items: list[BatchItem],
        parent: QObject | None = None,
        *,
        max_threads: int = 1,
    ) -> None:
        super().__init__(parent)
        self._items = items
        self._cancel = False
        self._max_threads = max(1, int(max_threads))

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        total = len(self._items)
        if self._max_threads <= 1 or total <= 1:
            for idx, item in enumerate(self._items):
                self._process_one(idx, item)
                self.progress.emit(idx + 1, total)
        else:
            self._run_parallel(total)
        self.finished.emit()

    def _run_parallel(self, total: int) -> None:
        # PyQt's pyqtSignal.emit() is thread-safe across QObjects, so we
        # can dispatch into a pool and let each worker thread emit
        # item_done / item_failed directly. Progress is bumped by the
        # main worker thread once each future returns so the count
        # stays monotonic.
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self._max_threads
        ) as pool:
            futures: dict[concurrent.futures.Future[None], int] = {}
            for idx, item in enumerate(self._items):
                if self._cancel:
                    self.item_done.emit(idx, "Cancelled")
                    completed += 1
                    self.progress.emit(completed, total)
                    continue
                futures[pool.submit(self._process_one, idx, item)] = idx
            for future in concurrent.futures.as_completed(futures):
                # _process_one already emitted item_done / item_failed.
                # Re-raise unexpected exceptions so they surface in tests
                # instead of being silently swallowed by the executor.
                future.result()
                completed += 1
                self.progress.emit(completed, total)

    def _process_one(self, idx: int, item: BatchItem) -> None:
        if self._cancel:
            self.item_done.emit(idx, "Cancelled")
            return
        try:
            Path(item.target).parent.mkdir(parents=True, exist_ok=True)
            write_metadata(
                item.source,
                item.target,
                item.metadata,
                mastering=item.mastering,
                cancel_check=lambda: self._cancel,
                sample_rate_hz=item.sample_rate_hz,
                lufs_target_lufs=item.lufs_target_lufs,
                codec_args_override=item.codec_args_override,
                force_re_encode=item.force_re_encode,
                cover_max_size=item.cover_max_size,
            )
            self.item_done.emit(idx, "Done")
        except MetadataWriteCancelledError:
            # Cancellation arrived mid-ffmpeg; the child was already
            # terminated by write_metadata.
            self.item_done.emit(idx, "Cancelled")
        except (
            FfmpegNotFoundError,
            MetadataWriteError,
            OSError,
            FileNotFoundError,
        ) as exc:
            self.item_failed.emit(idx, str(exc))


def build_items(
    sources: list[str],
    output_dir: str,
    state: FileInformationState,
    *,
    export: ExportSettings | None = None,
) -> list[BatchItem]:
    """Combine a source list + UI state into a list of BatchItem.

    ``export`` (the modal ``ExportSettings`` dialog state) drives output
    suffix, codec overrides, sample-rate, and LUFS target. Items are
    re-encoded automatically when any of these differs from the
    pure-tagging defaults.
    """
    items: list[BatchItem] = []
    out_root = Path(output_dir).expanduser().resolve()
    base = dataclasses.replace(state.metadata)
    mastering = dataclasses.replace(state.mastering)

    sample_rate_hz = export.parsed_sample_rate_hz() if export is not None else None
    lufs_target_lufs = export.parsed_lufs_target() if export is not None else None
    codec_args_override = (
        export.codec_args_override() if export is not None else None
    )
    # Cover-art resize honours the (width, height) configured in the
    # File Information dialog. Zero / negative values disable resizing.
    cover_w = state.tracklist.cover_size
    cover_h = state.tracklist.cover_height
    cover_max_size: tuple[int, int] | None = (
        (cover_w, cover_h) if cover_w > 0 and cover_h > 0 else None
    )

    for src in sources:
        src_path = Path(src)
        source_suffix = src_path.suffix or ".mp3"
        target_suffix = (
            export.output_suffix_for(source_suffix)
            if export is not None
            else source_suffix
        )
        stem = src_path.stem
        if state.tracklist.remove_track_number:
            cleaned = stem.lstrip("0123456789. _-")
            if cleaned:
                stem = cleaned
        if state.tracklist.uppercase:
            stem = stem.upper()
        target_name = f"{stem}{target_suffix}"
        target = out_root / target_name
        meta = dataclasses.replace(base)
        if not meta.title:
            meta.title = stem
        # A format change alone is not enough to flag re-encode: a WAV
        # input written out as WAV with the same default codec args is
        # still safely stream-copyable. We *do* flag re-encode when the
        # user-picked codec args differ from the source-format defaults
        # (write_metadata also derives this from codec_args_override and
        # sample_rate_hz, but being explicit here keeps build_items the
        # single source of truth).
        force_re_encode = (
            codec_args_override is not None
            or sample_rate_hz is not None
            or lufs_target_lufs is not None
            or target_suffix.lower() != source_suffix.lower()
        )
        items.append(BatchItem(
            source=str(src_path),
            target=str(target),
            metadata=meta,
            mastering=mastering,
            sample_rate_hz=sample_rate_hz,
            lufs_target_lufs=lufs_target_lufs,
            codec_args_override=(
                list(codec_args_override) if codec_args_override else None
            ),
            force_re_encode=force_re_encode,
            cover_max_size=cover_max_size,
        ))
    return items


class _ProbeSignals(QObject):
    """Signal carrier for :class:`ProbeTask` (QRunnable can't emit directly)."""

    finished = pyqtSignal(str, float)  # path, duration_seconds


class ProbeTask(QRunnable):
    """Probe a single file's duration on the global thread pool.

    Use :attr:`signals.finished` to receive the result back on the
    Qt thread that connected the slot.
    """

    def __init__(
        self,
        path: str,
        *,
        probe_fn: Callable[[str], float] = probe_duration_seconds,
    ) -> None:
        super().__init__()
        self._path = path
        self._probe_fn = probe_fn
        self.signals = _ProbeSignals()
        self.setAutoDelete(True)

    def run(self) -> None:  # pragma: no cover - exercised via signals
        try:
            duration = float(self._probe_fn(self._path))
        except Exception:
            duration = 0.0
        self.signals.finished.emit(self._path, duration)


def schedule_probe(
    path: str,
    on_finished: Callable[[str, float], None],
    *,
    pool: QThreadPool | None = None,
    probe_fn: Callable[[str], float] = probe_duration_seconds,
) -> ProbeTask:
    """Submit ``path`` to a background pool; ``on_finished`` runs on the caller's thread."""
    task = ProbeTask(path, probe_fn=probe_fn)
    task.signals.finished.connect(on_finished)
    (pool or QThreadPool.globalInstance()).start(task)
    return task


def start_worker(
    items: list[BatchItem], *, max_threads: int = 1
) -> tuple[BatchWorker, QThread]:
    """Create + start a worker thread; caller is responsible for cleanup."""
    thread = QThread()
    worker = BatchWorker(items, max_threads=max_threads)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return worker, thread
