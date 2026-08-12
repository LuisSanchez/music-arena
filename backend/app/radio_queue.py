"""Station warm queue for radio — low-quality single tracks, bounded workers."""

from __future__ import annotations

import os
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Any

from .engine.generate import generate_radio_track
from .engine.quality import STATIONS

_DEPTH = int(os.getenv("RADIO_WARM_DEPTH", "4"))
_ENABLED = os.getenv("RADIO_WARM_POOL", "1") not in {"0", "false", "False"}
# Serial radio production so arena is not starved
_WORKERS = max(1, int(os.getenv("RADIO_WORKERS", "1")))

_lock = threading.Lock()
_queues: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
_inflight: dict[str, int] = defaultdict(int)
_sem = threading.Semaphore(_WORKERS)
_active_stations: dict[str, float] = {}  # station -> last touch


def touch_station(station: str) -> None:
    with _lock:
        _active_stations[station] = time.time()


def queue_depth(station: str) -> int:
    with _lock:
        return len(_queues.get(station, ()))


def is_generating(station: str) -> bool:
    with _lock:
        return _inflight.get(station, 0) > 0


def take_track(station: str) -> dict[str, Any] | None:
    station = station.lower().strip()
    if station not in STATIONS:
        return None
    touch_station(station)
    with _lock:
        q = _queues[station]
        if not q:
            return None
        return q.popleft()


def schedule_fill(station: str) -> None:
    """Ensure the station queue is topped up (non-blocking)."""
    if not _ENABLED or _DEPTH <= 0:
        return
    station = station.lower().strip()
    if station not in STATIONS:
        return
    touch_station(station)
    with _lock:
        need = _DEPTH - len(_queues[station]) - _inflight[station]
        if need <= 0:
            return
        # one fill thread per call; worker re-checks depth
        _inflight[station] += 1

    def _worker() -> None:
        try:
            while True:
                with _lock:
                    depth = len(_queues[station])
                    if depth >= _DEPTH:
                        break
                if not _sem.acquire(blocking=False):
                    # another worker is generating; stop this filler
                    break
                try:
                    seed = secrets.randbits(31)
                    track = generate_radio_track(seed=seed, station=station)
                    with _lock:
                        if len(_queues[station]) < _DEPTH:
                            _queues[station].append(track)
                finally:
                    _sem.release()
                # yield so arena can schedule
                time.sleep(0.05)
        finally:
            with _lock:
                _inflight[station] = max(0, _inflight[station] - 1)

    threading.Thread(target=_worker, name=f"radio-fill-{station}", daemon=True).start()


def ensure_track(station: str) -> dict[str, Any]:
    """Blocking: take warm track or generate one now."""
    station = station.lower().strip()
    if station not in STATIONS:
        raise ValueError(f"invalid station: {station}")
    ready = take_track(station)
    if ready is not None:
        schedule_fill(station)
        return ready
    # cold path
    seed = secrets.randbits(31)
    track = generate_radio_track(seed=seed, station=station)
    schedule_fill(station)
    return track
