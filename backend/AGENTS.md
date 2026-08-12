# Backend — AGENTS

FastAPI service that **generates** electronic duel pairs and serves them as WAV for the current browser session.

## Layout

```
backend/
├── AGENTS.md
├── requirements.txt          # fastapi, uvicorn, numpy, scipy
└── app/
    ├── main.py               # routes, CORS, public DTO shaping
    ├── store.py              # MemoryStore: sessions, matches, track bytes
    └── engine/               # see engine/AGENTS.md
        ├── generate.py
        ├── compose.py
        ├── render.py
        ├── theory.py
        ├── drums.py
        └── dsp.py
```

Package import root when running from `backend/`:

```bash
python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Dependencies

See `requirements.txt`. Needs NumPy + SciPy for DSP. No database.

## Endpoints (summary)

Defined in `app/main.py`:

- `POST /api/session` → `{ sessionId }`
- `POST /api/match` → creates two tracks, returns sealed public match
- `GET /api/audio/{track_id}` → raw WAV
- `POST /api/vote` → marks match voted, returns revealed meta + winner tags
- `GET /api/health` → `{ "ok": "clash" }`

### Match body

```json
{
  "sessionId": "optional",
  "pace": "auto|slow|lofi|hifi|trance|dance",
  "bias": { "styles": ["lofi", "dance"], "strength": 0.85 }
}
```

`bias.styles` comes from frontend ear-lock (3-in-a-row). Engine uses it as a soft preference for style pick.

### Sealed vs revealed

Until vote, public track payloads hide `title`, `style`, `tags`, `producer`. BPM, key, duration, and `audioUrl` are always visible (arena needs them).

## Session store

`app/store.py`:

- In-memory only (`MemoryStore`)
- TTL purge: **2 hours** since session create
- Each session holds `matches` + `tracks` (WAV bytes in RAM)
- Missing session on match → new session is created transparently

**Implication:** restarting the API wipes all audio URLs. Frontend must re-press a pair.

## Generation entry points

| Function | File | Role |
|----------|------|------|
| `generate_match` | `engine/generate.py` | Pair of independent tracks + night title |
| `generate_track` | `engine/generate.py` | One seeded track → WAV + meta |
| `compose_track` | `engine/compose.py` | Musical blueprint (hits) |
| `render_blueprint` | `engine/render.py` | Audio bus mix → PCM |
| `render_wav_bytes` | `engine/render.py` | PCM → WAV container |

Default target length: **~90 seconds** (`target_sec=90.0` in `main.py` → `generate_match`).

## Performance notes

- 90s stereo @ 44.1kHz is heavy; pair generation is multi-second.
- Frontend prefetches the next pair 30s after a match starts so the next session feels instant.
- Avoid writing WAVs to disk in the hot path; keep them in `store`.

## Safe change checklist

1. Public JSON field renames → update `frontend/src/lib/api.ts` and `App.tsx`.
2. New styles → `theory.PACE_TABLE` + compose branches + tags for ear lock.
3. Do not add snare-roll burst fills (product decision).
4. Keep A/B independent (style/rhythm/BPM/key can all differ).
5. After API changes, restart uvicorn if not using `--reload`.

## Local smoke tests

```bash
cd backend
python3 -c "
from app.engine.generate import generate_match
m = generate_match(seed=42, pace='dance', target_sec=90)
print(m['trackA']['meta']['duration'], m['trackB']['meta']['duration'])
"
```
