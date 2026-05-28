"""Deep audio-signal analysis for AI music detection.

Uses the same library stack as X-MIXM_1.2 (PyAV + NumPy + SciPy +
ONNXRuntime) to decode audio and extract low-level spectral features that
complement the fast metadata-fingerprint heuristic in :mod:`panha.detector`.

This module is *optional*: if the required libraries are not importable it
returns graceful error dicts so callers can degrade to metadata-only mode
without crashing.

Detection approach
------------------
Neural-codec-generated audio (Suno / Udio / etc.) carries characteristic
signal fingerprints **even after metadata has been stripped**:

1. **Ultra-uniform loudness** — AI platforms loudness-normalise to a tight
   LUFS target, suppressing natural dynamic variation.  The per-frame RMS
   coefficient-of-variation (CV) falls well below that of organic recordings.

2. **Neural-codec spectral footprint** — Encoders like EnCodec / DAC
   (used by Suno) quantise the latent space, leaving a characteristic
   spectral-flatness signature and a sharp energy roll-off just below the
   Nyquist frequency.

3. **Anomalous ultra-HF energy** — A complete absence of energy above
   16 kHz on a 44.1 kHz file signals that a codec hard-clipped the
   bandwidth; genuine recordings typically retain some content up to ~20 kHz.

4. **Elevated zero-crossing rate** — Codec quantisation noise slightly
   inflates the ZCR compared with natural audio at similar loudness.

The ``score_audio_features`` function maps these signals to a 0-100 AI
likelihood percentage that the detector combines with its metadata score.
"""

from __future__ import annotations

from pathlib import Path

