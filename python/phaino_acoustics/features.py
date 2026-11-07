"""Model-free instantaneous-frequency (IF) front end for E0.

This module is the *measurement* stage, deliberately not the point of E0: it
turns a real waveform into an estimated frequency-vs-time track without using
the physical Doppler model.  The physical model fit lives in :mod:`fit`.

Method (STFT peak + parabolic interpolation)
-------------------------------------------
1. Split the signal into Hann-windowed frames of ``frame_len`` samples with
   hop ``hop``.  With a 512-sample frame at 8 kHz the window is 64 ms and the
   DFT bin spacing is 15.625 Hz.
2. Take the magnitude spectrum of each frame and pick the largest bin inside
   a caller-declared search band ``[f_min, f_max]``.  The band is a stated
   front-end prior (a narrowband component is expected to live there); it
   never uses the true parameters.
3. Refine the peak location by fitting a parabola through the log-magnitudes
   of the peak bin and its two neighbours.  For a Hann window this is the
   standard sub-bin estimator; the residual bias is small when the frequency
   changes slowly across one frame (it changes by < 2 Hz at the closest
   approach in the E0 base scenario).
4. Report the frequency at the frame centre time.

Known limitations, restated in the report: the estimate is defined only where
the narrowband component is above the local noise floor; below roughly
``-10 dB`` per-sample SNR the peak can jump to a noise maximum, producing
heavy-tailed outliers (E0 measures this).  Overlapping frames make successive
IF errors correlated, so they are not independent samples even though the
physical fit treats them that way.  A single narrowband component is assumed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class InstantaneousFrequencyTrack:
    """Estimated IF track: one frequency estimate per STFT frame centre."""

    t: np.ndarray          # frame-centre times, s
    f: np.ndarray          # estimated instantaneous frequency, Hz
    frame_len: int
    hop: int
    fs: float
    f_min: float
    f_max: float


def _hann(frame_len: int) -> np.ndarray:
    return np.hanning(frame_len)


def estimate_if_track(
    signal: np.ndarray,
    fs: float,
    frame_len: int = 512,
    hop: int = 256,
    f_min: float = 180.0,
    f_max: float = 2800.0,
    t_start: float = 0.0,
) -> InstantaneousFrequencyTrack:
    """Estimate a narrowband instantaneous-frequency track from a real signal.

    Parameters
    ----------
    signal:
        Real-valued waveform.
    fs:
        Sample rate in Hz.
    frame_len, hop:
        STFT frame length and hop in samples (``hop <= frame_len``).
    f_min, f_max:
        Search band for the narrowband peak, in Hz.  Must lie in
        ``[0, fs/2]``.  This is a front-end prior, not a fitted parameter.
    t_start:
        Time of the first sample of ``signal`` in the caller's absolute time
        axis, in seconds.  Frame-centre times are returned as
        ``t_start + (frame_start + frame_len/2)/fs``; the front end has no
        other way to know where the recording sits on the clock, so this must
        be supplied by the caller that owns the timestamps.
    """
    x = np.asarray(signal, dtype=np.float64)
    if x.ndim != 1:
        raise ValueError("signal must be one-dimensional")
    if not (0 < hop <= frame_len):
        raise ValueError("require 0 < hop <= frame_len")
    if frame_len > x.size:
        raise ValueError("frame_len exceeds signal length")
    if not (0.0 <= f_min < f_max <= fs / 2.0):
        raise ValueError("search band must lie inside [0, fs/2]")

    window = _hann(frame_len)
    n_frames = 1 + (x.size - frame_len) // hop
    idx = np.arange(n_frames) * hop
    frames = x[idx[:, None] + np.arange(frame_len)[None, :]]
    spectra = np.fft.rfft(frames * window[None, :], axis=1)
    mag = np.abs(spectra)

    bin_hz = fs / frame_len
    k_min = int(np.ceil(f_min / bin_hz))
    k_max = int(np.floor(f_max / bin_hz))
    k_min = max(k_min, 1)
    k_max = min(k_max, mag.shape[1] - 2)
    if k_max <= k_min:
        raise ValueError("search band contains too few DFT bins")

    band = mag[:, k_min : k_max + 1]
    k_rel = np.argmax(band, axis=1)
    k = k_rel + k_min

    # Parabolic interpolation on log-magnitude around the peak bin.
    logmag = np.log(mag + 1e-12)
    rows = np.arange(n_frames)
    y_lo = logmag[rows, k - 1]
    y_c = logmag[rows, k]
    y_hi = logmag[rows, k + 1]
    denom = y_lo - 2.0 * y_c + y_hi
    delta = np.zeros(n_frames, dtype=np.float64)
    ok = np.abs(denom) > 1e-12
    delta[ok] = 0.5 * (y_lo[ok] - y_hi[ok]) / denom[ok]
    delta = np.clip(delta, -0.5, 0.5)
    f_hat = (k + delta) * bin_hz

    t_centres = float(t_start) + (idx + 0.5 * frame_len) / fs
    return InstantaneousFrequencyTrack(
        t=t_centres,
        f=f_hat,
        frame_len=frame_len,
        hop=hop,
        fs=float(fs),
        f_min=float(f_min),
        f_max=float(f_max),
    )
