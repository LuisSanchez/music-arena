"""Render a composed blueprint to stereo PCM."""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from . import drums
from .compose import Blueprint, Hit, add_swing
from .dsp import (
    adsr,
    biquad_filter,
    delay_stereo,
    fade,
    get_sr,
    limiter,
    midi_to_hz,
    mix_at,
    noise_riser,
    resonant_lpf,
    rms_normalize,
    saturate,
    saw,
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
from .quality import ARENA, QualityProfile
from .theory import PRODUCERS


def beat_to_sample(beat: float, bpm: float) -> int:
    return int(round(beat * 60.0 / bpm * get_sr()))


def supersaw(freq: float, n: int, detune_cents: float, voices: int = 7) -> np.ndarray:
    """Detuned saw stack. One shared LPF at the end instead of per-voice polyBLEP."""
    t = time_axis(n)
    mix = np.zeros(n, dtype=np.float64)
    for i in range(voices):
        if voices == 1:
            cents = 0.0
        else:
            cents = -detune_cents + 2 * detune_cents * i / (voices - 1)
        f = freq * (2.0 ** (cents / 1200.0))
        mix += saw(f, t)
    mix /= max(voices, 1)
    # Soft anti-alias tilt (cheaper than filtering each voice)
    return resonant_lpf(mix, min(get_sr() * 0.42, max(freq * 8.0, 2500.0)), q=0.7)


def _fm_keys(freq: float, n: int, vel: float) -> np.ndarray:
    t = time_axis(n)
    mod = sine(freq * 2.01, t) * freq * 1.8 * adsr(n, 0.004, 0.18, 0.15, 0.25)
    carrier = np.sin(2 * np.pi * freq * t + mod / get_sr() * 40)
    env = adsr(n, 0.006, 0.22, 0.35, 0.35)
    return fade(carrier * env * vel, 0.004, 0.03)


def _pad(
    freq: float, n: int, vel: float, bright: float, profile: QualityProfile = ARENA
) -> np.ndarray:
    wave = supersaw(freq, n, detune_cents=profile.detune_pad, voices=profile.supersaw_voices_pad)
    wave += 0.3 * sine(freq, time_axis(n))
    env = adsr(n, 0.18, 0.4, 0.7, 0.5)
    cut = 900 + 2600 * bright
    wave = resonant_lpf(wave, cut, q=0.8)
    return fade(wave * env * vel, 0.02, 0.08)


def _lead_saw(
    freq: float,
    n: int,
    vel: float,
    bright: float,
    gated: bool,
    profile: QualityProfile = ARENA,
) -> np.ndarray:
    wave = supersaw(
        freq,
        n,
        detune_cents=profile.detune_lead if gated else max(3.0, profile.detune_lead - 2),
        voices=profile.supersaw_voices_lead,
    )
    env = adsr(n, 0.006, 0.08, 0.55 if not gated else 0.25, 0.06 if gated else 0.12)
    cut = 1400 + 4200 * bright
    wave = resonant_lpf(wave, cut, q=1.2)
    return fade(wave * env * vel, 0.003, 0.02)


def _arp_pluck(freq: float, n: int, vel: float, bright: float) -> np.ndarray:
    t = time_axis(n)
    wave = 0.65 * saw(freq, t) + 0.35 * squareish(freq, t)
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
        wave = 0.8 * sine(freq, t) + 0.2 * saw(freq, t)
        wave = resonant_lpf(wave, 280, q=0.7)
        env = adsr(n, 0.02, 0.2, 0.7, 0.2)
    elif style == "dance":
        wave = 0.45 * sine(freq, t) + 0.55 * saw(freq, t)
        wave = resonant_lpf(wave, 520, q=1.3)
        env = adsr(n, 0.004, 0.08, 0.45, 0.08)
    else:
        wave = 0.35 * sine(freq, t) + 0.65 * saw(freq, t)
        wave = resonant_lpf(wave, 480, q=1.6)
        env = adsr(n, 0.003, 0.05, 0.4, 0.05)
    return fade(saturate(wave * env * vel, 0.8 + 0.5 * drive), 0.002, 0.012)


def _stab(freq: float, n: int, vel: float, bright: float) -> np.ndarray:
    t = time_axis(n)
    # Near-unison second voice only — 1.005 was a constant comb/flange
    wave = 0.7 * saw(freq, t) + 0.3 * sine(freq, t)
    env = adsr(n, 0.003, 0.07, 0.12, 0.06)
    wave = resonant_lpf(wave, 1600 + 2400 * bright, q=1.1)
    return fade(wave * env * vel, 0.002, 0.02)


def _crash(rng: np.random.Generator, n: int, vel: float) -> np.ndarray:
    # Soft whoosh — no bright metallic edge
    noise = white(n, rng)
    noise = biquad_filter(noise, 2800, q=0.45, kind="highpass")
    noise = resonant_lpf(noise, 6500, q=0.6)
    env = np.exp(-time_axis(n) / 0.7)
    return fade(noise * env * vel * 0.28, 0.004, 0.08)


@lru_cache(maxsize=64)
def _cached_drum(kind: str, style: str, character: str, open_hat: bool = False) -> np.ndarray:
    """One-shots are style-static; regenerate once, not per hit."""
    rng = np.random.default_rng(abs(hash((kind, style, character, open_hat))) % (2**32))
    if kind == "kick":
        return drums.kick(rng, style, character)
    if kind == "snare":
        return drums.snare(rng, style, character)
    if kind == "clap":
        return drums.clap(rng, style)
    if kind == "hat":
        return drums.hat(rng, open_hat, style)
    if kind == "ride":
        return drums.ride(rng, style)
    if kind == "rim":
        return drums.perc(rng, "rim")
    if kind == "shaker":
        return drums.perc(rng, "shaker")
    if kind == "tom":
        return drums.perc(rng, "tom")
    raise ValueError(kind)


def render_blueprint(
    bp: Blueprint,
    rng: np.random.Generator,
    profile: QualityProfile = ARENA,
) -> tuple[np.ndarray, dict]:
    producer = PRODUCERS[bp.producer]
    n = beat_to_sample(bp.bars * 4 + 2, bp.bpm)  # tail
    # float32 buses: half the RAM/bandwidth of float64, enough for mix
    buses = {
        "drums": np.zeros((2, n), dtype=np.float32),
        "bass": np.zeros((2, n), dtype=np.float32),
        "music": np.zeros((2, n), dtype=np.float32),
        "fx": np.zeros((2, n), dtype=np.float32),
    }

    kick_hits: list[int] = []
    style = bp.style
    character = bp.producer

    for hit in bp.hits:
        start_beat = add_swing(hit.beat, bp.swing)
        start = beat_to_sample(start_beat, bp.bpm)
        if start >= n:
            continue
        voice = hit.voice
        buf: np.ndarray | None = None
        bus = "music"

        if voice == "kick":
            buf = _cached_drum("kick", style, character)
            bus = "drums"
            kick_hits.append(start)
        elif voice == "snare":
            buf = _cached_drum("snare", style, character)
            bus = "drums"
        elif voice == "clap":
            buf = _cached_drum("clap", style, character)
            bus = "drums"
        elif voice == "hat":
            buf = _cached_drum("hat", style, character, False) * hit.velocity
            bus = "drums"
        elif voice == "hat_open":
            buf = _cached_drum("hat", style, character, True) * hit.velocity
            bus = "drums"
        elif voice == "ride":
            buf = _cached_drum("ride", style, character) * hit.velocity
            bus = "drums"
        elif voice == "rim":
            buf = _cached_drum("rim", style, character) * hit.velocity
            bus = "drums"
        elif voice == "shaker":
            buf = _cached_drum("shaker", style, character) * hit.velocity
            bus = "drums"
        elif voice == "tom":
            buf = _cached_drum("tom", style, character) * hit.velocity
            bus = "drums"
        elif voice == "crackle":
            length = min(n - start, beat_to_sample(hit.duration, bp.bpm))
            buf = drums.vinyl_crackle(length, rng, density=0.00055)
            bus = "fx"
        elif voice == "riser":
            length = min(n - start, beat_to_sample(hit.duration, bp.bpm))
            # Cap riser work — long white-noise filters dominate FX cost
            length = min(length, beat_to_sample(8.0, bp.bpm))
            buf = noise_riser(length, rng, 200, 9000) * hit.velocity
            bus = "fx"
        elif voice == "crash":
            buf = _crash(rng, beat_to_sample(2.5, bp.bpm), hit.velocity)
            bus = "fx"
        elif voice == "impact":
            length = beat_to_sample(0.6, bp.bpm)
            t = time_axis(length)
            buf = sine(55, t) * np.exp(-t / 0.12) * hit.velocity
            k = _cached_drum("kick", "hifi", character)
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
                buf = _bass(freq, length, hit.velocity, style, float(producer["drive"]))
                bus = "bass"
            elif voice == "pad":
                buf = _pad(freq, length, hit.velocity, bright, profile=profile)
            elif voice == "lead":
                buf = _lead_saw(
                    freq,
                    length,
                    hit.velocity,
                    bright,
                    gated=style in {"trance", "hifi"},
                    profile=profile,
                )
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
            stereo_buf = stereo(buf.astype(np.float64, copy=False), hit.pan)
        else:
            stereo_buf = buf
        mix_at(buses[bus], stereo_buf.astype(np.float32, copy=False), start, 1.0)

    # Sidechain ducks music + bass from kick (lighter on radio)
    if not profile.light_fx or style in {"trance", "hifi", "dance"}:
        duck = np.ones(n, dtype=np.float32)
        sc = bp.sidechain * (0.55 if profile.light_fx else 1.0)
        duck_len = beat_to_sample(0.42 if style in {"trance", "hifi", "dance"} else 0.28, bp.bpm)
        curve = (1.0 - sc * np.exp(-np.linspace(0, 6, duck_len))).astype(np.float32)
        for k in kick_hits:
            end = min(n, k + duck_len)
            duck[k:end] *= curve[: end - k]
        buses["music"] *= duck
        buses["bass"] *= np.sqrt(duck)

    drums_b = buses["drums"] * np.float32(0.95 * float(producer["punch"]))
    bass_b = buses["bass"] * np.float32(0.9)
    music_b = buses["music"].astype(np.float64) * 0.85
    fx_b = buses["fx"] * np.float32(0.7)

    # Tone shaping per producer (one path — avoid dual full-buffer HPF copies)
    bright = float(producer["bright"])
    if bright < 0.85:
        music_b = np.vstack(
            [
                resonant_lpf(music_b[0], 6200, 0.7),
                resonant_lpf(music_b[1], 6200, 0.7),
            ]
        )
    # bright path: leave as-is (previous HPF blend was expensive for little gain)

    # Musical dotted-8th / quarter delay — keep mix/feedback low so it doesn't comb-filter
    delay_mix = min(0.14, float(producer["delay"]) * 0.45 * profile.delay_mix_scale)
    if delay_mix > 0.02:
        music_b = delay_stereo(
            music_b,
            time_s=(60.0 / bp.bpm) * (1.0 if style in {"lofi", "slow"} else 0.75),
            feedback=0.18 if not profile.light_fx else 0.1,
            mix=delay_mix,
            ping_pong=style in {"trance", "hifi"} and not profile.light_fx,
        )
    reverb_mix = min(0.16, float(producer["reverb"]) * 0.5 * profile.reverb_mix_scale)
    if reverb_mix > 0.02:
        music_b = schroeder_reverb(
            music_b, mix=reverb_mix, decay=0.48 if not profile.light_fx else 0.35
        )
    # Mild width only — heavy side gain + delay was flange-like
    music_b = widen(music_b, amount=min(0.18, float(producer["width"]) * 0.4))

    if float(producer["dirt"]) > 0.2:
        dirt = float(producer["dirt"])
        bass_b = saturate(bass_b.astype(np.float64), 1.0 + dirt).astype(np.float32)
        drums_b = saturate(drums_b.astype(np.float64), 1.0 + 0.4 * dirt).astype(np.float32)

    mix = drums_b.astype(np.float64) + bass_b.astype(np.float64) + music_b + fx_b.astype(np.float64)

    # Highpass rumble
    mix = np.vstack(
        [
            biquad_filter(mix[0], 28, kind="highpass"),
            biquad_filter(mix[1], 28, kind="highpass"),
        ]
    )
    mix = rms_normalize(mix, target_db=-13.5)
    mix = limiter(soft_clip(mix * 1.05, 0.98), 0.97)

    # Very subtle tape wow (stronger amounts read as flanger/chorus)
    if style in {"lofi", "slow"} or bp.producer == "tape":
        t = time_axis(n)
        wow = 1.0 + 0.0006 * np.sin(2 * np.pi * 0.22 * t)
        idx = np.clip((np.arange(n) * wow).astype(np.int64), 0, n - 1)
        mix = mix[:, idx]

    pcm = to_int16_stereo(mix)
    sr = get_sr()
    meta = {
        "duration": mix.shape[1] / sr,
        "bpm": bp.bpm,
        "key": _key_name(bp.key, bp.scale),
        "style": bp.style,
        "tags": bp.tags,
        "producer": bp.producer,
        "producerLabel": bp.producer_label,
        "title": bp.title,
        "bars": bp.bars,
        "sampleRate": sr,
        "profile": profile.name,
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


def render_wav_bytes(pcm: bytes, sample_rate: int | None = None) -> bytes:
    import wave
    from io import BytesIO

    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate or get_sr()))
        wf.writeframes(pcm)
    return buf.getvalue()
