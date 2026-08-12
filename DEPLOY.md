# Deploy: GitHub + Vercel (UI) + always-on API

CLASH is **two services**:

| Piece | What it is | Where it runs |
|-------|------------|----------------|
| **Frontend** | React/Vite static app | **Vercel** |
| **Backend** | FastAPI + NumPy/SciPy track synthesis | **Not Vercel** — Fly.io / Railway / Render / Docker VPS |

Why the API is not on Vercel serverless:

- Match generation is **CPU-heavy** (tens of seconds for ~90s stereo WAVs).
- Sessions hold **WAV bytes in memory** and need a **sticky long-lived process**.
- Serverless timeouts and multi-instance memory do not fit this engine.

---

## 1. Push to GitHub

```bash
git remote add origin https://github.com/<you>/music-arena.git
git push -u origin main
```

---

## 2. Deploy the API (example: Fly.io)

```bash
cd backend
# install flyctl, then:
fly launch --name clash-api --region iad --no-deploy
# set your Vercel URL after step 3 (or a temporary placeholder)
fly secrets set CORS_ORIGINS="https://your-app.vercel.app"
fly deploy
```

Railway / Render: connect the `backend/` folder, use the Dockerfile, set:

| Env | Example |
|-----|---------|
| `CORS_ORIGINS` | `https://your-app.vercel.app,https://your-app-git-main-you.vercel.app` |
| `PORT` | platform default (often `8000`) |

Health check: `GET /api/health` → `{"ok":"clash"}`.

Note the public API origin, e.g. `https://clash-api.fly.dev` (no trailing slash).

**RAM:** plan for **≥1 GB**; generation + two WAVs is memory-hungry.

---

## 3. Deploy the frontend on Vercel

1. Import the GitHub repo in Vercel.
2. Root of monorepo is fine — root `vercel.json` already points at `frontend/`.
3. **Environment variables** (Production + Preview):

| Name | Value |
|------|--------|
| `VITE_API_URL` | `https://clash-api.fly.dev` (your API origin) |

4. Deploy.

5. Update API CORS with the real Vercel URL(s):

```bash
fly secrets set CORS_ORIGINS="https://your-app.vercel.app,https://your-app-git-main-you.vercel.app"
```

Preview deployments get unique hosts — either:

- add a wildcard strategy on a host that supports it, or  
- set `CORS_ORIGINS` to include each preview you care about, or  
- use a fixed production domain only for API access.

---

## 4. Local still works

```bash
npm run dev
```

Leave `VITE_API_URL` empty so Vite proxies `/api` → `http://127.0.0.1:8000`.

---

## Security notes for public deploy

- No secrets are required in the frontend (only a public API URL).
- Protect the API with **rate limits** at the edge (Fly/Cloudflare) — `/api/match` is expensive.
- Do not expose the API without CORS locked to your Vercel origin(s).
- Sessions are in-memory: **restarting the API drops all tracks**.

---

## Quick verify

```bash
curl -s https://YOUR-API/api/health
curl -s -X POST https://YOUR-API/api/match \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://your-app.vercel.app' \
  -d '{"pace":"lofi"}' | head -c 200
```

Open the Vercel URL → enter arena → pair should press without CORS errors.
