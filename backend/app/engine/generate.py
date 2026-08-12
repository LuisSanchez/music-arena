"""Public entry: build a unique A/B clash from pace + preference bias."""

from __future__ import annotations

from typing import Any

import numpy as np

from .compose import compose_track, pick_style
from .render import render_blueprint, render_wav_bytes
from .theory import PACE_TABLE, PRODUCERS

PRODUCER_IDS = list(PRODUCERS.keys())


def generate_track(
    seed: int,
    pace: str,
    faster: bool,
    bias_styles: list[str] | None,
    producer: str,
    key: int | None = None,
    scale: str | None = None,
    bars: int | None = None,
    style: str | None = None,
    rhythm: str | None = None,
    target_sec: float = 90.0,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    blueprint = compose_track(
        rng,
        pace=pace,
        faster=faster,
        bias_styles=bias_styles,
        producer=producer,
        key=key,
        scale=scale,
        bars=bars,
        style=style,
        rhythm=rhythm,
        target_sec=target_sec,
    )
    _mix, payload = render_blueprint(blueprint, rng)
    wav = render_wav_bytes(payload["pcm"])
    return {
        "wav": wav,
        "meta": payload["meta"],
        "blueprint": blueprint,
    }


def generate_match(
    seed: int,
    pace: str = "auto",
    bias_styles: list[str] | None = None,
    bars: int | None = None,
    target_sec: float = 90.0,
) -> dict[str, Any]:
    """Two independent cuts: different song, different tempo, different rhythm."""
    rng = np.random.default_rng(seed)
    producers = list(PRODUCER_IDS)
    rng.shuffle(producers)
    a_prod, b_prod = producers[0], producers[1]

    style_a = pick_style(rng, pace, bias_styles)
    style_b = pick_style(rng, pace, bias_styles)
    # Prefer different styles so the groove clashes, not a tempo remake
    if style_b == style_a:
        allowed = list(PACE_TABLE.get(pace, PACE_TABLE["auto"])["styles"])
        others = [s for s in allowed if s != style_a]
        if others:
            style_b = str(rng.choice(others))

    # Distinct rhythm engines even when style collides
    profiles = ["straight", "broken", "shuffle", "half_time", "double_hat", "minimal"]
    rng.shuffle(profiles)
    rhythm_a, rhythm_b = profiles[0], profiles[1]

    # One deck is the faster cut; songs stay independent otherwise
    a_fast = bool(rng.random() < 0.5)

    track_a = generate_track(
        seed=int(rng.integers(1, 2**31 - 1)),
        pace=pace,
        faster=a_fast,
        bias_styles=bias_styles,
        producer=a_prod,
        key=None,
        scale=None,
        bars=bars,
        style=style_a,
        rhythm=rhythm_a,
        target_sec=target_sec,
    )
    track_b = generate_track(
        seed=int(rng.integers(1, 2**31 - 1)),
        pace=pace,
        faster=not a_fast,
        bias_styles=bias_styles,
        producer=b_prod,
        key=None,
        scale=None,
        bars=bars,
        style=style_b,
        rhythm=rhythm_b,
        target_sec=target_sec,
    )

    # Hard guarantee: tempos must differ (re-roll B tempo side if equal)
    if abs(track_a["meta"]["bpm"] - track_b["meta"]["bpm"]) < 0.5:
        track_b = generate_track(
            seed=int(rng.integers(1, 2**31 - 1)),
            pace=pace,
            faster=not a_fast,
            bias_styles=bias_styles,
            producer=b_prod,
            key=None,
            scale=None,
            bars=bars,
            style=style_b,
            rhythm=rhythm_b,
            target_sec=target_sec,
        )

    night = int(rng.integers(4, 48))
    return {
        "roundTitle": f"NIGHT SHIFT {night:02d}",
        "sealed": True,
        "pace": pace,
        "biasStyles": bias_styles or [],
        "trackA": track_a,
        "trackB": track_b,
    }
