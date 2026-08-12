import { useEffect, useMemo, useRef, useState } from "react";
import { Deck } from "./components/Deck";
import { Scope } from "./components/Scope";
import { createMatch, createSession, voteMatch, type Match, type Pace } from "./lib/api";
import { describeLock, readEar, recordVote, type Ear } from "./lib/prefs";

type Side = "A" | "B" | null;

const PACES: { id: Pace; label: string }[] = [
  { id: "auto", label: "Auto" },
  { id: "slow", label: "Slow" },
  { id: "lofi", label: "Lo-fi" },
  { id: "dance", label: "Dance" },
  { id: "trance", label: "Trance" },
  { id: "hifi", label: "Hi-fi" },
];

const HEARD_SECONDS = 8;
const AUTOPLAY_KEY = "clash.autoplay.v1";
const VOLUME_KEY = "clash.volume.v1";
/** Warm the next pair this long after the current match starts. */
const PREFETCH_AFTER_MS = 30_000;

type PrefetchSlot = {
  match: Match;
  pace: Pace;
  lockedKey: string;
  forMatchId: string;
};

function locksKey(locked: string[]): string {
  return [...locked].sort().join(",");
}

function readAutoplay(): boolean {
  try {
    const raw = localStorage.getItem(AUTOPLAY_KEY);
    if (raw === null) return true;
    return raw === "1";
  } catch {
    return true;
  }
}

function readVolume(): number {
  try {
    const raw = localStorage.getItem(VOLUME_KEY);
    if (raw === null) return 0.85;
    const n = Number(raw);
    if (!Number.isFinite(n)) return 0.85;
    return Math.min(1, Math.max(0, n));
  } catch {
    return 0.85;
  }
}

