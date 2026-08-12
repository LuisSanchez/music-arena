# Engine — AGENTS

Procedural electronic synthesis: **compose** a timed hit list, then **render** to stereo WAV.

## Pipeline

```
seed + pace + bias + producer
        ↓
compose_track  →  Blueprint { bpm, key, scale, style, rhythm, hits[] }
        ↓
render_blueprint → buses (drums / bass / music / fx) → sidechain → FX → limiter
        ↓
render_wav_bytes → audio/wav bytes
```

## Modules

| File | Responsibility |
|------|----------------|
| `generate.py` | Match pairing: two producers, two styles (prefer different), two rhythm profiles, one side always faster BPM |
| `compose.py` | Arrangement: form sections, kick/snare/hat maps per rhythm, bass patterns, pads/leads/FX hits |
| `render.py` | Instrument synthesis (supersaw, FM keys, bass, etc.), bus mix, sidechain ducking, delay/reverb |
| `theory.py` | Scales, progressions, producer character tables, `PACE_TABLE` BPM/style ranges |
| `drums.py` | Kick, snare, clap, hat, ride, perc, vinyl crackle one-shots |
| `dsp.py` | Sample rate (44100), filters, envelopes, stereo delay/reverb, limiter, int16 export |

## Important constants / helpers

- **Sample rate:** `dsp.SR = 44100`
- **Length:** `bars_for_duration(bpm, target_sec=90)` in `compose.py` snaps bars (multiple of 4, clamped 28–64)
- **Form:** `form_sections(bars)` → intro / breakdown / roll / drop bar indices (scales with length)
- **Rhythms:** `straight | broken | shuffle | half_time | double_hat | minimal`
- **Styles:** `trance | dance | lofi | slow | hifi`
- **Producers:** apex, nimbus, warehouse, tape, voltage, halo (mix personality, not AI models)

## Hit model

```python
Hit(beat, duration, pitch, velocity, voice, pan=0, extra=0)
```

Voices include: `kick`, `snare`, `clap`, `hat`, `hat_open`, `ride`, `rim`, `shaker`, `tom`, `bass`, `pad`, `lead`, `arp`, `stab`, `keys`, `riser`, `crash`, `impact`, `crackle`.

## Product constraints (current)

1. **No snare-roll bursts** — dense pre-drop snare machine-gun fills are intentionally absent.
2. **~90s tracks** — prefer adjusting `target_sec` / `bars_for_duration`, not hardcoding 16/32 bars in callers.
3. **Independent A/B** — `generate_match` picks distinct rhythm profiles; styles prefer different when pace allows.
4. **One side faster** — `faster=True/False` biases BPM within style range.

## Changing the music

- **Groove only:** kick/snare/hat maps in `_drums`, bass patterns in `_bass`
- **Structure only:** `form_sections` and drop/lead gating in `_lead` / `_fx`
- **Sound design only:** `render.py` instrument functions + producer table in `theory.py`
- **New pace:** extend `PACE_TABLE` and frontend `PACES` list together

## Debugging a bad sound

1. Generate one track with a fixed seed and write WAV:

```python
from app.engine.generate import generate_track
t = generate_track(seed=1, pace="trance", faster=True, bias_styles=None, producer="apex")
open("/tmp/out.wav", "wb").write(t["wav"])
print(t["meta"])
```

2. Inspect blueprint hit counts by `voice` if something is too dense.
3. Check sidechain / limiter in `render_blueprint` if overall level is crushed.
