"""Mastering chain — maps the X-MIXM slider grid to ffmpeg audio filters.

Each slider produces an integer 0..99. A value of 0 means the slider has
no effect; higher values intensify the corresponding filter. The
``MasteringSettings.bypass`` flag disables the entire chain regardless of
individual slider values, mirroring the BYPASS toggle in the transport
bar.

The slider layout below matches the order shown in the X-MIXM reference
UI, grouped by category badge:

    EQ:    Bass  Deep  Mid  Clear  Treble  Pres
    DYN:   Comp  Limit  Sat
    FX:    Verb  Echo
    OUT:   Width  Gain

The filter expressions are intentionally conservative so a slider at the
top of its range still produces a useful, non-clipping result on a real
mix.
"""

from __future__ import annotations

import dataclasses

SLIDER_MIN = 0
SLIDER_MAX = 99

# (attribute name, display label, center frequency in Hz)
EQ_BANDS: tuple[tuple[str, str, int], ...] = (
    ("bass", "Bass", 80),
    ("deep", "Deep", 180),
    ("mid", "Mid", 500),
    ("clear", "Clear", 1500),
    ("treble", "Treble", 5000),
    ("pres", "Pres", 10000),
)

EQ_NAMES: tuple[str, ...] = tuple(name for name, _label, _hz in EQ_BANDS)
DYN_NAMES: tuple[str, ...] = ("comp", "limit", "sat")
FX_NAMES: tuple[str, ...] = ("verb", "echo")
OUT_NAMES: tuple[str, ...] = ("width", "gain")
ALL_SLIDERS: tuple[str, ...] = EQ_NAMES + DYN_NAMES + FX_NAMES + OUT_NAMES


@dataclasses.dataclass
class MasteringSettings:
    """Audio mastering chain configuration.

    All sliders default to 0 (no effect). ``bypass`` is independent of
    slider state and short-circuits the chain when set.
    """

    bypass: bool = False
    # EQ
    bass: int = 0
    deep: int = 0
    mid: int = 0
    clear: int = 0
    treble: int = 0
    pres: int = 0
    # Dynamics
    comp: int = 0
    limit: int = 0
    sat: int = 0
    # FX
    verb: int = 0
    echo: int = 0
    # Output
    width: int = 0
    gain: int = 0

    def is_active(self) -> bool:
        """True when at least one filter would alter the signal."""
        if self.bypass:
            return False
        return any(getattr(self, n) for n in ALL_SLIDERS)

    def to_filter_chain(self) -> str:
        """Return a comma-separated ffmpeg ``-af`` filter chain.

        Empty string when the chain is bypassed or all sliders are 0.
        """
        if not self.is_active():
            return ""

        filters: list[str] = []

        # --- EQ (six fixed peaking bands, 0..+12 dB) -----------------
        for name, _label, hz in EQ_BANDS:
            value = getattr(self, name)
            if value > 0:
                gain_db = _scale(value, 0.0, 12.0)
                filters.append(
                    f"equalizer=f={hz}:width_type=q:w=1:g={gain_db:.2f}"
                )

        # --- Compressor (ratio 1..8, threshold -10..-30 dB) ----------
        if self.comp > 0:
            ratio = _scale(self.comp, 1.0, 8.0)
            threshold_db = _scale(self.comp, -10.0, -30.0)
            t_lin = 10 ** (threshold_db / 20.0)
            filters.append(
                f"acompressor=threshold={t_lin:.4f}:ratio={ratio:.2f}"
                ":attack=20:release=250:makeup=2"
            )

        # --- Limiter (level_in fixed, limit 1.0..0.5) ---------------
        if self.limit > 0:
            limit = _scale(self.limit, 1.0, 0.5)
            filters.append(
                f"alimiter=level_in=1:limit={limit:.3f}:attack=5:release=50"
            )

        # --- Saturation / exciter -----------------------------------
        if self.sat > 0:
            amount = _scale(self.sat, 0.0, 1.0)
            drive = _scale(self.sat, 1.0, 8.5)
            filters.append(
                f"aexciter=amount={amount:.2f}:drive={drive:.2f}"
                ":blend=0:freq=7500"
            )

        # --- Reverb-ish (multi-tap aecho) ---------------------------
        if self.verb > 0:
            wet = _scale(self.verb, 0.0, 1.0)
            in_gain = 1.0 - wet * 0.3
            out_gain = wet
            filters.append(
                f"aecho={in_gain:.2f}:{out_gain:.2f}"
                ":60|120|180|240:0.4|0.3|0.2|0.1"
            )

        # --- Single-tap echo ----------------------------------------
        if self.echo > 0:
            decay = _scale(self.echo, 0.2, 0.7)
            filters.append(f"aecho=0.8:0.6:500:{decay:.2f}")

        # --- Stereo width (extrastereo m=1..2.5) --------------------
        if self.width > 0:
            m = _scale(self.width, 1.0, 2.5)
            filters.append(f"extrastereo=m={m:.2f}")

        # --- Output gain (0..+12 dB) --------------------------------
        if self.gain > 0:
            db = _scale(self.gain, 0.0, 12.0)
            filters.append(f"volume={db:.2f}dB")

        return ",".join(filters)


def _scale(value: int, lo: float, hi: float) -> float:
    """Linearly map ``value`` from ``[0, SLIDER_MAX]`` to ``[lo, hi]``.

    Out-of-range inputs are clamped.
    """
    v = max(SLIDER_MIN, min(SLIDER_MAX, int(value)))
    return lo + (hi - lo) * v / SLIDER_MAX


# Codec table — when mastering is active we must re-encode rather than
# stream-copy. Keys are lower-case file suffixes (with leading dot).
RE_ENCODE_CODECS: dict[str, list[str]] = {
    ".mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    ".m4a": ["-c:a", "aac", "-b:a", "192k"],
    ".aac": ["-c:a", "aac", "-b:a", "192k"],
    ".ogg": ["-c:a", "libvorbis", "-q:a", "5"],
    ".flac": ["-c:a", "flac"],
    ".wav": ["-c:a", "pcm_s16le"],
}


def codec_args_for(suffix: str) -> list[str]:
    """Return ``-c:a …`` args for the given output suffix.

    Falls back to libmp3lame when the suffix is unknown so the writer
    never silently produces an empty audio stream.
    """
    return RE_ENCODE_CODECS.get(suffix.lower(), RE_ENCODE_CODECS[".mp3"])
