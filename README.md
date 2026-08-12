# CLASH

A local electronic **soundclash**. The backend procedurally writes two unique cuts for your session — different songs, different tempos, different rhythms. You listen A and B, vote for the stack that hits, or let autoplay rinse itself.

Nothing is persisted on the server. Your ear (vote history and a 3-in-a-row style lock) lives in browser `localStorage`.

## Run it

### Docker Compose (recommended for a full local stack)

```bash
docker compose up --build
```

Open [http://localhost:8080](http://localhost:8080).  
API is also on [http://localhost:8000](http://localhost:8000) (`/api/health`).

Stop with `Ctrl+C` or `docker compose down`.

### Dev servers (hot reload)

```bash
# install (once)
npm install
npm --prefix frontend install
python3 -m pip install -r backend/requirements.txt

# both servers
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

API: `http://127.0.0.1:8000` · Web: `http://127.0.0.1:5173` (proxies `/api`).

### Separate terminals

```bash
# terminal 1 — API
cd backend
python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# terminal 2 — UI
cd frontend
npm run dev
```

## Modes

- **Arena** — blind A/B soundclash (higher quality ~120s cuts, vote).
- **Radio** — continuous station on **one** style (not Auto). Medium–low quality (~55s, 22 kHz) so the backend can keep a warm queue without burning CPU/RAM.

## How a clash works (Arena)

1. Pick a pace: **Slow**, **Lo-fi**, **Dance**, **Trance**, **Hi-fi**, or **Auto**.
2. The desk presses two **independent** tracks (~120s each) — different composition, tempo, and rhythm engine.
3. Use play / pause / stop / seek on each stack; master volume and autoplay live in the center column.
4. Vote after hearing both. Choosing a winner **keeps that cut playing** (it is not skipped).
5. Three wins in the same lane lock the next press toward that lane (local only).
6. About **30s after** a pair starts, the next pair is pre-generated so the following session is ready.

## How Radio works

1. Switch to **Radio** in the nav.
2. Pick a station (Trance, Dance, … — **no Auto**).
3. **Go on air** — the API serves cheap continuous cuts and keeps ~4 warming in the background.
4. Skip anytime; the client buffers 3–4 tracks ahead for a smooth handoff.

Engines follow electronic patterns — 4-on-the-floor, broken kick, half-time, shuffle, dense hats, rolling bass, gated supersaw, house stabs, dusty lo-fi keys — randomized so no two cuts match. Dense snare-roll “machine gun” fills are intentionally disabled.

## Repo map

| Path | Role |
|------|------|
| [`AGENTS.md`](./AGENTS.md) | Full orientation for coding agents |
| [`backend/`](./backend/) | FastAPI + procedural synthesis |
| [`frontend/`](./frontend/) | React arena UI |

## Deploy (GitHub → Vercel + separate API)

The **UI** goes on **Vercel**. The **API** (track synthesis) needs a long-running host (Fly / Railway / Render) — not Vercel serverless.

See **[DEPLOY.md](./DEPLOY.md)** for the full checklist (`VITE_API_URL`, `CORS_ORIGINS`, Docker).

## Stack

- Backend: Python, FastAPI, NumPy, SciPy  
- Frontend: React 19, TypeScript, Vite 6  
