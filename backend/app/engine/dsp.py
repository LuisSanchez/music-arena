"""Vectorized building blocks for electronic synthesis."""

from __future__ import annotations

import threading

import numpy as np
from scipy.signal import butter, lfilter, sosfilt

# Default for arena. Radio jobs use use_sample_rate() context.
SR = 32000
_tls = threading.local()


def get_sr() -> int:
    return int(getattr(_tls, "sr", SR))


class use_sample_rate:
    """Temporarily set sample rate for the current thread (radio vs arena)."""

    def __init__(self, sr: int) -> None:
        self.sr = int(sr)
        self._prev: int | None = None

    def __enter__(self) -> int:
        self._prev = getattr(_tls, "sr", None)
        _tls.sr = self.sr
        return self.sr

    def __exit__(self, *args: object) -> None:
        if self._prev is None:
            if hasattr(_tls, "sr"):
                delattr(_tls, "sr")
        else:
            _tls.sr = self._prev


def samples(seconds: float) -> int:
    return max(1, int(round(seconds * get_sr())))


def time_axis(n: int) -> np.ndarray:
    return np.arange(n, dtype=np.float64) / get_sr()


def midi_to_hz(midi: float) -> float:
    return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))


def db_to_lin(db: float) -> float:
    return 10.0 ** (db / 20.0)


def fade(x: np.ndarray, fade_in: float = 0.004, fade_out: float = 0.008) -> np.ndarray:
    n = x.shape[-1]
    out = x.astype(np.float64, copy=True)
    fi = min(n, samples(fade_in))
    fo = min(n, samples(fade_out))
    if fi > 1:
        ramp = np.linspace(0.0, 1.0, fi)
        out[..., :fi] *= ramp
    if fo > 1:
        ramp = np.linspace(1.0, 0.0, fo)
        out[..., -fo:] *= ramp
    return out


def adsr(
    n: int,
    attack: float,
    decay: float,
    sustain: float,
    release: float,
    peak: float = 1.0,
) -> np.ndarray:
    a = samples(attack)
    d = samples(decay)
    r = samples(release)
    env = np.zeros(n, dtype=np.float64)
    i = 0
    if a > 0:
        take = min(a, n)
        env[i : i + take] = np.linspace(0.0, peak, take)
        i += take
    if i < n and d > 0:
        take = min(d, n - i)
        env[i : i + take] = np.linspace(peak, peak * sustain, take)
        i += take
    sustain_end = max(i, n - r)
    if i < sustain_end:
        env[i:sustain_end] = peak * sustain
        i = sustain_end
    if i < n:
        env[i:] = np.linspace(env[i - 1] if i else peak * sustain, 0.0, n - i)
    return env


def exp_decay(n: int, time_const: float) -> np.ndarray:
    t = time_axis(n)
    return np.exp(-t / max(time_const, 1e-4))


def sine(freq: np.ndarray | float, t: np.ndarray, phase: float = 0.0) -> np.ndarray:
    return np.sin(2.0 * np.pi * freq * t + phase)


def saw(freq: np.ndarray | float, t: np.ndarray, phase: float = 0.0) -> np.ndarray:
    return 2.0 * np.mod(freq * t + phase / (2.0 * np.pi) + 0.5, 1.0) - 1.0


def square(freq: np.ndarray | float, t: np.ndarray, pw: float = 0.5) -> np.ndarray:
    return np.where(np.mod(freq * t, 1.0) < pw, 1.0, -1.0)


def triangle(freq: np.ndarray | float, t: np.ndarray) -> np.ndarray:
    return 2.0 * np.abs(2.0 * np.mod(freq * t, 1.0) - 1.0) - 1.0


def poly_blep_saw(freq: float, t: np.ndarray) -> np.ndarray:
    """Naive saw is fine at musical pitches once lowpassed; cheap anti-alias tilt."""
    raw = saw(freq, t)
    # Soften aliases with a gentle one-pole based on frequency
    alpha = min(0.45, 1800.0 / max(freq, 80.0))
    return one_pole_lpf(raw, alpha)


def white(n: int, rng: np.random.Generator) -> np.ndarray:
    return rng.uniform(-1.0, 1.0, n)


def pinkish(n: int, rng: np.random.Generator) -> np.ndarray:
    x = white(n, rng)
    return one_pole_lpf(x, 0.08)


def one_pole_lpf(x: np.ndarray, alpha: float) -> np.ndarray:
    a = float(np.clip(alpha, 1e-4, 1.0))
    b = [a]
    aa = [1.0, -(1.0 - a)]
    return lfilter(b, aa, x).astype(np.float64)


def one_pole_hpf(x: np.ndarray, alpha: float) -> np.ndarray:
    return x - one_pole_lpf(x, alpha)


def biquad_filter(
    x: np.ndarray,
    cutoff: float,
    q: float = 0.8,
    kind: str = "lowpass",
) -> np.ndarray:
    sr = get_sr()
    cutoff = float(np.clip(cutoff, 30.0, sr * 0.45))
    q = float(np.clip(q, 0.3, 12.0))
    if kind == "lowpass":
        sos = butter(2, cutoff, btype="low", fs=sr, output="sos")
    elif kind == "highpass":
        sos = butter(2, cutoff, btype="high", fs=sr, output="sos")
    else:
        bw = max(cutoff / max(q, 0.4), 40.0)
        lo = max(30.0, cutoff - bw / 2)
        hi = min(sr * 0.45, cutoff + bw / 2)
        if hi <= lo:
            hi = lo + 40.0
        sos = butter(2, [lo, hi], btype="band", fs=sr, output="sos")
    return sosfilt(sos, x).astype(np.float64)


