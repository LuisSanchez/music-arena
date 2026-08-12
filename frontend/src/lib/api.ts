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

export async function createSession(): Promise<string> {
  const res = await fetch("/api/session", { method: "POST" });
  if (!res.ok) throw new Error("desk offline");
  const data = (await res.json()) as { sessionId: string };
  return data.sessionId;
}

export async function createMatch(
  sessionId: string | null,
  pace: Pace,
  styles: string[],
): Promise<Match> {
  const res = await fetch("/api/match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sessionId,
      pace,
      bias: styles.length ? { styles, strength: 0.85 } : null,
    }),
  });
  if (!res.ok) throw new Error("could not press the next pair");
  return res.json() as Promise<Match>;
}

export async function voteMatch(
  sessionId: string,
  matchId: string,
  choice: "A" | "B" | "skip",
): Promise<Match> {
  const res = await fetch("/api/vote", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessionId, matchId, choice }),
  });
  if (!res.ok) throw new Error("vote did not land");
  return res.json() as Promise<Match>;
}
