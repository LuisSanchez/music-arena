# Plan: Radio mode (low-quality continuous electronic station)

> **Status:** Implemented on `main` (see Radio API, `quality.RADIO`, `radio_queue.py`, and `frontend/src/components/Radio.tsx`).

## Goal

Add a **Radio** experience alongside the existing A/B **Arena**:

- User picks **one** electronic lane (trance / dance / lo-fi / hi-fi / slow) — **not Auto**.
- Backend generates a **continuous stream** of that style at **medium–low quality** so CPU/RAM stay manageable.
- Queue stays ahead of the listener for a **smooth, non-blocking** experience.
- Arena remains the high(er)-quality duel mode (~120s, 32 kHz, A/B vote).

## Why a separate path (not just Arena + autoplay)

| | Arena (today) | Radio (proposed) |
|--|---------------|------------------|
| Job | Compare two cuts | Keep one station playing |
| Output | Pair A/B | Single track sequence |
| Length | ~120s | ~45–60s (cheaper, more cuts/hour) |
| Sample rate | 32 kHz | **22.05 kHz** radio profile |
| Vote | Required for product loop | Optional “like / skip” only |
| Prefetch | 1 warm pair / client | Deeper station queue + server warm |

Generating full 120s stereo arena cuts as radio would burn the box; radio must use a **quality profile**.

---

## Product UX

### Entry

Nav / gate:

- **Arena** — current clash UI  
- **Radio** — new station UI  

### Radio screen

1. **Station pick** (required, no Auto): Slow · Lo-fi · Dance · Trance · Hi-fi  
2. **On air** now-playing card: title (can unseal immediately or use “Track N”), BPM, style, progress  
3. Transport: play / pause / **skip** / volume  
4. Queue strip: `Now → Next → +2 → +3` with “warming…” states  
5. Optional: heart / “more like this” (feeds ear lock later; not required for v1)

### Continuous play rules

- Always play **one track at a time** in the chosen style.
- When current ends (or user skips), immediately play the next **already-buffered** track.
- If queue is empty, show a short “pressing vinyl…” state and play as soon as the first cut lands — never block the whole UI.
- Changing station cancels the old queue and starts warming the new lane.

### Smoothness targets

| Metric | Target |
|--------|--------|
| Time to first audio after station pick | ≤ 3–5s (cold), often &lt;1s if warm |
| Gap between tracks | 0–200ms (or short crossfade) |
| Tracks buffered ahead | **3–5** radio cuts |
| Server gen for one radio cut | ~0.5–1.5s wall time on laptop |

---

## Quality profile: `radio` (medium–low)

Introduce an engine **`QualityProfile`** so Arena and Radio share code with different knobs.

### Recommended `radio` knobs

| Knob | Arena (current) | Radio |
|------|-----------------|-------|
| `SR` | 32_000 | **22_050** |
| `target_sec` | 120 | **48–60** |
| Supersaw voices | 3–4 | **2** |
| Arps / leads density | medium | low (8ths, skip bars) |
| Delay / reverb | already reduced | off or very light |
| Sidechain | full | lighter or skip on pads |
| Rhythms | varied | prefer `straight` / `shuffle` / `minimal` (no dense ticks) |
| Output | stereo 16-bit WAV | stereo 16-bit WAV (optional mono later) |

**Cost math (order of magnitude):**  
Samples ∝ `SR × duration`. Arena ~32k×120; radio ~22k×55 → roughly **~1/3** the sample work before even counting fewer voices/hits. Two radio cuts can cost less than one arena track.

### Implementation surface

```text
engine/quality.py   # QualityProfile dataclass + ARENA / RADIO presets
generate_track(..., profile="arena"|"radio")
compose_track / render_blueprint read profile for SR, density, FX
```

`SR` is currently a module constant in `dsp.py`. Plan:

1. Keep `dsp.SR` as default.
2. Pass `sample_rate` through render (or set a thread-local / context for the job).
3. Simplest reliable approach: **`render_blueprint` accepts `sr: int`** and all `samples()` / `time_axis` use that `sr` for the call.

Avoid global mutation of `SR` under process pools.

---

## Backend API

### New endpoints

```http
POST /api/radio/session
{ "station": "trance" | "dance" | "lofi" | "hifi" | "slow" }
→ { "sessionId", "station", "queue": [ TrackPublic, ... ]  // 1–2 ready cuts if warm }

POST /api/radio/next
{ "sessionId", "station" }
→ { "track": TrackPublic, "queueDepth": n }

GET  /api/radio/status?sessionId=
→ { "station", "queueDepth", "generating": bool }

# reuse
GET  /api/audio/{track_id}
```

Notes:

- **No `auto` station.** Reject or ignore invalid values.
- Track public payload can **unseal** style/title immediately (radio is not a blind duel).
- Optional later: `POST /api/radio/skip` for analytics.

### Radio station worker (server-side)

Extend / replace the pair-focused `warm.py` with a **station queue**:

```text
RadioQueue[station] = deque of generated single tracks (disk-backed)
depth target: RADIO_WARM_DEPTH = 4  (env)
max concurrent radio gens: RADIO_WORKERS = 1  (protect CPU)
```

On `POST /api/radio/session` or `/next`:

