export type Pace = "slow" | "lofi" | "hifi" | "trance" | "dance" | "auto";

export type Track = {
  id: string;
  audioUrl: string;
  duration: number;
  bpm: number;
  key: string;
  title: string;
  style: string | null;
  tags: string[];
  producer: string | null;
};

export type Match = {
  sessionId: string;
  matchId: string;
  roundTitle: string;
  pace: Pace;
  sealed: boolean;
  trackA: Track;
  trackB: Track;
  voted: boolean;
  choice: "A" | "B" | "skip" | null;
  winnerTags?: string[];
  winnerStyle?: string | null;
};

/**
 * Empty in local dev (Vite proxies `/api` → :8000).
 * On Vercel set VITE_API_URL to the public API origin, e.g. https://clash-api.example.com
 */
const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";

function apiUrl(path: string): string {
  if (!path) return path;
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

function withAbsoluteAudio(match: Match): Match {
  return {
    ...match,
    trackA: { ...match.trackA, audioUrl: apiUrl(match.trackA.audioUrl) },
    trackB: { ...match.trackB, audioUrl: apiUrl(match.trackB.audioUrl) },
  };
}

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(apiUrl(path), init);
}

export async function createSession(): Promise<string> {
  const res = await apiFetch("/api/session", { method: "POST" });
  if (!res.ok) throw new Error("desk offline");
  const data = (await res.json()) as { sessionId: string };
  return data.sessionId;
}

export async function createMatch(
  sessionId: string | null,
  pace: Pace,
  styles: string[],
): Promise<Match> {
  const res = await apiFetch("/api/match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sessionId,
      pace,
      bias: styles.length ? { styles, strength: 0.85 } : null,
    }),
  });
  if (!res.ok) throw new Error("could not press the next pair");
  return withAbsoluteAudio((await res.json()) as Match);
}

export async function voteMatch(
  sessionId: string,
  matchId: string,
  choice: "A" | "B" | "skip",
): Promise<Match> {
  const res = await apiFetch("/api/vote", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessionId, matchId, choice }),
  });
  if (!res.ok) throw new Error("vote did not land");
  return withAbsoluteAudio((await res.json()) as Match);
}