# Maximum audio samples analysed per file (reduces latency on long tracks).
# 20 s × 48 000 Hz = 960 000 samples — adequate for reliable features.
_MAX_SAMPLES: int = 48_000 * 20


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def extract_audio_features(
    path: str | Path,
    *,
    max_samples: int = _MAX_SAMPLES,
) -> dict[str, float | str]:
    """Decode *path* with PyAV and return a feature dict.

    All values are ``float`` except ``"error"`` (str).  An ``"error"``
    key is set whenever decoding or analysis fails; callers should check
    for it before reading other keys.

    Parameters
    ----------
    path:
        Audio file to analyse (any format supported by FFmpeg / PyAV).
    max_samples:
        Hard cap on the number of decoded mono samples so long files
        don't create huge allocations.  Default is 20 s at 48 kHz.
    """
    try:
        import av  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
        from scipy import signal  # noqa: PLC0415
    except ImportError as exc:
        return {"error": f"optional library not available: {exc}"}

    p = Path(path)
    if not p.exists():
        return {"error": f"file not found: {p}"}

    # --- decode -----------------------------------------------------------
    try:
        container = av.open(str(p))
        audio_stream = next(
            (s for s in container.streams if s.type == "audio"), None
        )
        if audio_stream is None:
            container.close()
            return {"error": "no audio stream found"}

        sample_rate: int = int(audio_stream.sample_rate or 44100)
        chunks: list = []
        total: int = 0

        for frame in container.decode(audio_stream):
            arr = frame.to_ndarray()          # (channels, samples) or (samples,)
            if arr.ndim > 1:
                arr = arr.mean(axis=0)         # mix to mono
            arr = arr.astype("float32")
            chunks.append(arr)
            total += len(arr)
            if total >= max_samples:
                break

        container.close()

        if not chunks:
            return {"error": "no audio data could be decoded"}

        audio = _np_module().concatenate(chunks)[:max_samples]

        peak = float(_np_module().abs(audio).max())
        if peak < 1e-9:
            return {"error": "audio is silent"}

        audio = audio / peak                   # normalise to [-1, 1]

    except Exception as exc:  # noqa: BLE001
        return {"error": f"decode error: {exc}"}

    import numpy as np  # noqa: PLC0415 — already confirmed importable above
    from scipy import signal  # noqa: PLC0415

    features: dict[str, float | str] = {
        "sample_rate": float(sample_rate),
        "duration_s": float(len(audio) / sample_rate),
    }

    # --- per-frame RMS (100 ms frames) ------------------------------------
    frame_len = max(1, int(sample_rate * 0.1))
    n_frames = len(audio) // frame_len
    if n_frames >= 4:
        mat = audio[: n_frames * frame_len].reshape(n_frames, frame_len)
        rms_frames = np.sqrt((mat ** 2).mean(axis=1))
        rms_mean = float(rms_frames.mean())
        rms_std = float(rms_frames.std())
        features["rms_mean"] = rms_mean
        # Coefficient of variation: std / mean.  Low = uniform loudness.
        features["rms_cv"] = rms_std / (rms_mean + 1e-10)
        # Peak-to-average ratio across frames
        features["rms_par"] = float(rms_frames.max() / (rms_mean + 1e-10))

    # --- spectral analysis ------------------------------------------------
    nperseg = min(4096, max(64, len(audio) // 8))
    if nperseg >= 64:
        freqs, _t, Sxx = signal.spectrogram(
            audio.astype("float64"),
            fs=sample_rate,
            nperseg=nperseg,
            noverlap=nperseg // 2,
        )
        power = Sxx.mean(axis=1) + 1e-30      # mean power per frequency bin

        # Spectral flatness (Wiener entropy): geometric/arithmetic mean ratio.
        # 0 = pure tone; 1 = white noise.
        geom_mean = float(np.exp(np.log(power).mean()))
        arith_mean = float(power.mean())
        features["spectral_flatness"] = geom_mean / arith_mean

        # Spectral centroid (power-weighted mean frequency).
        total_power = float(power.sum())
        features["spectral_centroid"] = float(
            (freqs * power).sum() / (total_power + 1e-30)
        )

        # High-frequency ratio (>8 kHz).
        hf_mask = freqs >= 8_000
        features["hf_ratio"] = (
            float(power[hf_mask].sum() / total_power) if hf_mask.any() else 0.0
        )

        # Ultra-HF ratio (>16 kHz) — neural-codec bandwidth cap signature.
        uhf_mask = freqs >= 16_000
        features["uhf_ratio"] = (
            float(power[uhf_mask].sum() / total_power) if uhf_mask.any() else 0.0
        )

        # Very-high-band ratio (>18 kHz)
        vhf_mask = freqs >= 18_000
        features["vhf_ratio"] = (
            float(power[vhf_mask].sum() / total_power) if vhf_mask.any() else 0.0
        )

    # --- zero-crossing rate -----------------------------------------------
    features["zcr"] = float(np.mean(np.abs(np.diff(np.signbit(audio).astype("int8")))))

    # --- crest factor (peak / RMS of full clip) ---------------------------
    clip_rms = float(np.sqrt(np.mean(audio ** 2)))
    features["crest_factor"] = 1.0 / (clip_rms + 1e-10)   # higher = more dynamic

    return features


def _np_module():
    """Lazy numpy import (avoids a hard top-level dependency)."""
    import numpy as np  # noqa: PLC0415
    return np


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_audio_features(
    features: dict[str, float | str],
) -> tuple[int, str]:
    """Map extracted features to an AI likelihood score + reason string.

    Returns
    -------
    score : int
        0 (strongly human) to 100 (strongly AI).  Returns **-1** if the
        analysis could not run (``"error"`` key present in *features*).
    reason : str
        Human-readable explanation surfaced in the detector tooltip.
    """
    if "error" in features:
        return -1, f"Audio scan unavailable — {features['error']}"

    score = 0
    hits: list[str] = []

    # 1. Loudness uniformity -----------------------------------------------
    rms_cv = float(features.get("rms_cv", 1.0))
    if rms_cv < 0.10:
        score += 30
        hits.append(f"ultra-uniform loudness (CV={rms_cv:.3f})")
    elif rms_cv < 0.18:
        score += 18
        hits.append(f"heavily compressed dynamics (CV={rms_cv:.3f})")
    elif rms_cv < 0.28:
        score += 8
        hits.append(f"moderately compressed (CV={rms_cv:.3f})")

    # 2. Ultra-HF energy / bandwidth roll-off --------------------------------
    sr = float(features.get("sample_rate", 44100))
    uhf = float(features.get("uhf_ratio", 0.0))
    vhf = float(features.get("vhf_ratio", 0.0))
    if sr >= 44100:
        if uhf < 5e-4:
            # Hard bandwidth cap below 16 kHz — clear neural-codec signature.
            score += 25
            hits.append("bandwidth cap <16 kHz (neural-codec fingerprint)")
        elif vhf < 1e-4 and uhf < 0.005:
            score += 15
            hits.append("strong HF roll-off (codec artifact)")
        elif uhf < 0.01:
            score += 8
            hits.append(f"reduced ultra-HF energy (uhf={uhf:.4f})")

    # 3. Spectral flatness --------------------------------------------------
    flatness = float(features.get("spectral_flatness", 0.0))
    if flatness > 0.30:
        score += 15
        hits.append(f"high spectral flatness ({flatness:.3f})")
    elif flatness > 0.18:
        score += 7
        hits.append(f"elevated spectral flatness ({flatness:.3f})")

    # 4. Crest factor -------------------------------------------------------
    # AI-generated audio tends to be loud-normalised → low crest factor
    # (compressed → peak ≈ RMS).  Natural orchestral music: crest > 12 dB.
    crest = float(features.get("crest_factor", 10.0))
    if crest < 4.0:
        score += 10
        hits.append(f"very low crest factor ({crest:.1f})")
    elif crest < 7.0:
        score += 4
        hits.append(f"low crest factor ({crest:.1f})")

    # 5. Zero-crossing rate ------------------------------------------------
    zcr = float(features.get("zcr", 0.0))
    if zcr > 0.38:
        score += 8
        hits.append(f"elevated ZCR ({zcr:.3f})")
    elif zcr > 0.28:
        score += 3

    score = min(100, score)
    reason_body = "; ".join(hits) if hits else "no strong audio indicators found"
    reason = f"Deep audio scan: {reason_body}"
    return score, reason
