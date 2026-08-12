import type { Pace, Track } from "./api";

export type Station = Exclude<Pace, "auto">;

export type RadioSession = {
  sessionId: string;
  station: Station;
  queue: Track[];
  queueDepth: number;
  generating: boolean;
};

export type RadioNext = {
  sessionId: string;
  station: Station;
  track: Track;
  queueDepth: number;
  generating: boolean;
};

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";

function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

function withAbs(track: Track): Track {
  return { ...track, audioUrl: apiUrl(track.audioUrl) };
}

export const STATIONS: { id: Station; label: string }[] = [
  { id: "slow", label: "Slow" },
  { id: "lofi", label: "Lo-fi" },
  { id: "dance", label: "Dance" },
  { id: "trance", label: "Trance" },
  { id: "hifi", label: "Hi-fi" },
];

const STATION_KEY = "clash.radio.station.v1";

export function readStation(): Station {
  try {
    const raw = localStorage.getItem(STATION_KEY);
    if (raw && STATIONS.some((s) => s.id === raw)) return raw as Station;
  } catch {
    /* ignore */
  }
  return "trance";
}

export function writeStation(station: Station): void {
  try {
    localStorage.setItem(STATION_KEY, station);
  } catch {
    /* ignore */
  }
}

export async function startRadio(
  station: Station,
  sessionId: string | null,
): Promise<RadioSession> {
  const res = await fetch(apiUrl("/api/radio/session"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessionId, station }),
  });
  if (!res.ok) throw new Error("radio desk offline");
  const data = (await res.json()) as RadioSession;
  return {
    ...data,
    queue: data.queue.map(withAbs),
  };
}

export async function nextRadioTrack(
  sessionId: string,
  station: Station,
): Promise<RadioNext> {
  const res = await fetch(apiUrl("/api/radio/next"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessionId, station }),
  });
  if (!res.ok) throw new Error("could not queue next cut");
  const data = (await res.json()) as RadioNext;
  return { ...data, track: withAbs(data.track) };
}
