import { useCallback, useEffect, useRef, useState } from "react";
import {
  STATIONS,
  nextRadioTrack,
  readStation,
  startRadio,
  writeStation,
  type Station,
} from "../lib/radio";
import type { Track } from "../lib/api";

const CLIENT_BUFFER = 4;
const VOLUME_KEY = "clash.volume.v1";

function fmt(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function readVolume(): number {
  try {
    const n = Number(localStorage.getItem(VOLUME_KEY));
    if (Number.isFinite(n)) return Math.min(1, Math.max(0, n));
  } catch {
    /* ignore */
  }
  return 0.85;
}

type Props = {
  onBack: () => void;
};

export function Radio({ onBack }: Props) {
  const [station, setStation] = useState<Station>(() => readStation());
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [queue, setQueue] = useState<Track[]>([]);
  const [current, setCurrent] = useState<Track | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [warming, setWarming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [volume, setVolume] = useState(() => readVolume());
  const [onAir, setOnAir] = useState(false);

  const audioRef = useRef<HTMLAudioElement>(null);
  const queueRef = useRef<Track[]>([]);
  const sessionRef = useRef<string | null>(null);
  const stationRef = useRef(station);
  const filling = useRef(false);
  const warmers = useRef<HTMLAudioElement[]>([]);

  useEffect(() => {
    queueRef.current = queue;
  }, [queue]);
  useEffect(() => {
    sessionRef.current = sessionId;
  }, [sessionId]);
  useEffect(() => {
    stationRef.current = station;
  }, [station]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = volume;
    try {
      localStorage.setItem(VOLUME_KEY, String(volume));
    } catch {
      /* ignore */
    }
  }, [volume]);

  const preload = useCallback((tracks: Track[]) => {
    warmers.current.forEach((a) => {
      a.src = "";
    });
    warmers.current = tracks.slice(0, 4).map((t) => {
      const a = new Audio();
      a.preload = "auto";
      a.crossOrigin = "anonymous";
      a.src = t.audioUrl;
      return a;
    });
  }, []);

  const fillQueue = useCallback(async () => {
    if (filling.current) return;
    const sid = sessionRef.current;
    const st = stationRef.current;
    if (!sid) return;
    if (queueRef.current.length >= CLIENT_BUFFER) return;
    filling.current = true;
    setWarming(true);
    try {
      while (queueRef.current.length < CLIENT_BUFFER) {
        const next = await nextRadioTrack(sid, st);
        if (stationRef.current !== st) break;
        setQueue((q) => {
          const nq = [...q, next.track];
          queueRef.current = nq;
          preload(nq);
          return nq;
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "fill failed");
    } finally {
      filling.current = false;
      setWarming(false);
    }
  }, [preload]);

  async function goOnAir() {
    setError(null);
    setWarming(true);
    setOnAir(true);
    writeStation(station);
    try {
      const session = await startRadio(station, sessionId);
      setSessionId(session.sessionId);
      sessionRef.current = session.sessionId;
      const [first, ...rest] = session.queue;
      setCurrent(first ?? null);
      setQueue(rest);
      queueRef.current = rest;
      preload(rest);
      setPlaying(true);
      // keep filling in background
      void fillQueue();
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not start station");
      setOnAir(false);
    } finally {
      setWarming(false);
    }
  }

  function playCurrent() {
    const el = audioRef.current;
    if (!el) return;
    void el.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
  }

  function pause() {
    audioRef.current?.pause();
    setPlaying(false);
  }

  const advance = useCallback(() => {
    setQueue((q) => {
      const [head, ...rest] = q;
      if (head) {
        setCurrent(head);
        setPlaying(true);
        queueRef.current = rest;
        preload(rest);
        return rest;
      }
      setCurrent(null);
      setPlaying(false);
      return [];
    });
    void fillQueue();
  }, [fillQueue, preload]);

  function skip() {
    advance();
  }

  useEffect(() => {
    const el = audioRef.current;
    if (!el || !current) return;
    el.src = current.audioUrl;
    el.volume = volume;
    el.load();
    if (playing) {
      void el.play().catch(() => setPlaying(false));
    }
  }, [current?.id]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const onTime = () => setTime(el.currentTime);
    const onMeta = () => setDuration(el.duration || 0);
    const onEnded = () => advance();
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("loadedmetadata", onMeta);
    el.addEventListener("ended", onEnded);
    return () => {
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("loadedmetadata", onMeta);
      el.removeEventListener("ended", onEnded);
    };
  }, [advance]);

  // Keep buffer full while on air
  useEffect(() => {
    if (!onAir || !sessionId) return;
    if (queue.length < CLIENT_BUFFER - 1) void fillQueue();
  }, [queue.length, onAir, sessionId, fillQueue]);

  const pct = duration > 0 ? Math.min(100, (time / duration) * 100) : 0;
  const volPct = Math.round(volume * 100);

  return (
    <div className="shell radio-shell">
      <header className="matchup-head">
        <div className="mode-row">
          <button type="button" className="mode-link" onClick={onBack}>
            ← Arena
          </button>
          <span className="chip">RADIO</span>
        </div>
        <h1 className="track-title">On-air electronic</h1>
        <p className="radio-sub">
          Pick one lane. Low-cost cuts keep the station warm without burning the desk.
        </p>
        <div className="pace-rail" role="tablist" aria-label="Station">
          {STATIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              data-on={station === s.id}
              disabled={onAir && warming}
              onClick={() => {
                setStation(s.id);
                writeStation(s.id);
                if (onAir) {
                  setOnAir(false);
                  setCurrent(null);
                  setQueue([]);
                  queueRef.current = [];
                  setSessionId(null);
                  sessionRef.current = null;
                  pause();
                }
              }}
            >
              {s.label}
            </button>
          ))}
        </div>
      </header>

      <section className="radio-card">
        {!onAir ? (
          <div className="radio-idle">
            <p>Station locked to <strong>{station}</strong> — no auto mix.</p>
            <button type="button" className="enter" onClick={() => void goOnAir()}>
              Go on air
            </button>
          </div>
        ) : (
          <>
            <div className="radio-now">
              <div className="side-tag" data-live={playing}>
                {playing ? "ON AIR" : "PAUSED"}
              </div>
              <h2>{current?.title ?? (warming ? "Pressing vinyl…" : "Waiting for next cut")}</h2>
              <div className="meta-chip">
                {current
                  ? `${current.style ?? station} · ${current.bpm.toFixed(0)} bpm · ${current.producer ?? "—"}`
                  : station}
              </div>
              <div
                className="scrub"
                role="slider"
                aria-valuenow={Math.round(time)}
                aria-valuemin={0}
                aria-valuemax={Math.round(duration)}
                onClick={(e) => {
                  const el = audioRef.current;
                  if (!el || !duration) return;
                  const rect = e.currentTarget.getBoundingClientRect();
                  const r = (e.clientX - rect.left) / rect.width;
                  el.currentTime = r * duration;
                }}
              >
                <i style={{ width: `${pct}%` }} />
              </div>
              <div className="time-row">
                <span>
                  {fmt(time)} / {fmt(duration || current?.duration || 0)}
                </span>
                <span>{current?.key ?? "—"}</span>
              </div>
            </div>

            <div className="radio-transport">
              <button type="button" className="play" disabled={!current} onClick={() => (playing ? pause() : playCurrent())}>
                <svg viewBox="0 0 24 24" aria-hidden>
                  {playing ? (
                    <g>
                      <rect x="6" y="5" width="4" height="14" rx="1" />
                      <rect x="14" y="5" width="4" height="14" rx="1" />
                    </g>
                  ) : (
                    <path d="M8 5v14l11-7z" />
                  )}
                </svg>
              </button>
              <button type="button" className="btn-ghost" onClick={skip}>
                Skip
              </button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => {
                  setOnAir(false);
                  pause();
                  setCurrent(null);
                  setQueue([]);
                }}
              >
                Stop station
              </button>
            </div>

            <div className="vol" style={{ maxWidth: 280, margin: "12px auto 0" }}>
              <svg viewBox="0 0 24 24" aria-hidden>
                <path d="M3 9v6h4l5 5V4L7 9H3z" />
              </svg>
              <input
                type="range"
                min={0}
                max={100}
                value={volPct}
                style={{ ["--vol" as string]: `${volPct}%` }}
                onChange={(e) => setVolume(Number(e.target.value) / 100)}
                aria-label="Volume"
              />
              <span className="vol-pct">{volPct}</span>
            </div>

            <div className="radio-queue" aria-label="Upcoming">
              <span className="queue-label">Queue</span>
              {queue.length === 0 ? (
                <span className="queue-node" data-on={warming}>
                  {warming ? "…" : "—"}
                </span>
              ) : (
                queue.map((t, i) => (
                  <span key={t.id} className="queue-node" data-on={i === 0} title={t.title}>
                    +{i + 1}
                  </span>
                ))
              )}
              {warming ? <span className="meta-chip">warming</span> : null}
            </div>
          </>
        )}

        {error ? (
          <p className="hint" data-error="true">
            {error}
          </p>
        ) : null}
      </section>

      <audio ref={audioRef} preload="auto" crossOrigin="anonymous" />
    </div>
  );
}
