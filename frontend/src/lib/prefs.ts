const KEY = "clash.ear.v1";

export type StoredVote = {
  ts: number;
  choice: "A" | "B" | "skip";
  winnerStyle?: string | null;
  winnerTags?: string[];
};

export type Ear = {
  votes: StoredVote[];
  locked: string[];
};

const EMPTY: Ear = { votes: [], locked: [] };

export function readEar(): Ear {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw) as Ear;
    return {
      votes: Array.isArray(parsed.votes) ? parsed.votes.slice(-40) : [],
      locked: Array.isArray(parsed.locked) ? parsed.locked : [],
    };
  } catch {
    return EMPTY;
  }
}

export function recordVote(vote: StoredVote): Ear {
  const ear = readEar();
  const votes = [...ear.votes, vote].slice(-40);
  const locked = inferLock(votes);
  const next = { votes, locked };
  localStorage.setItem(KEY, JSON.stringify(next));
  return next;
}

export function inferLock(votes: StoredVote[]): string[] {
  const wins = votes.filter((v) => v.choice !== "skip" && (v.winnerTags?.length || v.winnerStyle));
  const last = wins.slice(-3);
  if (last.length < 3) return [];
  const sets = last.map((v) => new Set([...(v.winnerTags ?? []), v.winnerStyle].filter(Boolean) as string[]));
  const [a, b, c] = sets;
  const shared = [...a].filter((tag) => b.has(tag) && c.has(tag));
  // Prefer musical tags over derived ones
  const musical = ["lofi", "dance", "trance", "slow", "hifi"];
  const preferred = shared.filter((t) => musical.includes(t));
  if (preferred.length) return preferred;

  const lastStyles = last
    .map((v) => v.winnerStyle)
    .filter((s): s is string => !!s);
  if (lastStyles.length === 3) {
    if (lastStyles.every((s) => s === "lofi" || s === "dance")) return ["lofi", "dance"];
    if (lastStyles.every((s) => s === "trance" || s === "hifi")) return ["trance", "hifi"];
    if (lastStyles.every((s) => s === "slow" || s === "lofi")) return ["slow", "lofi"];
  }
  return shared.slice(0, 2);
}

export function describeLock(locked: string[]): string {
  if (!locked.length) return "listening — no lock yet";
  return locked.join(" + ");
}
