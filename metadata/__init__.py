"""Audio metadata I/O backed by ffmpeg."""

from .ffmpeg_writer import (
    COVER_IMAGE_SUFFIXES,
    FfmpegNotFoundError,
    Metadata,
    MetadataWriteCancelledError,
    MetadataWriteError,
    format_duration,
    probe_duration_seconds,
    read_metadata,
    resolve_cover_path,
    write_metadata,
)

__all__ = [
    "COVER_IMAGE_SUFFIXES",
    "FfmpegNotFoundError",
    "Metadata",
    "MetadataWriteCancelledError",
    "MetadataWriteError",
    "format_duration",
    "probe_duration_seconds",
    "read_metadata",
    "resolve_cover_path",
    "write_metadata",
]
