"""Quality profiles: arena (full duel cuts) vs radio (cheap continuous stream)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityProfile:
    name: str
    sample_rate: int
    target_sec: float
    supersaw_voices_pad: int
    supersaw_voices_lead: int
    detune_pad: float
    detune_lead: float
    delay_mix_scale: float
    reverb_mix_scale: float
    thin_parts: bool  # fewer arps/leads
    light_fx: bool  # skip second FX, softer sidechain
    rhythms: tuple[str, ...]


ARENA = QualityProfile(
    name="arena",
    sample_rate=32_000,
    target_sec=120.0,
    supersaw_voices_pad=3,
    supersaw_voices_lead=4,
    detune_pad=5.0,
    detune_lead=7.0,
    delay_mix_scale=1.0,
    reverb_mix_scale=1.0,
    thin_parts=False,
    light_fx=False,
    rhythms=("straight", "broken", "shuffle", "half_time", "minimal"),
)

RADIO = QualityProfile(
    name="radio",
    sample_rate=22_050,
    target_sec=55.0,
    supersaw_voices_pad=2,
    supersaw_voices_lead=2,
    detune_pad=3.0,
    detune_lead=4.0,
    delay_mix_scale=0.35,
    reverb_mix_scale=0.4,
    thin_parts=True,
    light_fx=True,
    rhythms=("straight", "shuffle", "minimal", "half_time"),
)

STATIONS = ("slow", "lofi", "dance", "trance", "hifi")
