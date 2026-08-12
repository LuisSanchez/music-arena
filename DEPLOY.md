# Deploy: GitHub + Vercel (UI) + always-on API

## Local Docker

```bash
docker compose up --build
# UI  http://localhost:8080  (nginx → /api → api:8000)
# API http://localhost:8000
```

| Service | Image | Role |
|---------|--------|------|
| `api` | `backend/Dockerfile` | FastAPI synthesis |
| `web` | `frontend/Dockerfile` | Vite build + nginx, proxies `/api` |

For production split (Vercel UI + remote API), see below. Compose is the local full-stack path.

---

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

## 2. Deploy the API on Railway (recommended for this monorepo)

The repo root is a monorepo (`backend/` + `frontend/`). Railway must build **only** the API.

### Fix for `service config at '/backend' not found`

That error almost always means the **Root Directory** (or config path) is wrong:

| Wrong | Right |
|-------|--------|
| `/backend` (leading slash) | `backend` |
| Config path pointing at a missing folder | Leave default, or use `backend/railway.toml` |
| Root Directory empty **and** dockerfile path `Dockerfile` | Either set root to `backend`, **or** keep root empty and dockerfile = `backend/Dockerfile` |

### Dashboard setup (pick one approach)

**Option A — Root Directory = `backend` (simplest)**

1. New Project → Deploy from GitHub → select `music-arena`.
2. Service settings:
   - **Root Directory:** `backend` (no leading `/`)
   - **Builder:** Dockerfile  
   - **Dockerfile path:** `Dockerfile` (relative to that root)
3. Variables:

| Variable | Value |
|----------|--------|
| `CORS_ORIGINS` | `https://your-app.vercel.app` (comma-separate previews if needed) |
| `PORT` | leave unset — Railway injects it |

4. Generate domain (Settings → Networking → Public Domain).
5. Health: `https://YOUR-RAILWAY-DOMAIN/api/health` → `{"ok":"clash"}`.

Config-as-code lives at [`backend/railway.toml`](./backend/railway.toml).

**Option B — Root Directory empty (repo root)**

1. Root Directory: *(blank)*
2. Dockerfile path: `backend/Dockerfile`
3. Use root [`railway.toml`](./railway.toml) or set the same paths in the UI.

### RAM

Plan for **≥1 GB** (NumPy/SciPy + ~120s WAVs). Generation can take several seconds per match; radio cuts are cheaper.

### Fly.io alternative

```bash
cd backend
fly launch --name clash-api --region iad --no-deploy
fly secrets set CORS_ORIGINS="https://your-app.vercel.app"
fly deploy
```

---

## 3. Deploy the frontend on Vercel

### Fix for `frontend/frontend/package.json` ENOENT

That means **Root Directory is already `frontend`** but the install command still runs  
`npm --prefix frontend install` → looks for `frontend/frontend/package.json`.

**Use this setup (recommended):**

| Setting | Value |
|---------|--------|
| **Root Directory** | `frontend` (no leading slash) |
| **Install Command** | `npm install` — or leave empty to use `frontend/vercel.json` |
| **Build Command** | `npm run build` |
| **Output Directory** | `dist` |
| **Framework Preset** | Vite |

In the Vercel dashboard:

1. Project → **Settings → General → Root Directory** → `frontend` → Save  
2. **Settings → Build & Development Settings**  
   - Turn **Override** off for Install/Build/Output (so `frontend/vercel.json` applies), **or** set the values above explicitly  
3. **Settings → Environment Variables** (Production + Preview):

| Name | Value |
|------|--------|
| `VITE_API_URL` | `https://your-api.up.railway.app` (your Railway public URL, no trailing slash) |

4. Redeploy.

**Alternative monorepo root:** leave Root Directory **empty**, use root `vercel.json` (`npm install --prefix frontend`, output `frontend/dist`). Do **not** combine empty root with a `frontend` prefix *and* Root Directory = `frontend`.

5. On Railway, set:

```text
CORS_ORIGINS=https://your-app.vercel.app
```

(comma-separate preview hosts if you need them.)

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