export function App() {
  const [entered, setEntered] = useState(false);
  const [pace, setPace] = useState<Pace>("auto");
  const [ear, setEar] = useState<Ear>(() => readEar());
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [match, setMatch] = useState<Match | null>(null);
  const [pressing, setPressing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState<Side>(null);
  const [heard, setHeard] = useState({ A: false, B: false });
  const [times, setTimes] = useState({ A: 0, B: 0 });
  const [durs, setDurs] = useState({ A: 0, B: 0 });
  const [idleLeft, setIdleLeft] = useState<number | null>(null);
  const [autoplay, setAutoplay] = useState(() => readAutoplay());
  const [volume, setVolume] = useState(() => readVolume());

  const audioA = useRef<HTMLAudioElement>(null);
  const audioB = useRef<HTMLAudioElement>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sources = useRef<{ A?: MediaElementAudioSourceNode; B?: MediaElementAudioSourceNode }>({});
  const idleTimer = useRef<number | null>(null);
  const nextTimer = useRef<number | null>(null);
  const matchRef = useRef<Match | null>(null);
  const votedRef = useRef(false);
  const heardRef = useRef({ A: false, B: false });
  const lockRef = useRef<string[]>(ear.locked);
  const autoplayRef = useRef(autoplay);
  const liveRef = useRef<Side>(null);
  /** After a vote for A/B, keep that cut playing until it ends (do not auto-skip). */
  const winnerHoldRef = useRef<Side>(null);
  const paceRef = useRef(pace);
  const sessionIdRef = useRef(sessionId);
  const prefetchRef = useRef<PrefetchSlot | null>(null);
  const prefetchTimer = useRef<number | null>(null);
  const prefetchInFlight = useRef(false);
  const warmAudio = useRef<HTMLAudioElement[]>([]);

  const canVote = heard.A && heard.B && !!match && !match.voted;
  const fasterSide: Side =
    match && match.trackA.bpm !== match.trackB.bpm
      ? match.trackA.bpm > match.trackB.bpm
        ? "A"
        : "B"
      : null;

  const lockLabel = useMemo(() => describeLock(ear.locked), [ear.locked]);
  const volPct = Math.round(volume * 100);

  useEffect(() => {
    liveRef.current = live;
  }, [live]);

  useEffect(() => {
    paceRef.current = pace;
  }, [pace]);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    autoplayRef.current = autoplay;
    try {
      localStorage.setItem(AUTOPLAY_KEY, autoplay ? "1" : "0");
    } catch {
      /* ignore */
    }
    if (!autoplay) {
      if (idleTimer.current) window.clearInterval(idleTimer.current);
      setIdleLeft(null);
    }
  }, [autoplay]);

  useEffect(() => {
    if (audioA.current) audioA.current.volume = volume;
    if (audioB.current) audioB.current.volume = volume;
    try {
      localStorage.setItem(VOLUME_KEY, String(volume));
    } catch {
      /* ignore */
    }
  }, [volume]);

  useEffect(() => {
    return () => {
      if (idleTimer.current) window.clearInterval(idleTimer.current);
      if (nextTimer.current) window.clearTimeout(nextTimer.current);
      if (prefetchTimer.current) window.clearTimeout(prefetchTimer.current);
      warmAudio.current.forEach((el) => {
        el.src = "";
      });
      warmAudio.current = [];
    };
  }, []);

  async function ensureSession(existing: string | null): Promise<string> {
    if (existing) return existing;
    const id = await createSession();
    setSessionId(id);
    sessionIdRef.current = id;
    return id;
  }

  function clearPrefetchTimer() {
    if (prefetchTimer.current) {
      window.clearTimeout(prefetchTimer.current);
      prefetchTimer.current = null;
    }
  }

  function warmTrackAudio(m: Match) {
    warmAudio.current.forEach((el) => {
      el.src = "";
    });
    warmAudio.current = [m.trackA.audioUrl, m.trackB.audioUrl].map((url) => {
      const el = new Audio();
      el.preload = "auto";
      el.src = url;
      return el;
    });
  }

  function schedulePrefetch(forMatchId: string) {
    clearPrefetchTimer();
    prefetchTimer.current = window.setTimeout(() => {
      void runPrefetch(forMatchId);
    }, PREFETCH_AFTER_MS);
  }

  async function runPrefetch(forMatchId: string) {
    if (prefetchInFlight.current) return;
    // Still on the match that scheduled this warm-up?
    if (matchRef.current?.matchId !== forMatchId) return;

    const nextPace = paceRef.current;
    const locked = lockRef.current;
    const key = locksKey(locked);
    const existing = prefetchRef.current;
    if (
      existing &&
      existing.forMatchId === forMatchId &&
      existing.pace === nextPace &&
      existing.lockedKey === key
    ) {
      return;
    }

    prefetchInFlight.current = true;
    try {
      const id = await ensureSession(sessionIdRef.current);
      const next = await createMatch(id, nextPace, locked);
      // Drop if user already moved on while we were generating
      if (matchRef.current?.matchId !== forMatchId) return;
      if (paceRef.current !== nextPace) return;
      prefetchRef.current = {
        match: next,
        pace: nextPace,
        lockedKey: key,
        forMatchId,
      };
      warmTrackAudio(next);
    } catch {
      // Prefetch is best-effort; cold generate still works.
    } finally {
      prefetchInFlight.current = false;
    }
  }

  function takePrefetch(nextPace: Pace, locked: string[]): Match | null {
    const ready = prefetchRef.current;
    if (!ready) return null;
    if (ready.pace !== nextPace) return null;
    if (ready.lockedKey !== locksKey(locked)) return null;
    prefetchRef.current = null;
    return ready.match;
  }

  async function pressPair(nextPace = pace, sid = sessionId, locked = lockRef.current) {
    if (idleTimer.current) window.clearInterval(idleTimer.current);
    if (nextTimer.current) window.clearTimeout(nextTimer.current);
    clearPrefetchTimer();
    winnerHoldRef.current = null;
    stopBoth();
    setPressing(true);
    setError(null);
    setIdleLeft(null);
    heardRef.current = { A: false, B: false };
    setHeard({ A: false, B: false });
    setTimes({ A: 0, B: 0 });
    setLive(null);
    votedRef.current = false;
    try {
      const warmed = takePrefetch(nextPace, locked);
      if (warmed) {
        setSessionId(warmed.sessionId);
        sessionIdRef.current = warmed.sessionId;
        matchRef.current = warmed;
        setMatch(warmed);
        schedulePrefetch(warmed.matchId);
        return;
      }

      const id = await ensureSession(sid);
      const next = await createMatch(id, nextPace, locked);
      setSessionId(next.sessionId);
      sessionIdRef.current = next.sessionId;
      matchRef.current = next;
      setMatch(next);
      schedulePrefetch(next.matchId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "press failed");
    } finally {
      setPressing(false);
    }
  }

  function unlockAudio() {
    if (!ctxRef.current) {
      const ctx = new AudioContext();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      analyser.connect(ctx.destination);
      ctxRef.current = ctx;
      analyserRef.current = analyser;
    }
    void ctxRef.current.resume();
  }

  function connect(side: "A" | "B") {
    const el = side === "A" ? audioA.current : audioB.current;
    const ctx = ctxRef.current;
    const analyser = analyserRef.current;
    if (!el || !ctx || !analyser) return;
    if (!sources.current[side]) {
      try {
        const src = ctx.createMediaElementSource(el);
        src.connect(analyser);
        sources.current[side] = src;
      } catch {
        // Already wired from a StrictMode remount.
      }
    }
  }

  function stopSide(side: "A" | "B") {
    const el = side === "A" ? audioA.current : audioB.current;
    if (!el) return;
    el.pause();
    el.currentTime = 0;
    setTimes((prev) => ({ ...prev, [side]: 0 }));
    setLive((prev) => (prev === side ? null : prev));
    if (idleTimer.current) window.clearInterval(idleTimer.current);
    setIdleLeft(null);
  }

  function stopBoth() {
    stopSide("A");
    stopSide("B");
  }

  function playSide(side: "A" | "B") {
    unlockAudio();
    connect(side);
    const other = side === "A" ? audioB.current : audioA.current;
    const el = side === "A" ? audioA.current : audioB.current;
    other?.pause();
    if (!el) return;
    el.volume = volume;
    void el.play().then(() => setLive(side)).catch(() => setLive(side));
    if (idleTimer.current) window.clearInterval(idleTimer.current);
    setIdleLeft(null);
  }

  function playPause(side: "A" | "B") {
    const el = side === "A" ? audioA.current : audioB.current;
    if (!el) return;
    if (liveRef.current === side && !el.paused) {
      el.pause();
      setLive(null);
      return;
    }
    playSide(side);
  }

  function seekSide(side: "A" | "B", ratio: number) {
    const el = side === "A" ? audioA.current : audioB.current;
    if (!el || !Number.isFinite(el.duration) || el.duration <= 0) return;
    el.currentTime = ratio * el.duration;
    setTimes((prev) => ({ ...prev, [side]: el.currentTime }));
    markHeard(side, el);
  }

  function markHeard(side: "A" | "B", el: HTMLAudioElement) {
    const needed = Math.min(HEARD_SECONDS, (el.duration || 12) * 0.35);
    if (el.currentTime >= needed || el.ended) {
      if (!heardRef.current[side]) {
        heardRef.current = { ...heardRef.current, [side]: true };
        setHeard(heardRef.current);
      }
    }
  }

  function startIdleCountdown() {
    if (!autoplayRef.current) return;
    const current = matchRef.current;
    if (!current || current.voted || votedRef.current) return;
    let left = 10;
    setIdleLeft(left);
    if (idleTimer.current) window.clearInterval(idleTimer.current);
    idleTimer.current = window.setInterval(() => {
      left -= 1;
      setIdleLeft(left);
      if (left <= 0) {
        if (idleTimer.current) window.clearInterval(idleTimer.current);
        void onVote("skip");
      }
    }, 1000);
  }

  async function onVote(choice: "A" | "B" | "skip") {
    const current = matchRef.current;
    if (!current || !sessionId || current.voted || votedRef.current) return;
    if (choice !== "skip" && !(heardRef.current.A && heardRef.current.B)) return;
    votedRef.current = true;
    if (idleTimer.current) window.clearInterval(idleTimer.current);
    setIdleLeft(null);
    if (nextTimer.current) window.clearTimeout(nextTimer.current);

    if (choice === "skip") {
      stopBoth();
      winnerHoldRef.current = null;
    } else {
      // Keep the chosen cut playing — do not skip or cut it off.
      const loser: "A" | "B" = choice === "A" ? "B" : "A";
      stopSide(loser);
      winnerHoldRef.current = choice;
      if (liveRef.current !== choice) {
        playSide(choice);
      }
    }

    try {
      const revealed = await voteMatch(sessionId, current.matchId, choice);
      matchRef.current = revealed;
      setMatch(revealed);
      const nextEar = recordVote({
        ts: Date.now(),
        choice,
        winnerStyle: revealed.winnerStyle,
        winnerTags: revealed.winnerTags,
      });
      lockRef.current = nextEar.locked;
      setEar(nextEar);
      // Only auto-advance on skip; a selected winner plays out fully.
      if (choice === "skip" && autoplayRef.current) {
        nextTimer.current = window.setTimeout(() => {
          void pressPair(pace, sessionId, nextEar.locked);
        }, 1200);
      }
    } catch (err) {
      votedRef.current = false;
      winnerHoldRef.current = null;
      setError(err instanceof Error ? err.message : "vote failed");
    }
  }

  async function enterDock() {
    unlockAudio();
    setEntered(true);
    await pressPair();
  }

  function toggleAutoplay() {
    setAutoplay((prev) => {
      const next = !prev;
      autoplayRef.current = next;
      return next;
    });
  }

  useEffect(() => {
    const a = audioA.current;
    const b = audioB.current;
    if (!a || !b || !match) return;
    a.volume = volume;
    b.volume = volume;

    const onTime = (side: "A" | "B") => (ev: Event) => {
      const el = ev.currentTarget as HTMLAudioElement;
      setTimes((prev) => ({ ...prev, [side]: el.currentTime }));
      markHeard(side, el);
    };
    const onMeta = (side: "A" | "B") => (ev: Event) => {
      const el = ev.currentTarget as HTMLAudioElement;
      setDurs((prev) => ({ ...prev, [side]: el.duration || 0 }));
    };
    const afterWinnerEnds = () => {
      winnerHoldRef.current = null;
      setLive(null);
      if (autoplayRef.current) {
        void pressPair(pace, sessionId, lockRef.current);
      }
    };
    const onEndedA = () => {
      markHeard("A", a);
      setLive(null);
      if (winnerHoldRef.current === "A") {
        afterWinnerEnds();
        return;
      }
      if (matchRef.current?.voted || votedRef.current) return;
      if (!autoplayRef.current) return;
      if (b.readyState >= 2) playSide("B");
      else b.addEventListener("canplay", () => playSide("B"), { once: true });
    };
    const onEndedB = () => {
      markHeard("B", b);
      setLive(null);
      if (winnerHoldRef.current === "B") {
        afterWinnerEnds();
        return;
      }
      if (matchRef.current?.voted || votedRef.current) return;
      startIdleCountdown();
    };
    const kickA = () => {
      if (!match.voted && !votedRef.current && autoplayRef.current) playSide("A");
    };

    a.addEventListener("timeupdate", onTime("A"));
    b.addEventListener("timeupdate", onTime("B"));
    a.addEventListener("loadedmetadata", onMeta("A"));
    b.addEventListener("loadedmetadata", onMeta("B"));
    a.addEventListener("ended", onEndedA);
    b.addEventListener("ended", onEndedB);
    if (a.readyState >= 3) kickA();
    else a.addEventListener("canplay", kickA, { once: true });

    return () => {
      a.removeEventListener("timeupdate", onTime("A"));
      b.removeEventListener("timeupdate", onTime("B"));
      a.removeEventListener("loadedmetadata", onMeta("A"));
      b.removeEventListener("loadedmetadata", onMeta("B"));
      a.removeEventListener("ended", onEndedA);
      b.removeEventListener("ended", onEndedB);
      a.removeEventListener("canplay", kickA);
    };
  }, [match?.matchId]);

  const hint = error
    ? error
    : match?.voted
      ? match.choice === "skip"
        ? autoplay
          ? "Too close · next pair loading"
          : "Skipped · hit next pair when ready"
        : autoplay
          ? "Winner locked · finishing the cut, then next pair"
          : "Winner locked · enjoy the cut, then hit next pair"
      : !heard.A || !heard.B
        ? "Listen to both tracks to unlock voting."
        : idleLeft !== null
          ? `No hands · next matchup in ${idleLeft}s`
          : autoplay
            ? "Two different cuts. Pick the one that hits harder."
            : "Autoplay off · play each stack manually.";

  return (
    <div className="app">
      <nav className="nav">
        <div className="wordmark">
          CLA<span>SH</span>
        </div>
        <div className="nav-meta">
          <div className="bias-pill">
            ear lock
            <strong>{lockLabel}</strong>
          </div>
        </div>
      </nav>

      <div className="shell">
        <header className="matchup-head">
          <span className="chip">{match?.roundTitle ?? "waiting for a pair"}</span>
          <h1 className="track-title">Blind electronic soundclash</h1>
          <div className="pace-rail" role="tablist" aria-label="Pace">
            {PACES.map((item) => (
              <button
                key={item.id}
                type="button"
                data-on={pace === item.id}
                onClick={() => {
                  setPace(item.id);
                  paceRef.current = item.id;
                  // Pace change invalidates a warm pair for the previous lane
                  prefetchRef.current = null;
                  clearPrefetchTimer();
                  if (entered) void pressPair(item.id);
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        </header>

        <section className="deck" aria-label="Arena matchup">
          <Deck
            side="A"
            track={match?.trackA ?? null}
            current={times.A}
            duration={durs.A}
            live={live === "A"}
            revealed={!!match?.voted}
            faster={fasterSide === "A"}
            canVote={canVote}
            onPlayPause={() => playPause("A")}
            onStop={() => stopSide("A")}
            onSeek={(r) => seekSide("A", r)}
            onVote={() => void onVote("A")}
          />

          <div className="deck-mid">
            <div className="queue-flow" aria-label="Play order">
              <span className="queue-node" data-on={live === "A" || (!live && heard.A && !heard.B)}>
                A
              </span>
              <i />
              <span
                className="queue-node"
                data-side="B"
                data-on={live === "B" || (!!heard.A && heard.B && !live)}
              >
                B
              </span>
              <i />
              <span className="queue-node">Next</span>
            </div>

            <Scope analyser={analyserRef.current} live={live !== null} side={live} />

            <p className="hint" data-error={!!error}>
              {hint}
            </p>

            <button
              className="skip"
              type="button"
              disabled={!match || match.voted}
              onClick={() => void onVote("skip")}
            >
              Too close — skip
            </button>

            <div className="mid-toggles">
              <button
                type="button"
                className="autoplay-toggle"
                data-on={autoplay}
                onClick={toggleAutoplay}
                aria-pressed={autoplay}
              >
                autoplay {autoplay ? "on" : "off"}
              </button>

              <div className="vol">
                <svg viewBox="0 0 24 24" aria-hidden>
                  <path d="M3 9v6h4l5 5V4L7 9H3z" />
                  <path
                    d="M16 8a4.5 4.5 0 0 1 0 8"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                  />
                </svg>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={volPct}
                  aria-label="Volume"
                  style={{ ["--vol" as string]: `${volPct}%` }}
                  onChange={(e) => setVolume(Number(e.target.value) / 100)}
                />
                <span className="vol-pct">{volPct}</span>
              </div>
            </div>

            <div className="mid-actions">
              <button
                type="button"
                className="btn-next"
                disabled={!match}
                onClick={() => void pressPair()}
              >
                Next pair
              </button>
            </div>
          </div>

          <Deck
            side="B"
            track={match?.trackB ?? null}
            current={times.B}
            duration={durs.B}
            live={live === "B"}
            revealed={!!match?.voted}
            faster={fasterSide === "B"}
            canVote={canVote}
            onPlayPause={() => playPause("B")}
            onStop={() => stopSide("B")}
            onSeek={(r) => seekSide("B", r)}
            onVote={() => void onVote("B")}
          />
        </section>

        <p className="footer-note">
          Two independent electronic cuts — different songs, tempos, and rhythms. Your vote stays
          in this browser; three wins in the same lane lock the next pair to that sound.
        </p>
      </div>

      <audio
        ref={audioA}
        src={match ? match.trackA.audioUrl : undefined}
        preload="auto"
        crossOrigin="anonymous"
      />
      <audio
        ref={audioB}
        src={match ? match.trackB.audioUrl : undefined}
        preload="auto"
        crossOrigin="anonymous"
      />


      {!entered ? (
        <div className="gate">
          <div className="gate-card">
            <h2>CLASH</h2>
            <p>
              Two tracks. Different tempo. Different rhythm. Listen to both, then vote for the one
              that hits harder — like a nightclub soundclash, in your browser.
            </p>
            <button className="enter" type="button" onClick={() => void enterDock()}>
              Enter the arena
            </button>
          </div>
        </div>
      ) : null}

      {pressing ? (
        <div className="press">
          <div className="press-card">
            <h2>PRESS</h2>
            <p>Cutting a fresh pair for this session…</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
