"""Render a composed blueprint to stereo PCM."""

from __future__ import annotations

import numpy as np

from . import drums
from .compose import Blueprint, Hit, add_swing
from .dsp import (
    SR,
    adsr,
    biquad_filter,
    delay_stereo,
    fade,
    limiter,
    midi_to_hz,
    mix_at,
    noise_riser,
    one_pole_hpf,
    poly_blep_saw,
    resonant_lpf,
    rms_normalize,
    saturate,
    schroeder_reverb,
    sine,
    soft_clip,
    stereo,
    time_axis,
    to_int16_stereo,
    triangle,
    white,
    widen,
)
from .theory import PRODUCERS


def beat_to_sample(beat: float, bpm: float) -> int:
    return int(round(beat * 60.0 / bpm * SR))


def supersaw(freq: float, n: int, detune_cents: float, voices: int = 7) -> np.ndarray:
    t = time_axis(n)
    mix = np.zeros(n)
    for i in range(voices):
        # spread from -detune to +detune
        if voices == 1:
            cents = 0.0
        else:
            cents = -detune_cents + 2 * detune_cents * i / (voices - 1)
        f = freq * (2.0 ** (cents / 1200.0))
        mix += poly_blep_saw(f, t)
    return mix / voices


def _fm_keys(freq: float, n: int, vel: float) -> np.ndarray:
    t = time_axis(n)
    mod = sine(freq * 2.01, t) * freq * 1.8 * adsr(n, 0.004, 0.18, 0.15, 0.25)
    carrier = np.sin(2 * np.pi * freq * t + mod / SR * 40)
    env = adsr(n, 0.006, 0.22, 0.35, 0.35)
    return fade(carrier * env * vel, 0.004, 0.03)


def _pad(freq: float, n: int, vel: float, bright: float) -> np.ndarray:
    wave = supersaw(freq, n, detune_cents=12, voices=5)
    wave += 0.25 * sine(freq, time_axis(n))
    env = adsr(n, 0.18, 0.4, 0.7, 0.5)
    cut = 900 + 2600 * bright
    wave = resonant_lpf(wave, cut, q=0.8)
    return fade(wave * env * vel, 0.02, 0.08)


def _lead_saw(freq: float, n: int, vel: float, bright: float, gated: bool) -> np.ndarray:
    wave = supersaw(freq, n, detune_cents=14 if gated else 8, voices=7)
    env = adsr(n, 0.006, 0.08, 0.55 if not gated else 0.25, 0.06 if gated else 0.12)
    cut = 1400 + 4200 * bright
    wave = resonant_lpf(wave, cut, q=1.4)
    return fade(wave * env * vel, 0.003, 0.02)


def _arp_pluck(freq: float, n: int, vel: float, bright: float) -> np.ndarray:
    t = time_axis(n)
    wave = 0.65 * poly_blep_saw(freq, t) + 0.35 * squareish(freq, t)
    env = adsr(n, 0.002, 0.06, 0.12, 0.05)
    wave = resonant_lpf(wave, 1800 + 3200 * bright, q=2.2)
    return fade(wave * env * vel, 0.001, 0.015)


def squareish(freq: float, t: np.ndarray) -> np.ndarray:
    return np.sign(np.sin(2 * np.pi * freq * t))


def _bass(freq: float, n: int, vel: float, style: str, drive: float) -> np.ndarray:
    t = time_axis(n)
    if style == "lofi":
        wave = 0.7 * sine(freq, t) + 0.3 * triangle(freq, t)
        wave = resonant_lpf(wave, 380, q=0.8)
        env = adsr(n, 0.008, 0.12, 0.6, 0.12)
    elif style == "slow":
        wave = 0.8 * sine(freq, t) + 0.2 * poly_blep_saw(freq, t)
        wave = resonant_lpf(wave, 280, q=0.7)
        env = adsr(n, 0.02, 0.2, 0.7, 0.2)
    elif style == "dance":
        wave = 0.45 * sine(freq, t) + 0.55 * poly_blep_saw(freq, t)
        wave = resonant_lpf(wave, 520, q=1.3)
        env = adsr(n, 0.004, 0.08, 0.45, 0.08)
    else:
        wave = 0.35 * sine(freq, t) + 0.65 * poly_blep_saw(freq, t)
        wave = resonant_lpf(wave, 480, q=1.6)
        env = adsr(n, 0.003, 0.05, 0.4, 0.05)
    return fade(saturate(wave * env * vel, 0.8 + 0.5 * drive), 0.002, 0.012)