1. Pop a ready track from that station’s deque if available.
2. Attach to session on disk via existing `store.write_track`.
3. If depth &lt; target, `schedule_radio_fill(station)` in background.
4. Never run unbounded parallel radio jobs — **one global radio generator** (or a small semaphore).

This is the main “generate as much as possible without burning the backend” lever: **depth + single worker**, not “spawn N processes per client”.

### Generation entry

```python
def generate_radio_track(seed, station: str, profile=RADIO) -> {wav, meta}
# pace/style locked to station; single track, no A/B
```

Reuse `compose_track` with `style=station`, `faster=random`, simpler rhythm.

### Resource guardrails

| Control | Default | Purpose |
|---------|---------|---------|
| `RADIO_WARM_DEPTH` | 4 | Max queued cuts per station |
| `RADIO_MAX_STATIONS_ACTIVE` | 3 | Only warm stations someone is using |
| `RADIO_WORKERS` | 1 | Serial radio production |
| `RADIO_TARGET_SEC` | 55 | Length |
| `RADIO_SR` | 22050 | Sample rate |
| Arena warm depth | keep 1 | Don’t starve arena |

When radio is active, optional: lower arena process pool workers temporarily (v2).

---

## Frontend

### New pieces

```text
src/pages or modes:
  App.tsx → mode: "arena" | "radio"
  components/Radio.tsx      # station UI
  lib/radio.ts              # API + queue state
```

### Client queue

- Maintain `queue: Track[]` (target 3–5).
- On station start: `POST /api/radio/session` then loop `next` until depth ≥ 2 or timeout.
- While playing track *i*, ensure *i+1…i+3* requested if missing.
- Preload with `new Audio(url); audio.preload = "auto"` (same as arena warm).
- On `ended` / skip: shift queue, play head, fetch more.

### Crossfade (nice-to-have v1.1)

- 1.5–2s linear crossfade between tracks using two `<audio>` elements (A/B bus already exist).
- If next not ready, hard cut with spinner — never stall mid-track.

### localStorage

```text
clash.radio.station.v1 = "trance"
clash.radio.volume.v1  = reuse volume key or separate
```

Remember last station; never default radio to Auto.

---

## Smooth experience architecture

```text
┌──────────── UI ─────────────┐     ┌────────── API ──────────┐
│ Station = trance            │     │ RadioQueue[trance]      │
│ Now playing ←───────────────┼─────│  [T1][T2][T3][T4]      │
│ Buffer: T2,T3,T4            │     │ worker: fill if &lt;4      │
│ on near-end: pull next      │     │ generate_radio_track()  │
└─────────────────────────────┘     └─────────────────────────┘
```

**Client + server double buffering:**

1. Server keeps a small station-wide pool (shared across listeners of that station — good for single-tenant self-host).
2. Client keeps private session tracks (copied/attached from pool) so skip doesn’t break other clients if multi-user later.
3. For single-user local/Vercel+API: station pool alone is enough; attach track ids to session for TTL cleanup.

---

## Phased delivery

### PR 1 — Engine quality profile + radio generator

- `QualityProfile` + `RADIO` preset (22.05 kHz, ~55s, sparse parts, light FX).
- `generate_radio_track(station, seed)`.
- Unit smoke: duration ~55s, SR 22050, gen time benchmark.

### PR 2 — Radio API + warm station queue

- Endpoints above.
- Disk-backed queue; `RADIO_*` env vars.
- `GET /api/audio` unchanged.
- Rate-limit: one radio fill job at a time.

### PR 3 — Radio UI

- Mode switch Arena | Radio.
- Station picker (no Auto).
- Continuous play + skip + queue indicator.
- Preload 3 tracks; gapless handoff.

### PR 4 — Polish

- Optional crossfade.
- “Liked” → slight bias for next radio seeds (reuse ear tags carefully).
- Status endpoint for “warming” UI.
- Docs: `DEPLOY.md` / `AGENTS.md` radio section.

---

## Files to touch (expected)

| Area | Files |
|------|--------|
| Engine | `dsp.py` or new `quality.py`, `compose.py`, `render.py`, `generate.py` |
| API | `main.py`, new `radio_queue.py` (or extend `warm.py`), `store.py` |
| UI | `App.tsx`, new `Radio.tsx`, `lib/api.ts` / `lib/radio.ts`, `global.css` |
| Ops | `.env.example`, `AGENTS.md`, `README.md` |

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Radio fills starve Arena | Cap `RADIO_WORKERS=1`; arena match stays priority path |
| Process pool + radio thrash | Radio gens use thread pool only; leave process pool for arena pairs |
| Disk fill from long radio sessions | Reuse track TTL purge; max depth per station |
| 22 kHz sounds “too bad” | Keep 32 kHz radio profile as env override `RADIO_SR` |
| User picks Auto out of habit | UI omits Auto; API 400 if sent |

---

## Success criteria

1. User can select **Trance** (etc.), hit On Air, and hear continuous music with **no multi-second gaps** after the first buffer fills.
2. One radio cut generates in **well under half** the time of a current arena track on the same machine.
3. Backend RAM stays bounded (disk queue + depth cap; no unbounded WAV lists).
4. Arena mode behavior unchanged.

---

## Out of scope (v1)

- Multi-tenant shared stations with global charts  
- True streaming codecs (HLS/Opus) — stick to WAV for simplicity  
- Offline pre-bake of hours of music  
- Auto station / multi-genre mix  
