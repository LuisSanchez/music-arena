"""Harmony, scales, and producer identities for the clash engines."""

from __future__ import annotations

from dataclasses import dataclass

SCALES = {
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "harmonic": [0, 2, 3, 5, 7, 8, 11],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "major": [0, 2, 4, 5, 7, 9, 11],
}

# Each progression is a list of scale-degree triads (1-indexed) lasting one bar unless repeated.
PROGRESSIONS = {
    "trance": [
        [1, 6, 3, 7],
        [1, 6, 4, 5],
        [1, 7, 6, 7],
        [1, 3, 7, 6],
        [1, 6, 1, 7],
    ],
    "dance": [
        [1, 5, 6, 4],
        [1, 6, 3, 7],
        [6, 4, 1, 5],
        [1, 4, 6, 5],
        [2, 5, 1, 6],
    ],
    "lofi": [
        [2, 5, 1, 6],
        [1, 4, 3, 6],
        [6, 2, 5, 1],
        [1, 6, 4, 5],
        [4, 5, 1, 6],
    ],
    "slow": [
        [1, 6, 4, 5],
        [1, 3, 6, 7],
        [6, 4, 1, 5],
        [1, 7, 4, 6],
    ],
}

KEYS = [45, 47, 48, 50, 52, 53, 55, 57]  # A2 through A3-ish roots

PRODUCERS = {
    "apex": {
        "label": "Apex",
        "bright": 1.15,
        "drive": 1.2,
        "width": 0.28,
        "reverb": 0.12,
        "delay": 0.12,
        "punch": 1.15,
        "dirt": 0.1,
    },
    "nimbus": {
        "label": "Nimbus",
        "bright": 0.95,
        "drive": 0.9,
        "width": 0.32,
        "reverb": 0.18,
        "delay": 0.1,
        "punch": 0.85,
        "dirt": 0.05,
    },
    "warehouse": {
        "label": "Warehouse",
        "bright": 0.8,
        "drive": 1.35,
        "width": 0.16,
        "reverb": 0.12,
        "delay": 0.08,
        "punch": 1.25,
        "dirt": 0.32,
    },
    "tape": {
        "label": "Tape",
        "bright": 0.62,
        "drive": 1.05,
        "width": 0.12,
        "reverb": 0.14,
        "delay": 0.06,
        "punch": 0.8,
        "dirt": 0.4,
    },
    "voltage": {
        "label": "Voltage",
        "bright": 1.05,
        "drive": 1.15,
        "width": 0.2,
        "reverb": 0.1,
        "delay": 0.1,
        "punch": 1.2,
        "dirt": 0.16,
    },
    "halo": {
        "label": "Halo",
        "bright": 1.0,
        "drive": 0.95,
        "width": 0.3,
        "reverb": 0.16,
        "delay": 0.12,
        "punch": 0.9,
        "dirt": 0.06,
    },
}

PACE_TABLE = {
    "slow": {"bpm": (72, 84), "styles": ["slow", "lofi"], "family": "slow"},
    "lofi": {"bpm": (80, 94), "styles": ["lofi"], "family": "lofi"},
    "hifi": {"bpm": (126, 140), "styles": ["trance", "dance", "hifi"], "family": "hifi"},
    "trance": {"bpm": (132, 140), "styles": ["trance"], "family": "trance"},
    "dance": {"bpm": (122, 128), "styles": ["dance"], "family": "dance"},
    "auto": {"bpm": (78, 138), "styles": ["slow", "lofi", "trance", "dance", "hifi"], "family": "auto"},
}


@dataclass(frozen=True)
class Chord:
    root_midi: int
    tones: tuple[int, ...]
    degree: int


def scale_notes(root: int, scale: str, octaves: range = range(2, 6)) -> list[int]:
    degrees = SCALES[scale]
    notes = []
    for octv in octaves:
        base = root % 12 + 12 * octv
        for d in degrees:
            notes.append(base + d)
    return notes


def chord_from_degree(root: int, scale: str, degree: int, seventh: bool = False) -> Chord:
    degrees = SCALES[scale]
    idx = (degree - 1) % 7
    tones = []
    for step in (0, 2, 4, 6) if seventh else (0, 2, 4):
        tones.append(root + 12 * 3 + degrees[(idx + step) % 7] + 12 * ((idx + step) // 7))
    # keep voicing in a musical register
    while tones[0] > 64:
        tones = [t - 12 for t in tones]
    while tones[0] < 48:
        tones = [t + 12 for t in tones]
    return Chord(root_midi=tones[0], tones=tuple(tones), degree=degree)


def nearest_in_scale(midi: float, notes: list[int]) -> int:
    return min(notes, key=lambda n: abs(n - midi))