def _stab(freq: float, n: int, vel: float, bright: float) -> np.ndarray:
    t = time_axis(n)
    wave = 0.5 * poly_blep_saw(freq, t) + 0.3 * poly_blep_saw(freq * 1.005, t) + 0.2 * sine(freq, t)
    env = adsr(n, 0.003, 0.07, 0.12, 0.06)
    wave = resonant_lpf(wave, 1600 + 2400 * bright, q=1.1)
    return fade(wave * env * vel, 0.002, 0.02)


def _crash(rng: np.random.Generator, n: int, vel: float) -> np.ndarray:
    noise = white(n, rng)
    noise = biquad_filter(noise, 4200, q=0.5, kind="highpass")
    env = np.exp(-time_axis(n) / 0.55)
    return fade(noise * env * vel * 0.45, 0.002, 0.05)


def render_blueprint(bp: Blueprint, rng: np.random.Generator) -> tuple[np.ndarray, dict]:
    producer = PRODUCERS[bp.producer]
    n = beat_to_sample(bp.bars * 4 + 2, bp.bpm)  # tail
    buses = {
        "drums": np.zeros((2, n)),
        "bass": np.zeros((2, n)),
        "music": np.zeros((2, n)),
        "fx": np.zeros((2, n)),
    }

    kick_hits: list[int] = []

    for hit in bp.hits:
        start_beat = add_swing(hit.beat, bp.swing)
        start = beat_to_sample(start_beat, bp.bpm)
        if start >= n:
            continue
        voice = hit.voice
        buf: np.ndarray | None = None
        bus = "music"

        if voice == "kick":
            buf = drums.kick(rng, bp.style, bp.producer)
            bus = "drums"
            kick_hits.append(start)
        elif voice == "snare":
            buf = drums.snare(rng, bp.style, bp.producer)
            bus = "drums"
        elif voice == "clap":
            buf = drums.clap(rng, bp.style)
            bus = "drums"
        elif voice == "hat":
            buf = drums.hat(rng, False, bp.style) * hit.velocity
            bus = "drums"
        elif voice == "hat_open":
            buf = drums.hat(rng, True, bp.style) * hit.velocity
            bus = "drums"
        elif voice == "ride":
            buf = drums.ride(rng, bp.style) * hit.velocity
            bus = "drums"
        elif voice == "rim":
            buf = drums.perc(rng, "rim") * hit.velocity
            bus = "drums"
        elif voice == "shaker":
            buf = drums.perc(rng, "shaker") * hit.velocity
            bus = "drums"
        elif voice == "tom":
            buf = drums.perc(rng, "tom") * hit.velocity
            bus = "drums"
        elif voice == "crackle":
            length = min(n - start, beat_to_sample(hit.duration, bp.bpm))
            buf = drums.vinyl_crackle(length, rng, density=0.00055)
            bus = "fx"
        elif voice == "riser":
            length = min(n - start, beat_to_sample(hit.duration, bp.bpm))
            buf = noise_riser(length, rng, 200, 9000) * hit.velocity
            bus = "fx"
        elif voice == "crash":
            buf = _crash(rng, beat_to_sample(2.5, bp.bpm), hit.velocity)
            bus = "fx"
        elif voice == "impact":
            length = beat_to_sample(0.6, bp.bpm)
            t = time_axis(length)
            buf = sine(55, t) * np.exp(-t / 0.12) * hit.velocity
            k = drums.kick(rng, "hifi", bp.producer)
            take = min(length, k.shape[0])
            buf[:take] += 0.4 * k[:take]
            bus = "fx"
        else:
            freq = midi_to_hz(hit.pitch) if hit.pitch else 110.0
            length = min(n - start, beat_to_sample(hit.duration, bp.bpm))
            if length < 32:
                continue
            bright = float(producer["bright"])
            if voice == "bass":
                buf = _bass(freq, length, hit.velocity, bp.style, float(producer["drive"]))
                bus = "bass"
            elif voice == "pad":
                buf = _pad(freq, length, hit.velocity, bright)
            elif voice == "lead":
                buf = _lead_saw(freq, length, hit.velocity, bright, gated=bp.style in {"trance", "hifi"})
            elif voice == "arp":
                buf = _arp_pluck(freq, length, hit.velocity, bright)
            elif voice == "stab":
                buf = _stab(freq, length, hit.velocity, bright)
            elif voice == "keys":
                buf = _fm_keys(freq, length, hit.velocity)
            else:
                continue

        if buf is None:
            continue
        if buf.ndim == 1:
            stereo_buf = stereo(buf, hit.pan)
        else:
            stereo_buf = buf
        mix_at(buses[bus], stereo_buf, start, 1.0)

    # Sidechain ducks music + bass from kick
    duck = np.ones(n)
    duck_len = beat_to_sample(0.42 if bp.style in {"trance", "hifi", "dance"} else 0.28, bp.bpm)
    curve = 1.0 - bp.sidechain * np.exp(-np.linspace(0, 6, duck_len))
    for k in kick_hits:
        end = min(n, k + duck_len)
        duck[k:end] *= curve[: end - k]
    buses["music"] *= duck
    buses["bass"] *= np.sqrt(duck)  # bass ducks a bit less so the note remains

    drums_b = buses["drums"] * (0.95 * float(producer["punch"]))
    bass_b = buses["bass"] * 0.9
    music_b = buses["music"] * 0.85
    fx_b = buses["fx"] * 0.7

    # Tone shaping per producer
    bright = float(producer["bright"])
    if bright < 0.85:
        music_b = np.vstack(
            [
                resonant_lpf(music_b[0], 6200, 0.7),
                resonant_lpf(music_b[1], 6200, 0.7),
            ]
        )
    else:
        music_b = np.vstack(
            [
                one_pole_hpf(music_b[0], 0.02) * 0.15 + music_b[0] * 0.92,
                one_pole_hpf(music_b[1], 0.02) * 0.15 + music_b[1] * 0.92,
            ]
        )

    music_b = delay_stereo(
        music_b,
        time_s=(60.0 / bp.bpm) * (0.75 if bp.style != "lofi" else 1.0),
        feedback=0.32,
        mix=float(producer["delay"]),
        ping_pong=True,
    )
    music_b = schroeder_reverb(music_b, mix=float(producer["reverb"]), decay=0.62)
    music_b = widen(music_b, amount=float(producer["width"]))

    if float(producer["dirt"]) > 0.2:
        dirt = float(producer["dirt"])
        bass_b = saturate(bass_b, 1.0 + dirt)
        drums_b = saturate(drums_b, 1.0 + 0.4 * dirt)

    mix = drums_b + bass_b + music_b + fx_b

    # Highpass rumble, gentle presence
    mix = np.vstack(
        [
            biquad_filter(mix[0], 28, kind="highpass"),
            biquad_filter(mix[1], 28, kind="highpass"),
        ]
    )
    mix = rms_normalize(mix, target_db=-13.5)
    mix = limiter(soft_clip(mix * 1.05, 0.98), 0.97)

    # Tiny tape wow for lofi / tape
    if bp.style in {"lofi", "slow"} or bp.producer == "tape":
        t = time_axis(n)
        wow = 1.0 + 0.0018 * np.sin(2 * np.pi * 0.35 * t)
        idx = np.clip((np.arange(n) * wow).astype(np.int64), 0, n - 1)
        mix = mix[:, idx]

    pcm = to_int16_stereo(mix)
    meta = {
        "duration": mix.shape[1] / SR,
        "bpm": bp.bpm,
        "key": _key_name(bp.key, bp.scale),
        "style": bp.style,
        "tags": bp.tags,
        "producer": bp.producer,
        "producerLabel": bp.producer_label,
        "title": bp.title,
        "bars": bp.bars,
        "sampleRate": SR,
    }
    return mix, {"pcm": pcm, "meta": meta}


def _key_name(root: int, scale: str) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    quality = {
        "minor": "minor",
        "harmonic": "harmonic minor",
        "dorian": "dorian",
        "major": "major",
    }[scale]
    return f"{names[root % 12]} {quality}"


def render_wav_bytes(pcm: bytes) -> bytes:
    import wave
    from io import BytesIO

    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm)
    return buf.getvalue()