def resonant_lpf(x: np.ndarray, cutoff: float, q: float = 1.2) -> np.ndarray:
    sr = get_sr()
    cutoff = float(np.clip(cutoff, 40.0, sr * 0.42))
    sos = butter(3, cutoff, btype="low", fs=sr, output="sos")
    y = sosfilt(sos, x).astype(np.float64)
    if q > 1.0:
        peak = biquad_filter(x, cutoff, q=min(q, 8.0), kind="band")
        y = y + (q - 1.0) * 0.08 * peak
    return y


def saturate(x: np.ndarray, drive: float = 1.4) -> np.ndarray:
    return np.tanh(x * drive) / np.tanh(drive)


def soft_clip(x: np.ndarray, thresh: float = 0.95) -> np.ndarray:
    return thresh * np.tanh(x / max(thresh, 1e-6))


def mix_at(dest: np.ndarray, src: np.ndarray, start: int, gain: float = 1.0) -> None:
    if start >= dest.shape[-1] or start + 1 < 0:
        return
    if start < 0:
        src = src[..., -start:]
        start = 0
    end = min(dest.shape[-1], start + src.shape[-1])
    take = end - start
    if take <= 0:
        return
    dest[..., start:end] += src[..., :take] * gain


def stereo(mono: np.ndarray, pan: float = 0.0) -> np.ndarray:
    pan = float(np.clip(pan, -1.0, 1.0))
    left = np.sqrt(0.5 * (1.0 - pan))
    right = np.sqrt(0.5 * (1.0 + pan))
    return np.vstack((mono * left, mono * right))


def widen(stereo_x: np.ndarray, amount: float = 0.25) -> np.ndarray:
    mid = 0.5 * (stereo_x[0] + stereo_x[1])
    side = 0.5 * (stereo_x[0] - stereo_x[1])
    side = side * (1.0 + amount)
    return np.vstack((mid + side, mid - side))


def delay_stereo(
    x: np.ndarray,
    time_s: float,
    feedback: float = 0.18,
    mix: float = 0.12,
    ping_pong: bool = False,
) -> np.ndarray:
    n = x.shape[1]
    d = samples(time_s)
    if d <= 0 or d >= n or mix <= 0.001:
        return x
    # Avoid sub-20ms delays (classic flanger comb zone)
    d = max(d, samples(0.03))
    out = x.copy()
    delayed = np.zeros_like(x)
    if ping_pong:
        delayed[0, d:] = x[1, :-d]
        delayed[1, d:] = x[0, :-d]
    else:
        delayed[:, d:] = x[:, :-d]
    # Single soft second tap only (weaker than before)
    d2 = min(n - 1, int(d * 2))
    if d2 > d:
        delayed[:, d2:] += 0.22 * x[:, :-d2]
    wet = delayed + feedback * 0.25 * delayed
    out = (1.0 - mix) * out + mix * wet
    return out


def schroeder_reverb(x: np.ndarray, mix: float = 0.12, decay: float = 0.48) -> np.ndarray:
    """Room-ish reverb; comb times stay above flanger range."""
    # Longer combs (~45–95ms) = space, not whooshy modulation
    comb_ms = [45.1, 53.3, 61.7, 72.9, 84.1, 95.3]
    out = np.zeros_like(x)
    for i, ms in enumerate(comb_ms):
        d = samples(ms / 1000.0)
        tap = np.zeros_like(x)
        if d < x.shape[1]:
            tap[:, d:] = x[:, :-d]
            fb = decay * (0.72 + 0.04 * (i % 3))
            # recursive-ish: second generation
            d2 = min(x.shape[1] - 1, d * 2)
            tap[:, d2:] += fb * x[:, :-d2]
            d3 = min(x.shape[1] - 1, int(d * 3.2))
            tap[:, d3:] += fb * 0.5 * x[:, :-d3]
        pan = -0.7 if i % 2 == 0 else 0.7
        out += stereo(tap[0] * 0.5 + tap[1] * 0.5, pan)
    out = out / 5.5
    return (1.0 - mix) * x + mix * out


def noise_riser(n: int, rng: np.random.Generator, start_cut: float, end_cut: float) -> np.ndarray:
    noise = white(n, rng)
    # piecewise opening filter
    chunks = 16
    out = np.zeros(n)
    for i in range(chunks):
        a = int(i * n / chunks)
        b = int((i + 1) * n / chunks)
        amt = i / max(chunks - 1, 1)
        cut = start_cut + (end_cut - start_cut) * (amt**1.4)
        out[a:b] = resonant_lpf(noise[a:b], cut, q=0.9)
    env = np.linspace(0.05, 1.0, n) ** 1.6
    return fade(out * env, 0.02, 0.01)


def limiter(x: np.ndarray, ceiling: float = 0.97) -> np.ndarray:
    peak = np.max(np.abs(x)) + 1e-9
    if peak > ceiling:
        x = x * (ceiling / peak)
    return soft_clip(x, ceiling)


def rms_normalize(x: np.ndarray, target_db: float = -14.0) -> np.ndarray:
    rms = np.sqrt(np.mean(x**2)) + 1e-9
    target = db_to_lin(target_db)
    return x * (target / rms)


def to_int16_stereo(x: np.ndarray) -> bytes:
    x = np.clip(x, -1.0, 1.0)
    pcm = (x.T * 32767.0).astype(np.int16)
    return pcm.tobytes()
