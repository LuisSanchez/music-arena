# Frontend — AGENTS

React + Vite arena UI for CLASH. Talks only to `/api/*` (proxied to the FastAPI backend).

## Layout

```
frontend/
├── AGENTS.md
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts          # proxy /api → http://127.0.0.1:8000
└── src/
    ├── main.tsx
    ├── App.tsx             # match lifecycle, transport, vote, prefetch
    ├── vite-env.d.ts
    ├── components/
    │   ├── Deck.tsx        # Track A/B card: play/pause, seek, stop, vote
    │   └── Scope.tsx       # Analyser scope canvas
    ├── lib/
    │   ├── api.ts          # types + fetch helpers
    │   └── prefs.ts        # ear lock in localStorage
    └── styles/
        └── global.css      # synthwave theme (magenta/cyan/violet)
```

## Scripts

```bash
npm install
npm run dev       # Vite :5173
npm run build     # tsc + vite build
npm run preview
```

From monorepo root, `npm run dev` also starts the API via `concurrently`.

## State machine (match)

```
enter dock → pressPair (cold or warm prefetch)
    ↓
autoplay on? → play A → end → play B → end → idle skip countdown
autoplay off? → user play/stop only
    ↓
heard A + heard B (≈8s each or track end) → vote unlocked
    ↓
vote A/B → stop loser, keep winner playing → reveal → (autoplay: next when winner ends)
vote skip → stop both → (autoplay: next soon)
```

### Prefetch (important)

- **30s after** a match is installed, `schedulePrefetch` calls `POST /api/match` in the background.
- Result is cached in `prefetchRef` and audio URLs are warmed with detached `Audio` elements.
- Next `pressPair` consumes the warm match if pace + ear-lock key still match; otherwise cold generate.
- Pace change clears the warm cache.

### Winner hold

Voting for A or B must **not** cut the chosen track. `winnerHoldRef` tracks that side; when the element `ended`, then autoplay may call `pressPair`.

## Key files

| File | Notes |
|------|-------|
| `App.tsx` | All orchestration: refs for timers, prefetch, Web Audio graph, vote |
| `lib/api.ts` | `Pace`, `Track`, `Match`, `createMatch`, `voteMatch` |
| `lib/prefs.ts` | `recordVote`, `inferLock` (3 shared tags → lock) |
| `components/Deck.tsx` | Presentational player card |
| `styles/global.css` | Design tokens: `--magenta`, `--cyan`, `--violet`, dark panels |

## Web Audio caveat

`createMediaElementSource` can only be called once per HTML media element. Sources are cached on `sources.current` and failures from StrictMode remounts are swallowed.

## localStorage

| Key | Content |
|-----|---------|
| `clash.ear.v1` | `{ votes: [...], locked: string[] }` |
| `clash.autoplay.v1` | `"1"` \| `"0"` |
| `clash.volume.v1` | volume 0–1 as string |

## UI / design notes

- Baseline UX: EDMBench (two cards + center column: queue, scope, skip, volume, autoplay).
- Palette is **synthwave** (not yellow/sodium warehouse). A = cyan, B = magenta.
- Do not reintroduce yellow as the primary accent unless product asks.

## When changing API contracts

Update in lockstep:

1. `backend/app/main.py` public payload
2. `src/lib/api.ts` types
3. Any consumers in `App.tsx` / `Deck.tsx`

## Typecheck

```bash
cd frontend && npx tsc --noEmit
```
