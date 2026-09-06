import { useEffect, useState } from "react";
import { getHealth } from "./api";

/**
 * Polls /api/health so the UI can say the desk is sleeping (cheap idle)
 * vs live (workers up). After a successful generate we force "hot" until
 * the next poll sees the janitor put the engine back to sleep.
 */
export function useEngineHealth(intervalMs = 45_000): {
  cold: boolean;
  markHot: () => void;
} {
  const [healthCold, setHealthCold] = useState(true);
  const [hotUntilPoll, setHotUntilPoll] = useState(false);

  useEffect(() => {
    let timer: number | undefined;
    let cancelled = false;

    const tick = async () => {
      try {
        const h = await getHealth();
        if (!cancelled) setHealthCold(h.cold);
      } catch {
        if (!cancelled) setHealthCold(true);
      }
      if (!cancelled) timer = window.setTimeout(tick, intervalMs);
    };

    void tick();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [intervalMs]);

  useEffect(() => {
    if (healthCold) setHotUntilPoll(false);
  }, [healthCold]);

  return {
    cold: healthCold && !hotUntilPoll,
    markHot: () => setHotUntilPoll(true),
  };
}
