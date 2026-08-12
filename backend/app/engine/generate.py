"""Public entry: build a unique A/B clash from pace + preference bias."""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Any

import numpy as np

from .compose import compose_track, pick_style
from .dsp import use_sample_rate
from .quality import ARENA, RADIO, STATIONS, QualityProfile
from .render import render_blueprint, render_wav_bytes
from .theory import PACE_TABLE, PRODUCERS

PRODUCER_IDS = list(PRODUCERS.keys())

# Default cut length (~2 minutes). Match generation runs A/B in parallel.
DEFAULT_TARGET_SEC = 120.0

# Process pool for true multi-core render (falls back to threads)
_proc_pool: ProcessPoolExecutor | None = None
_USE_PROCESSES = os.getenv("CLASH_PROCESS_POOL", "1") not in {"0", "false", "False"}


def _get_proc_pool() -> ProcessPoolExecutor:
    global _proc_pool
    if _proc_pool is None:
        _proc_pool = ProcessPoolExecutor(max_workers=2)
    return _proc_pool


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
    target_sec: float | None = None,
    profile: QualityProfile | None = None,
) -> dict[str, Any]:
    profile = profile or ARENA
    target_sec = float(target_sec if target_sec is not None else profile.target_sec)
    rng = np.random.default_rng(seed)
    with use_sample_rate(profile.sample_rate):
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
            thin_parts=profile.thin_parts,
            rhythm_pool=profile.rhythms,
        )
        _mix, payload = render_blueprint(blueprint, rng, profile=profile)
        wav = render_wav_bytes(payload["pcm"], sample_rate=profile.sample_rate)
    return {
        "wav": wav,
        "meta": payload["meta"],
    }


def generate_radio_track(
    seed: int,
    station: str,
    producer: str | None = None,
) -> dict[str, Any]:
    """Single low-cost cut locked to a station (no auto, no A/B)."""
    station = station.lower().strip()
    if station not in STATIONS:
        raise ValueError(f"invalid station: {station}")
    rng = np.random.default_rng(seed)
    if producer is None:
        producer = str(rng.choice(PRODUCER_IDS))
    return generate_track(
        seed=seed,
        pace=station,
        faster=bool(rng.random() < 0.5),
        bias_styles=[station],
        producer=producer,
        style=station,
        profile=RADIO,
    )


def _generate_track_job(args: dict[str, Any]) -> dict[str, Any]:
    """Picklable worker entry for ProcessPoolExecutor."""
    return generate_track(**args)


def generate_match(
    seed: int,
    pace: str = "auto",
    bias_styles: list[str] | None = None,
    bars: int | None = None,
    target_sec: float = DEFAULT_TARGET_SEC,
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
    # Prefer smoother grooves; avoid double_hat (dense metallic tick bursts)
    profiles = ["straight", "broken", "shuffle", "half_time", "minimal"]
    rng.shuffle(profiles)
    rhythm_a, rhythm_b = profiles[0], profiles[1]

    # One deck is the faster cut; songs stay independent otherwise
    a_fast = bool(rng.random() < 0.5)
    seed_a = int(rng.integers(1, 2**31 - 1))
    seed_b = int(rng.integers(1, 2**31 - 1))

    job_a = {
        "seed": seed_a,
        "pace": pace,
        "faster": a_fast,
        "bias_styles": bias_styles,
        "producer": a_prod,
        "key": None,
        "scale": None,
        "bars": bars,
        "style": style_a,
        "rhythm": rhythm_a,
        "target_sec": target_sec,
    }
    job_b = {
        "seed": seed_b,
        "pace": pace,
        "faster": not a_fast,
        "bias_styles": bias_styles,
        "producer": b_prod,
        "key": None,
        "scale": None,
        "bars": bars,
        "style": style_b,
        "rhythm": rhythm_b,
        "target_sec": target_sec,
    }

    def _run_parallel(executor_cls, job_fn):
        with executor_cls(max_workers=2) as pool:
            fut_a = pool.submit(job_fn, job_a)
            fut_b = pool.submit(job_fn, job_b)
            return fut_a.result(), fut_b.result()

    track_a = track_b = None
    if _USE_PROCESSES:
        try:
            # Prefer a long-lived process pool under uvicorn; per-call pool also works
            pool = _get_proc_pool()
            fut_a = pool.submit(_generate_track_job, job_a)
            fut_b = pool.submit(_generate_track_job, job_b)
            track_a = fut_a.result()
            track_b = fut_b.result()
        except Exception:
            try:
                track_a, track_b = _run_parallel(ProcessPoolExecutor, _generate_track_job)
            except Exception:
                track_a = track_b = None
    if track_a is None or track_b is None:
        # Threads: still overlaps NumPy/SciPy work that releases the GIL
        track_a, track_b = _run_parallel(ThreadPoolExecutor, _generate_track_job)

    # Hard guarantee: tempos must differ (re-roll B tempo side if equal)
    if abs(track_a["meta"]["bpm"] - track_b["meta"]["bpm"]) < 0.5:
        job_b["seed"] = int(rng.integers(1, 2**31 - 1))
        track_b = generate_track(**job_b)

    night = int(rng.integers(4, 48))
    return {
        "roundTitle": f"NIGHT SHIFT {night:02d}",
        "sealed": True,
        "pace": pace,
        "biasStyles": bias_styles or [],
        "trackA": track_a,
        "trackB": track_b,
    }
