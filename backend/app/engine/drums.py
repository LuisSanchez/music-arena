"""One-shot electronic drums with producer-specific character."""

from __future__ import annotations

import numpy as np

from .dsp import (
    SR,
    biquad_filter,
    exp_decay,
    fade,
    resonant_lpf,
    saturate,
    sine,
    time_axis,
    white,
)


def kick(rng: np.random.Generator, style: str, character: str) -> np.ndarray:
    if style == "lofi":
        length = 0.32
        start_f, end_f = 118.0, 46.0
        click = 0.18
        punch = 0.9
    elif style == "slow":
        length = 0.42
        start_f, end_f = 130.0, 40.0
        click = 0.12
        punch = 0.75
    elif style == "trance":
        length = 0.28
        start_f, end_f = 168.0, 48.0
        click = 0.28
        punch = 1.15
    elif style == "dance":
        length = 0.26
        start_f, end_f = 155.0, 50.0
        click = 0.34
        punch = 1.05
    else:  # hifi / festival
        length = 0.24
        start_f, end_f = 180.0, 52.0
        click = 0.4
        punch = 1.25

    if character == "warehouse":
        punch *= 1.15
        click *= 0.85
    elif character == "tape":
        click *= 0.55
        end_f -= 4
    elif character == "apex":
        click *= 1.2

    n = int(length * SR)
    t = time_axis(n)
    sweep = end_f + (start_f - end_f) * np.exp(-t * 28.0)
    phase = 2 * np.pi * np.cumsum(sweep) / SR
    body = np.sin(phase) * exp_decay(n, 0.085 if style != "slow" else 0.14)
    sub = sine(end_f, t) * exp_decay(n, 0.16)
    click_n = int(0.007 * SR)
    clk = white(click_n, rng) * np.linspace(1.0, 0.0, click_n)
    clk = biquad_filter(clk, 4500 if style != "lofi" else 2200, q=0.7, kind="highpass")
    out = body * 0.86 + sub * 0.42
    out[:click_n] += clk * click
    out = saturate(out * punch, 1.3 if style != "lofi" else 0.9)
    if style == "lofi":
        out = resonant_lpf(out, 5200, q=0.7)
    return fade(out, 0.0008, 0.02)


def snare(rng: np.random.Generator, style: str, character: str) -> np.ndarray:
    n = int((0.22 if style != "slow" else 0.3) * SR)
    t = time_axis(n)
    tone_f = 190 if style != "lofi" else 165
    tone = sine(tone_f, t) * exp_decay(n, 0.045)
    tone += 0.35 * sine(tone_f * 1.54, t) * exp_decay(n, 0.03)
    noise = white(n, rng)
    if style in {"trance", "hifi"}:
        noise = biquad_filter(noise, 2200, q=0.8, kind="band")
    elif style == "dance":
        noise = biquad_filter(noise, 1800, q=0.7, kind="band")
    else:
        noise = biquad_filter(noise, 1400, q=0.6, kind="band")
    noise *= exp_decay(n, 0.055 if style != "lofi" else 0.08)
    snap = white(int(0.008 * SR), rng)
    body = tone * 0.35 + noise * (0.85 if style != "lofi" else 0.55)
    body[: snap.shape[0]] += snap * 0.25
    if character == "apex":
        body = saturate(body * 1.2, 1.6)
    return fade(body, 0.0005, 0.03)


def clap(rng: np.random.Generator, style: str) -> np.ndarray:
    # Soft layered clap — fewer micro-bursts (was a metallic rattle)
    n = int(0.22 * SR)
    out = np.zeros(n)
    offsets = [0, int(0.014 * SR)]
    for i, off in enumerate(offsets):
        burst_n = int(0.035 * SR)
        burst = white(burst_n, rng) * exp_decay(burst_n, 0.014 + 0.004 * i)
        burst = biquad_filter(burst, 1400 if style != "lofi" else 1000, q=0.7, kind="band")
        gain = 0.85 if i == 0 else 0.55
        end = min(n, off + burst_n)
        out[off:end] += burst[: end - off] * gain
    tail = white(n, rng)
    tail = biquad_filter(tail, 1800, q=0.45, kind="band") * exp_decay(n, 0.1)
    out += 0.14 * tail
    return fade(out * 0.85, 0.0005, 0.05)


def hat(rng: np.random.Generator, open_hat: bool, style: str) -> np.ndarray:
    length = 0.28 if open_hat else (0.045 if style != "lofi" else 0.06)
    n = int(length * SR)
    noise = white(n, rng)
    cut = 9000 if style in {"hifi", "trance"} else 7200
    if style == "lofi":
        cut = 4800
    noise = biquad_filter(noise, cut, q=0.6, kind="highpass")
    if open_hat:
        noise = resonant_lpf(noise, 11000 if style != "lofi" else 7000, q=0.7)
        noise *= exp_decay(n, 0.085)
    else:
        noise *= exp_decay(n, 0.012 if style != "lofi" else 0.02)
    return fade(noise, 0.0003, 0.008)


def ride(rng: np.random.Generator, style: str) -> np.ndarray:
    n = int(0.4 * SR)
    t = time_axis(n)
    metal = np.zeros(n)
    for f in (320, 487, 743, 1088, 1650, 2420):
        metal += sine(f * (1.0 + 0.003 * rng.normal()), t, phase=rng.uniform(0, 6.28))
    metal = metal / 6.0
    noise = biquad_filter(white(n, rng), 7000, q=0.5, kind="highpass")
    body = (0.35 * metal + 0.65 * noise) * exp_decay(n, 0.12 if style != "slow" else 0.18)
    return fade(body * 0.55, 0.001, 0.04)


def perc(rng: np.random.Generator, kind: str) -> np.ndarray:
    if kind == "rim":
        n = int(0.06 * SR)
        t = time_axis(n)
        body = sine(780, t) * exp_decay(n, 0.012)
        body += 0.5 * white(n, rng) * exp_decay(n, 0.008)
        return fade(biquad_filter(body, 2000, q=0.9, kind="band"), 0.0003, 0.008)
    if kind == "shaker":
        n = int(0.07 * SR)
        body = biquad_filter(white(n, rng), 6500, q=0.6, kind="highpass")
        body *= exp_decay(n, 0.018)
        return fade(body, 0.0004, 0.01)
    # tom / bongo
    n = int(0.16 * SR)
    t = time_axis(n)
    f = 140 + 40 * rng.random()
    sweep = f + 40 * np.exp(-t * 40)
    phase = 2 * np.pi * np.cumsum(sweep) / SR
    body = np.sin(phase) * exp_decay(n, 0.05)
    return fade(body, 0.0005, 0.02)


def vinyl_crackle(n: int, rng: np.random.Generator, density: float = 0.0008) -> np.ndarray:
    noise = white(n, rng) * 0.012
    noise = biquad_filter(noise, 1800, q=0.4, kind="band")
    pops = np.zeros(n)
    count = max(1, int(n * density))
    for _ in range(count):
        i = int(rng.integers(0, n - 40))
        width = int(rng.integers(8, 35))
        pops[i : i + width] += rng.uniform(0.08, 0.28) * rng.choice([-1.0, 1.0])
        pops[i : i + width] *= np.hanning(width)
    return noise + pops
