"""Disk-backed warm pair pool — pre-generate the next match for a pace/bias key."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from typing import Any

# How many warm pairs to keep per (pace, bias) key
_MAX_PER_KEY = int(os.getenv("CLASH_WARM_DEPTH", "1"))
_enabled = os.getenv("CLASH_WARM_POOL", "1") not in {"0", "false", "False"}

_lock = threading.Lock()
_pool: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
_inflight: set[str] = set()


def _key(pace: str, bias_styles: list[str] | None) -> str:
    tags = ",".join(sorted(bias_styles or []))
    return f"{pace}|{tags}"


def warm_held() -> int:
    with _lock:
        return sum(len(q) for q in _pool.values())


def clear_warm() -> None:
    """Drop pre-pressed pairs so WAV bytes leave RAM on idle."""
    with _lock:
        for q in _pool.values():
            q.clear()
        _pool.clear()


def take_warm(pace: str, bias_styles: list[str] | None) -> dict[str, Any] | None:
    if not _enabled:
        return None
    k = _key(pace, bias_styles)
    with _lock:
        q = _pool.get(k)
        if not q:
            return None
        return q.popleft()


def schedule_warm(pace: str, bias_styles: list[str] | None, target_sec: float = 120.0) -> None:
    """Fire-and-forget generation into the warm pool (one worker per key)."""
    if not _enabled or _MAX_PER_KEY <= 0:
        return
    k = _key(pace, bias_styles)
    with _lock:
        q = _pool[k]
        if len(q) >= _MAX_PER_KEY:
            return
        if k in _inflight:
            return
        _inflight.add(k)

    def _worker() -> None:
        from .engine.generate import generate_match
        from .reclaim import generation_job

        try:
            with generation_job():
                seed = int(time.time() * 1000) & 0x7FFFFFFF
                raw = generate_match(
                    seed=seed,
                    pace=pace,
                    bias_styles=bias_styles,
                    target_sec=target_sec,
                )
            with _lock:
                q = _pool[k]
                if len(q) < _MAX_PER_KEY:
                    q.append(raw)
        except Exception:
            pass
        finally:
            with _lock:
                _inflight.discard(k)

    threading.Thread(target=_worker, name=f"clash-warm-{k[:24]}", daemon=True).start()
