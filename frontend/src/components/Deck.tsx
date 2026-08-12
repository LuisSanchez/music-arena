import type { Track } from "../lib/api";

type Props = {
  side: "A" | "B";
  track: Track | null;
  current: number;
  duration: number;
  live: boolean;
  revealed: boolean;
  faster: boolean;
  canVote: boolean;
  onPlayPause: () => void;
  onStop: () => void;
  onSeek: (ratio: number) => void;
  onVote: () => void;
};

function fmt(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function Deck({
  side,
  track,
  current,
  duration,
  live,
  revealed,
  faster,
  canVote,
  onPlayPause,
  onStop,
  onSeek,
  onVote,
}: Props) {
  const total = duration || track?.duration || 0;
  const pct = total > 0 ? Math.min(100, (current / total) * 100) : 0;

  function handleScrub(clientX: number, el: HTMLElement) {
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0) return;
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    onSeek(ratio);
  }

  return (
    <article className="card" data-side={side} data-live={live}>
      <div className="card-top">
        <span className="side-tag">Track {side}</span>
        <div className="eq" aria-hidden>
          <i />
          <i />
          <i />
          <i />
          <i />
        </div>
        <span className="meta-chip">
          {track ? (
            <>
              {track.bpm.toFixed(1)} bpm
              {faster ? <em> · faster</em> : null}
            </>
          ) : (
            "—"
          )}
        </span>
      </div>

      <div className="player">
        <button
          className="play"
          type="button"
          aria-label={live ? `Pause track ${side}` : `Play track ${side}`}
          aria-pressed={live}
          disabled={!track}
          onClick={onPlayPause}
        >
          <svg viewBox="0 0 24 24" aria-hidden>
            <path className="ic-play" d="M8 5v14l11-7z" />
            <g className="ic-pause">
              <rect x="6" y="5" width="4" height="14" rx="1" />
              <rect x="14" y="5" width="4" height="14" rx="1" />
            </g>
          </svg>
        </button>
        <div className="wave-wrap">
          <div
            className="scrub"
            role="slider"
            tabIndex={0}
            aria-label={`Seek track ${side}`}
            aria-valuemin={0}
            aria-valuemax={Math.round(total)}
            aria-valuenow={Math.round(current)}
            onClick={(e) => handleScrub(e.clientX, e.currentTarget)}
            onKeyDown={(e) => {
              if (!total) return;
              if (e.key === "ArrowRight") onSeek(Math.min(1, (current + 2) / total));
              if (e.key === "ArrowLeft") onSeek(Math.max(0, (current - 2) / total));
            }}
          >
            <i style={{ width: `${pct}%` }} />
          </div>
          <div className="time-row">
            <span>
              {fmt(current)} / {fmt(total)}
            </span>
            <span>{track?.key ?? "key sealed"}</span>
          </div>
        </div>
      </div>

      <div className="card-foot">
        {revealed && track?.producer ? (
          <div className="reveal-line">
            {track.producer} · {track.title} · {track.style}
          </div>
        ) : null}
        <div className="card-actions">
          <button className="btn-ghost" type="button" disabled={!track} onClick={onStop}>
            stop
          </button>
        </div>
        <button className="btn-vote" type="button" disabled={!canVote} onClick={onVote}>
          {side} takes it
        </button>
      </div>
    </article>
  );
}
