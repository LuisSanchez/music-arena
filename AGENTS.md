# AGENTS.md — orientation for coding agents

This file is the map for any agent (or human) working in **music-arena / CLASH**.

## What this product is

**CLASH** is a local electronic **soundclash arena** (inspired by [EDMBench](https://edmbench.com/)):

- Backend **procedurally synthesizes** two independent stereo WAV tracks per match (~90s each).
- Tracks differ in **song, tempo, and rhythm engine** (not the same cut at two BPMs).
- Frontend is a blind A/B arena: play/pause, seek, volume, autoplay, vote, ear-lock prefs.
- **No server-side persistence.** Sessions live in memory (TTL ~2h). User prefs use `localStorage`.

Product name in the UI: **CLASH**. Repo folder: `music-arena`.

## Quick start

```bash
# from repo root — both servers
npm install                 # root: concurrently
npm --prefix frontend install
python3 -m pip install -r backend/requirements.txt

npm run dev                 # API :8000 + Vite :5173
```

Or separately:

```bash
# API
cd backend && python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Web (proxies /api → :8000)
cd frontend && npm run dev -- --host 127.0.0.1 --port 5173
```

Open http://127.0.0.1:5173

## Repository layout

```
music-arena/
├── AGENTS.md                 ← you are here
├── README.md                 ← human-facing product overview
├── package.json              ← root scripts: dev / dev:api / dev:web
├── .gitignore
├── backend/                  ← FastAPI + procedural audio engine
│   ├── AGENTS.md
│   ├── requirements.txt
│   └── app/
│       ├── main.py           ← HTTP API
│       ├── store.py          ← in-memory sessions / WAVs
│       └── engine/           ← compose → render → WAV
│           ├── AGENTS.md
│           ├── generate.py   ← public entry: generate_match / generate_track
│           ├── compose.py    ← blueprints, drums, bass, form
│           ├── render.py     ← DSP → int16 stereo PCM → WAV
│           ├── theory.py     ← scales, progressions, producers, paces
│           ├── drums.py      ← one-shot drums
│           └── dsp.py        ← filters, reverb, mix helpers
└── frontend/                 ← React + Vite arena UI
    ├── AGENTS.md
    ├── package.json
    ├── vite.config.ts        ← proxies /api → localhost:8000
    └── src/
        ├── App.tsx           ← match lifecycle, autoplay, prefetch, votes
        ├── components/       ← Deck, Scope
        ├── lib/              ← api.ts, prefs.ts
        └── styles/global.css ← synthwave / EDMBench-inspired UI
```

## Architecture (one match)

```
User picks pace → POST /api/match
       ↓
generate_match(seed, pace, bias_styles, target_sec≈90)
  → two generate_track(...) calls (different style/rhythm/BPM/producer)
  → compose_track → render_blueprint → WAV bytes
       ↓
In-memory session stores track A/B WAV + meta
       ↓
Frontend plays A then B (or manual transport)
       ↓
POST /api/vote → reveal producers/titles; localStorage ear lock
```

### Key product rules (do not casually reverse)

| Rule | Detail |
|------|--------|
| Independent cuts | A and B are different songs, tempos, and rhythm engines |
| ~90s length | Bar count from BPM via `bars_for_duration` (~90s target) |
| No snare roll | Dense snare-burst fills were removed from all styles |
| Vote keeps winner | Choosing A/B does **not** stop the winner; it plays out |
| Prefetch | 30s after a match starts, next pair is generated + audio warmed |
| Ear lock | 3 wins in a row with shared style tags → bias next generation |
| Sealed until vote | Producer/title/style hidden until vote |

## API surface

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Liveness |
| POST | `/api/session` | New session id |
| POST | `/api/match` | Body: `{ sessionId?, pace, bias? }` → pair + audio URLs |
| GET | `/api/audio/{track_id}` | WAV bytes (`audio/wav`, no-store) |
| POST | `/api/vote` | Body: `{ sessionId, matchId, choice: A\|B\|skip }` → reveal |

Paces: `auto | slow | lofi | hifi | trance | dance`.

CORS allows Vite on `5173` / `4173`. Frontend always talks to `/api/*` (Vite proxy).

## Frontend localStorage keys

| Key | Meaning |
|-----|---------|
| `clash.ear.v1` | Vote history + locked style tags |
| `clash.autoplay.v1` | `"1"` / `"0"` |
| `clash.volume.v1` | 0–1 float string |

## Stack

- **Backend:** Python 3.11+, FastAPI, uvicorn, NumPy, SciPy
- **Frontend:** React 19, TypeScript, Vite 6
- **Audio:** Server-side procedural PCM → WAV (no sample library)

## Where to change what

| Goal | Start here |
|------|------------|
| New API fields / endpoints | `backend/app/main.py`, `frontend/src/lib/api.ts` |
| Session lifetime / memory | `backend/app/store.py` |
| Match pairing / bias / length | `backend/app/engine/generate.py` |
| Groove, form, drums, bass | `backend/app/engine/compose.py` |
| Timbre / mix / reverb | `backend/app/engine/render.py`, `dsp.py`, `drums.py` |
| Scales / producers / BPM tables | `backend/app/engine/theory.py` |
| Arena UX / autoplay / prefetch | `frontend/src/App.tsx` |
| Deck player UI | `frontend/src/components/Deck.tsx` |
| Theme / layout | `frontend/src/styles/global.css` |
| Preference lock logic | `frontend/src/lib/prefs.ts` |

## Conventions

- Prefer **small, focused edits**; do not refactor unrelated modules.
- Generation is CPU-heavy (~2–5s+ per pair at 90s). Do not block the UI thread; keep work on the API.
- Do not add disk persistence for votes or tracks unless explicitly requested.
- Do not reintroduce snare-roll fills unless the user asks.
- Keep A/B **musically independent** (tempo + rhythm + composition).
- When changing compose form, keep `form_sections()` and bar counts consistent.
- Frontend must keep `createMediaElementSource` single-connect per element (StrictMode-safe).

## Testing without a browser

```bash
cd backend
python3 -c "from app.engine.generate import generate_match; m=generate_match(1,'trance'); print(m['trackA']['meta'])"
curl -s -X POST http://127.0.0.1:8000/api/match -H 'Content-Type: application/json' -d '{"pace":"lofi"}'
```

## Related docs

- [README.md](./README.md) — product pitch + run instructions
- [backend/AGENTS.md](./backend/AGENTS.md) — API + engine map
- [backend/app/engine/AGENTS.md](./backend/app/engine/AGENTS.md) — synthesis pipeline detail
- [frontend/AGENTS.md](./frontend/AGENTS.md) — UI state machine + components
