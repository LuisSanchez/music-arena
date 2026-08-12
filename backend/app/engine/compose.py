"""Seeded composers that follow trance, dance, lo-fi, and slow-electronic patterns."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .theory import (
    PACE_TABLE,
    PRODUCERS,
    PROGRESSIONS,
    chord_from_degree,
    nearest_in_scale,
    scale_notes,
)


@dataclass
class Hit:
    beat: float
    duration: float
    pitch: int
    velocity: float
    voice: str
    pan: float = 0.0
    extra: float = 0.0


@dataclass
class Blueprint:
    seed: int
    bpm: float
    bars: int
    key: int
    scale: str
    style: str
    tags: list[str]
    producer: str
    producer_label: str
    progression: list[int]
    hits: list[Hit] = field(default_factory=list)
    swing: float = 0.0
    sidechain: float = 0.65
    title: str = ""
    rhythm: str = "straight"


def beats_per_bar() -> int:
    return 4


def total_beats(bars: int) -> int:
    return bars * beats_per_bar()


def form_sections(bars: int) -> dict[str, int]:
    """Scale arrangement landmarks with track length."""
    intro_end = max(2, bars // 8)
    drop_start = max(8, bars // 2)
    breakdown_start = max(4, bars // 4)
    breakdown_end = min(drop_start - 2, breakdown_start + max(2, bars // 8))
    roll_start = max(breakdown_end, drop_start - 2)
    return {
        "intro_end": intro_end,
        "breakdown_start": breakdown_start,
        "breakdown_end": breakdown_end,
        "roll_start": roll_start,
        "drop_start": drop_start,
    }


def bars_for_duration(bpm: float, target_sec: float = 90.0) -> int:
    """Pick a bar count so the cut lands near target_sec at this tempo."""
    raw = target_sec * float(bpm) / 240.0  # 4/4: bars = sec * bpm / (4*60)
    # Snap to a multiple of 4 so form sections stay clean
    bars = int(round(raw / 4.0) * 4)
    return int(np.clip(bars, 28, 64))


def pick_style(rng: np.random.Generator, pace: str, bias_styles: list[str] | None) -> str:
    table = PACE_TABLE.get(pace, PACE_TABLE["auto"])
    allowed = list(table["styles"])
    if bias_styles:
        preferred = [s for s in bias_styles if s in allowed or s in PACE_TABLE]
        # Map user tags onto engine styles
        mapped = []
        for s in preferred:
            if s in allowed:
                mapped.append(s)
            elif s == "hifi" and pace in {"auto", "hifi"}:
                mapped.extend(["trance", "dance", "hifi"])
            elif s == "slow" and pace in {"auto", "slow"}:
                mapped.append("slow")
        if mapped:
            # Strong bias: 80% preferred
            if rng.random() < 0.82:
                return str(rng.choice(mapped))
    return str(rng.choice(allowed))


def pick_bpm(rng: np.random.Generator, pace: str, style: str, faster: bool) -> float:
    style_bpm = {
        "trance": (132, 140),
        "dance": (122, 128),
        "lofi": (80, 94),
        "slow": (72, 84),
        "hifi": (128, 140),
    }
    lo, hi = style_bpm.get(style, PACE_TABLE.get(pace, PACE_TABLE["auto"])["bpm"])
    if pace == "slow" and style in {"lofi", "slow"}:
        lo, hi = 72, 84
    elif pace == "hifi" and style in {"trance", "dance", "hifi"}:
        lo, hi = max(lo, 126), max(hi, 138)
    span = hi - lo
    if faster:
        return float(np.round(lo + span * rng.uniform(0.62, 1.0), 1))
    return float(np.round(lo + span * rng.uniform(0.0, 0.42), 1))


def chord_at(blueprint: Blueprint, beat: float):
    bar = int(beat // 4) % len(blueprint.progression)
    degree = blueprint.progression[bar]
    seventh = blueprint.style in {"lofi", "slow"}
    return chord_from_degree(blueprint.key, blueprint.scale, degree, seventh=seventh)


def add_swing(beat: float, swing: float) -> float:
    # push even 16ths later
    sixteenth = beat * 4.0
    if abs(sixteenth - round(sixteenth)) < 1e-6 and int(round(sixteenth)) % 2 == 1:
        return beat + 0.25 * swing
    return beat


def compose_track(
    rng: np.random.Generator,
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
) -> Blueprint:
    if style is None:
        style = pick_style(rng, pace, bias_styles)
    bpm = pick_bpm(rng, pace, style, faster)
    if bars is None:
        bars = bars_for_duration(bpm, target_sec=target_sec)
    if key is None:
        # A2=45 through F3=53 etc.
        key = int(rng.choice([45, 47, 48, 50, 52, 53, 55, 57]))
    if scale is None:
        if style == "trance":
            scale = str(rng.choice(["minor", "harmonic", "minor"]))
        elif style == "dance":
            scale = str(rng.choice(["minor", "dorian", "major"]))
        elif style == "lofi":
            scale = str(rng.choice(["dorian", "major", "minor"]))
        else:
            scale = str(rng.choice(["minor", "dorian"]))

    if rhythm is None:
        rhythm = str(
            rng.choice(["straight", "broken", "shuffle", "half_time", "double_hat", "minimal"])
        )

    family = "trance" if style in {"trance", "hifi"} else ("dance" if style == "dance" else ("lofi" if style == "lofi" else "slow"))
    prog = list(PROGRESSIONS[family][int(rng.integers(0, len(PROGRESSIONS[family])))])
    swing = 0.0
    if rhythm == "shuffle" or style in {"dance", "lofi"}:
        swing = float(rng.uniform(0.14, 0.28) if rhythm == "shuffle" else rng.uniform(0.12, 0.22))
    elif style == "slow" or rhythm == "half_time":
        swing = float(rng.uniform(0.06, 0.16))

    producer_meta = PRODUCERS[producer]
    tags = [style, family, rhythm]
    if bpm < 95:
        tags.append("slow")
    else:
        tags.append("hifi" if bpm >= 120 else "mid")
    if style == "lofi":
        tags.append("lofi")
    if style in {"dance", "trance"}:
        tags.append("dance" if style == "dance" else "trance")

    bp = Blueprint(
        seed=int(rng.integers(0, 2**31 - 1)),
        bpm=bpm,
        bars=bars,
        key=key,
        scale=scale,
        style=style,
        tags=sorted(set(tags)),
        producer=producer,
        producer_label=str(producer_meta["label"]),
        progression=prog,
        swing=swing,
        sidechain=0.72 if style in {"trance", "hifi", "dance"} else 0.38,
        rhythm=rhythm,
    )
    _drums(bp, rng)
    _bass(bp, rng)
    _harmony(bp, rng)
    _lead(bp, rng)
    _fx(bp, rng)
    bp.title = _title(rng, style)
    return bp


def _title(rng: np.random.Generator, style: str) -> str:
    nouns = {
        "trance": ["Horizon", "Voltage", "Halo", "Afterglow", "Rapture", "Ion", "Cascade"],
        "dance": ["Floor", "Ribbon", "Midnight", "Pulse", "Block", "Sugar", "Dock"],
        "lofi": ["Window", "Static", "Amber", "Porch", "Cassette", "Rain", "Loft"],
        "slow": ["Harbor", "Ember", "Drift", "Low Tide", "Sodium", "Hush"],
        "hifi": ["Strobe", "Peak", "Stack", "White Heat", "Rush", "Grid"],
    }
    adjectives = {
        "trance": ["Uplifted", "Sealed", "Astral", "Cold", "Open"],
        "dance": ["Wet", "Late", "Chrome", "Second", "Hot"],
        "lofi": ["Dusty", "Secondhand", "Warm", "Folded", "Night"],
        "slow": ["Deep", "Still", "Low", "Quiet", "Long"],
        "hifi": ["Hard", "Festival", "Bright", "Wide", "Peak"],
    }
    a = str(rng.choice(adjectives.get(style, adjectives["trance"])))
    n = str(rng.choice(nouns.get(style, nouns["trance"])))
    return f"{a} {n}"


def _drums(bp: Blueprint, rng: np.random.Generator) -> None:
    style = bp.style
    rhythm = bp.rhythm
    beats = total_beats(bp.bars)
    form = form_sections(bp.bars)
    # Kick placements by rhythm engine (per bar offsets)
    kick_map = {
        "straight": [0.0, 1.0, 2.0, 3.0],
        "broken": [0.0, 0.75, 1.5, 2.0, 2.75],
        "shuffle": [0.0, 1.0, 2.0, 3.0],
        "half_time": [0.0, 2.0],
        "double_hat": [0.0, 1.0, 2.0, 3.0],
        "minimal": [0.0, 2.5],
    }
    snare_map = {
        "straight": [1.0, 3.0],
        "broken": [1.0, 2.5, 3.0],
        "shuffle": [1.0, 3.0],
        "half_time": [2.0],
        "double_hat": [1.0, 3.0],
        "minimal": [1.5, 3.0],
    }
    kicks = kick_map.get(rhythm, kick_map["straight"])
    snares = snare_map.get(rhythm, snare_map["straight"])

    for beat in range(beats):
        bar = beat // 4
        intro = bar < form["intro_end"] and style != "lofi"
        breakdown = (
            style in {"trance", "hifi"}
            and form["breakdown_start"] <= bar < form["breakdown_end"]
        )
        drop = bar >= form["drop_start"] or style in {"dance", "lofi", "slow"}
        local = beat % 4

        # Kick — place when this beat hosts the kick's bar-local time
        for k in kicks:
            if int(k) != local:
                continue
            offset = k - local
            if intro and k != 0.0:
                continue
            if breakdown and k not in {0.0, 2.0}:
                continue
            vel = 1.0 if k in {0.0, 2.0} else 0.82
            if style == "slow" and rhythm != "straight" and k not in {0.0, 2.0}:
                vel *= 0.85
            bp.hits.append(Hit(float(beat) + offset, 0.4, 36, vel, "kick"))

        # Snare / clap
        if not intro:
            voice = "clap" if style in {"dance", "trance", "hifi"} and rhythm != "half_time" else "snare"
            for s in snares:
                if int(s) != local:
                    continue
                offset = s - local
                vel = 0.78 if not breakdown else 0.35
                if rhythm == "half_time":
                    vel *= 1.1
                bp.hits.append(Hit(float(beat) + offset, 0.4, 38, vel, voice))

        # Hats — density driven by rhythm engine
        if rhythm == "double_hat" or style in {"trance", "hifi"}:
            steps = (0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875) if rhythm == "double_hat" else (0.0, 0.25, 0.5, 0.75)
            for s in steps:
                if intro and s not in {0.0, 0.5}:
                    continue
                vel = 0.22 if s in {0.0, 0.5} else 0.38
                voice = "hat_open" if s in {0.5, 0.75} and rhythm != "double_hat" else "hat"
                if s == 0.5 and rhythm != "double_hat":
                    voice = "hat_open"
                bp.hits.append(
                    Hit(beat + s, 0.15, 42, vel * (0.4 if breakdown else 1), voice, pan=0.12 if s else -0.1)
                )
        elif rhythm == "minimal":
            if local in {0, 2}:
                bp.hits.append(Hit(float(beat), 0.12, 42, 0.2, "hat", pan=-0.15))
            if local == 1:
                bp.hits.append(Hit(beat + 0.5, 0.2, 46, 0.28, "hat_open", pan=0.2))
        elif rhythm == "half_time":
            bp.hits.append(Hit(float(beat), 0.12, 42, 0.18, "hat", pan=-0.1))
            if local % 2 == 0:
                bp.hits.append(Hit(beat + 0.5, 0.2, 46, 0.3, "hat_open", pan=0.18))
        elif style == "dance" or rhythm in {"straight", "broken", "shuffle"}:
            bp.hits.append(Hit(float(beat), 0.15, 42, 0.26, "hat", pan=-0.12))
            open_at = 0.5 if rhythm != "broken" else 0.75
            bp.hits.append(Hit(beat + open_at, 0.22, 46, 0.48, "hat_open", pan=0.18))
            if drop and (rhythm == "broken" or rng.random() < 0.65):
                bp.hits.append(Hit(beat + 0.75, 0.08, 42, 0.22, "hat", pan=0.3))
                bp.hits.append(Hit(beat + 0.75, 0.08, 37, 0.3, "shaker", pan=0.4))
        elif style == "lofi":
            bp.hits.append(Hit(float(beat), 0.12, 42, 0.22 + 0.08 * rng.random(), "hat", pan=-0.2))
            if beat % 2 == 0:
                bp.hits.append(Hit(beat + 0.5, 0.18, 46, 0.28, "hat_open", pan=0.22))
        else:
            if beat % 2 == 0:
                bp.hits.append(Hit(beat + 0.5, 0.2, 46, 0.25, "hat_open"))

        # Perc seasoning
        if rhythm == "broken" and beat % 4 == 3 and bar >= form["intro_end"]:
            bp.hits.append(Hit(beat + 0.75, 0.1, 37, 0.45, "rim", pan=-0.4))
        if style == "dance" and beat % 4 == 3 and bar >= form["intro_end"]:
            bp.hits.append(Hit(beat + 0.75, 0.1, 37, 0.4, "rim", pan=-0.4))
        if style == "trance" and bar >= form["drop_start"] and beat % 8 == 4:
            bp.hits.append(Hit(float(beat), 0.3, 51, 0.22, "ride", pan=0.25))
        if (style == "lofi" or rhythm == "half_time") and beat % 8 == 6 and rng.random() < 0.6:
            bp.hits.append(Hit(beat + 0.5, 0.15, 41, 0.35, "tom", pan=-0.3))

def _bass(bp: Blueprint, rng: np.random.Generator) -> None:
    style = bp.style
    rhythm = bp.rhythm
    notes = scale_notes(bp.key, bp.scale, range(1, 4))
    beats = total_beats(bp.bars)
    form = form_sections(bp.bars)

    bass_patterns = {
        "straight": [
            [0, 1, 1, 1, 0, 1, 1, 1],
            [1, 0, 1, 0, 1, 0, 1, 0],
        ],
        "broken": [
            [1, 0, 0, 1, 0, 1, 1, 0],
            [0, 1, 0, 1, 1, 0, 0, 1],
        ],
        "shuffle": [
            [1, 0, 1, 0, 1, 0, 1, 0],
            [1, 0, 0, 1, 1, 0, 0, 1],
        ],
        "half_time": [
            [1, 0, 0, 0, 1, 0, 0, 0],
            [1, 0, 0, 1, 0, 0, 1, 0],
        ],
        "double_hat": [
            [0, 1, 1, 1, 0, 1, 1, 1],
            [1, 1, 0, 1, 1, 1, 0, 1],
        ],
        "minimal": [
            [1, 0, 0, 0, 0, 0, 1, 0],
            [1, 0, 0, 0, 1, 0, 0, 0],
        ],
    }
    pattern_pool = bass_patterns.get(rhythm, bass_patterns["straight"])

    for beat in range(beats):
        bar = beat // 4
        intro = bar < form["intro_end"]
        breakdown = (
            style in {"trance", "hifi"}
            and form["breakdown_start"] <= bar < form["breakdown_end"]
        )
        if breakdown:
            continue
        chord = chord_at(bp, beat)
        root = nearest_in_scale(chord.root_midi - 24, notes)
        fifth = nearest_in_scale(root + 7, notes)
        octv = root + 12

        if style in {"trance", "hifi"} or rhythm in {"double_hat", "broken"}:
            pattern = pattern_pool[int(rng.integers(0, len(pattern_pool)))]
            step = 0.25 if rhythm != "half_time" else 0.5
            slots = 8 if step == 0.25 else 4
            for i in range(slots):
                on = pattern[i % len(pattern)]
                if not on:
                    continue
                if intro and i % 2:
                    continue
                pitch = root if i < slots // 2 else (octv if rng.random() < 0.25 else root)
                if i in {3, 7} and rng.random() < 0.35:
                    pitch = fifth
                vel = 0.7 if i % 2 else 0.55
                dur = 0.22 if step == 0.25 else 0.4
                bp.hits.append(Hit(beat + i * step, dur, pitch, vel, "bass"))
        elif style == "dance" or rhythm in {"straight", "shuffle"}:
            if rhythm == "shuffle":
                slots = [0.0, 0.75, 1.5, 2.0, 2.75, 3.5]
            elif rhythm == "broken":
                slots = [0.0, 0.75, 1.25, 2.0, 2.5, 3.25]
            else:
                slots = [0.0, 0.75, 1.5, 2.0, 2.75]
            if intro:
                slots = [0.0, 2.0]
            for s in slots:
                local = beat + s
                if local >= beats:
                    continue
                pitch = root if s in {0.0, 2.0} else (fifth if rng.random() < 0.4 else octv)
                dur = 0.7 if s in {0.0, 2.0} else 0.35
                bp.hits.append(Hit(local, dur, pitch, 0.78, "bass"))
        elif style == "lofi" or rhythm == "minimal":
            if beat % 2 == 0:
                bp.hits.append(Hit(float(beat), 1.6 if rhythm != "minimal" else 1.2, root, 0.62, "bass"))
            if beat % 4 == 2 and rng.random() < (0.35 if rhythm == "minimal" else 0.5):
                bp.hits.append(Hit(beat + 1.5, 0.4, fifth, 0.4, "bass"))
        else:
            if beat % 4 == 0:
                bp.hits.append(Hit(float(beat), 2.8, root, 0.6, "bass"))
            if beat % 4 == 2 and rng.random() < 0.4:
                bp.hits.append(Hit(float(beat) + 2, 1.4, fifth - 12 if fifth > 40 else fifth, 0.42, "bass"))


def _harmony(bp: Blueprint, rng: np.random.Generator) -> None:
    style = bp.style
    form = form_sections(bp.bars)
    for bar in range(bp.bars):
        beat = bar * 4
        chord = chord_at(bp, beat)
        breakdown = (
            style in {"trance", "hifi"}
            and form["breakdown_start"] <= bar < form["breakdown_end"]
        )
        drop = bar >= form["drop_start"]
        intro = bar < form["intro_end"]

        if style in {"trance", "hifi"}:
            # long pad, thicker on breakdown
            vel = 0.28 if not breakdown else 0.4
            for i, tone in enumerate(chord.tones):
                pan = -0.45 + 0.3 * i
                bp.hits.append(Hit(float(beat), 4.0, tone, vel, "pad", pan=pan))
            # arp 16ths after intro
            if bar >= form["intro_end"]:
                arp_tones = list(chord.tones) + [chord.tones[0] + 12]
                if rng.random() < 0.5:
                    arp_tones = arp_tones + list(reversed(arp_tones[1:-1]))
                for i in range(16):
                    tone = arp_tones[i % len(arp_tones)]
                    vel_a = 0.22 if not drop else 0.3
                    if breakdown:
                        vel_a += 0.08
                    bp.hits.append(
                        Hit(beat + i * 0.25, 0.2, tone + 12, vel_a, "arp", pan=-0.2 + 0.4 * ((i % 4) / 3))
                    )
        elif style == "dance":
            # offbeat stabs
            if intro:
                continue
            for s in (0.5, 1.5, 2.5, 3.5):
                for i, tone in enumerate(chord.tones[:3]):
                    bp.hits.append(
                        Hit(beat + s, 0.22, tone, 0.34, "stab", pan=-0.3 + 0.3 * i)
                    )
            if drop:
                for tone in chord.tones:
                    bp.hits.append(Hit(float(beat), 3.8, tone, 0.16, "pad", pan=0.2))
        elif style == "lofi":
            for i, tone in enumerate(chord.tones):
                bp.hits.append(Hit(float(beat), 3.6, tone, 0.34, "keys", pan=-0.35 + 0.25 * i))
            if bar % 2 == 1:
                bp.hits.append(Hit(beat + 2.5, 0.8, chord.tones[0] + 12, 0.22, "keys", pan=0.4))
        else:
            for i, tone in enumerate(chord.tones):
                bp.hits.append(Hit(float(beat), 4.0, tone, 0.32, "pad", pan=-0.4 + 0.3 * i))


def _lead(bp: Blueprint, rng: np.random.Generator) -> None:
    style = bp.style
    form = form_sections(bp.bars)
    notes = scale_notes(bp.key, bp.scale, range(4, 7))
    # 2-bar motif
    motif_len = 8
    contour = rng.choice([-2, -1, 0, 1, 2, 3], size=motif_len)
    start = nearest_in_scale(bp.key + 24 + int(rng.choice([0, 2, 4, 7])), notes)
    motif = []
    cur = start
    for step in contour:
        cur = nearest_in_scale(cur + int(step) * 2, notes)
        motif.append(cur)

    beats = total_beats(bp.bars)
    for beat in range(0, beats, 2):
        bar = beat // 4
        if style in {"trance", "hifi"}:
            if bar < form["drop_start"]:
                continue
            for i, pitch in enumerate(motif):
                # gated 16ths, some rests
                if rng.random() < 0.12:
                    continue
                bp.hits.append(Hit(beat + i * 0.25, 0.24, pitch, 0.55 + 0.08 * (i % 3 == 0), "lead", pan=0.05))
        elif style == "dance":
            if bar < form["intro_end"] * 2 or bar % 4 == 3:
                continue
            # shorter hook, 8ths
            for i, pitch in enumerate(motif[::2]):
                bp.hits.append(Hit(beat + i * 0.5, 0.4, pitch - 12, 0.48, "lead", pan=0.1))
        elif style == "lofi":
            if bar % 4 != 2:
                continue
            for i, pitch in enumerate(motif[:4]):
                bp.hits.append(Hit(beat + i * 0.5, 0.45, pitch - 12, 0.32, "lead", pan=0.15))
        else:
            if bar % 4 != 1:
                continue
            for i, pitch in enumerate(motif[:4]):
                bp.hits.append(Hit(beat + i * 1.0, 0.9, pitch - 12, 0.28, "lead"))


def _fx(bp: Blueprint, rng: np.random.Generator) -> None:
    form = form_sections(bp.bars)
    drop_beat = float(form["drop_start"] * 4)
    roll_beat = float(form["roll_start"] * 4)
    # riser into drop
    if bp.style in {"trance", "hifi", "dance"}:
        bp.hits.append(Hit(roll_beat, max(4.0, drop_beat - roll_beat), 0, 0.45, "riser"))
        bp.hits.append(Hit(drop_beat, 0.8, 0, 0.7, "crash"))
        if bp.bars > 8:
            bp.hits.append(Hit(drop_beat, 1.0, 0, 0.5, "impact"))
        # second lift mid-drop on longer cuts
        if bp.bars >= 28:
            mid = float((form["drop_start"] + (bp.bars - form["drop_start"]) // 2) * 4)
            bp.hits.append(Hit(mid - 4.0, 4.0, 0, 0.3, "riser"))
            bp.hits.append(Hit(mid, 0.7, 0, 0.5, "crash"))
    if bp.style == "lofi":
        bp.hits.append(Hit(0.0, float(total_beats(bp.bars)), 0, 0.5, "crackle"))
        bp.hits.append(Hit(float(form["drop_start"] * 4), 0.6, 0, 0.3, "crash"))
    if bp.style == "slow":
        bp.hits.append(Hit(0.0, float(total_beats(bp.bars)), 0, 0.25, "crackle"))
        bp.hits.append(Hit(0.0, 4.0, 0, 0.2, "riser"))
    # crash every 8 bars
    for bar in range(0, bp.bars, 8):
        if bar == 0 and bp.style in {"trance", "hifi"}:
            continue
        bp.hits.append(Hit(float(bar * 4), 1.2, 0, 0.4, "crash"))
