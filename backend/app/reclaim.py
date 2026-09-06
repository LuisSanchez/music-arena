"""Idle memory reclamation.

Railway bills for RAM even at 0 CPU. After a match the process pool (two
NumPy/SciPy workers) plus leftover malloc arenas sit near 1GB forever.
This module:

- tracks real client activity (healthchecks do NOT count)
- shuts the render pool down after CLASH_IDLE_RECLAIM_SEC
- drops in-RAM warm / radio caches
- asks glibc to return pages (malloc_trim)

The next /api/match after reclaim is a cold start (slower); follow-up
presses reuse a live pool and are faster.
"""

from __future__ import annotations

import gc
import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

# Healthchecks must not reset this — otherwise the desk never sleeps.
_last_active = time.time()
_busy = 0
_cold = True
_started = False
_gate = threading.Lock()
_janitor: threading.Thread | None = None

IDLE_SEC = max(60, int(os.getenv("CLASH_IDLE_RECLAIM_SEC", "180")))
SWEEP_SEC = max(10.0, float(os.getenv("CLASH_IDLE_SWEEP_SEC", "30")))


def touch() -> None:
    global _last_active
    with _gate:
        _last_active = time.time()


def is_cold() -> bool:
    with _gate:
        return _cold


def mark_hot() -> None:
    global _cold
    with _gate:
        _cold = False


def idle_seconds() -> float:
    with _gate:
        return max(0.0, time.time() - _last_active)


def malloc_trim() -> bool:
    """Return free glibc arenas to the OS. No-op on macOS / non-glibc."""
    if sys.platform != "linux":
        return False
    try:
        import ctypes

        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
        return True
    except Exception:
        return False


def collect() -> None:
    gc.collect()
    malloc_trim()


def _rss_kb(pid: int) -> int:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError):
        return 0
    return 0


def rss_mb() -> float | None:
    """Current RSS of this process plus direct children (Linux)."""
    try:
        pids = {os.getpid()}
        task = Path(f"/proc/{os.getpid()}/task")
        for tid in task.iterdir():
            children = tid / "children"
            if not children.exists():
                continue
            for raw in children.read_text().split():
                try:
                    pids.add(int(raw))
                except ValueError:
                    continue
        kb = sum(_rss_kb(pid) for pid in pids)
        return round(kb / 1024.0, 1)
    except OSError:
        return None


@contextmanager
def generation_job() -> Iterator[None]:
    """Hold a busy slot so the janitor cannot kill workers mid-render."""
    global _busy, _last_active
    with _gate:
        _busy += 1
        _last_active = time.time()
    try:
        yield
    finally:
        with _gate:
            _busy = max(0, _busy - 1)
            _last_active = time.time()


def _pool_mod():
    """Avoid importing generate (NumPy) until a real match has run."""
    return sys.modules.get("app.engine.generate")


def _pool_alive() -> bool:
    gen = _pool_mod()
    if gen is None:
        return False
    fn = getattr(gen, "pool_alive", None)
    return bool(fn()) if callable(fn) else False


def _needs_reclaim() -> bool:
    from .radio_queue import radio_held
    from .warm import warm_held

    return _pool_alive() or warm_held() > 0 or radio_held() > 0


def reclaim(*, force: bool = False) -> dict[str, Any]:
    """Drop workers + in-RAM caches. Skips when a generate is in flight."""
    global _cold
    from .radio_queue import clear_radio
    from .store import store
    from .warm import clear_warm

    with _gate:
        if _busy > 0 and not force:
            return {"ok": False, "skipped": True, "reason": "busy"}
        _cold = True
        clear_warm()
        clear_radio()
        store.reclaim_idle()
        gen = _pool_mod()
        if gen is not None:
            shutdown = getattr(gen, "shutdown_proc_pool", None)
            if callable(shutdown):
                shutdown()
        collect()
        return {
            "ok": True,
            "skipped": False,
            "cold": True,
            "rssMb": rss_mb(),
            "idleSeconds": max(0.0, time.time() - _last_active),
        }


def snapshot() -> dict[str, Any]:
    from .radio_queue import radio_held
    from .warm import warm_held

    with _gate:
        cold = _cold
        idle = max(0.0, time.time() - _last_active)
        busy = _busy
    return {
        "ok": "clash",
        "cold": cold,
        "engine": "sleeping" if cold else "ready",
        "idleSeconds": int(idle),
        "busy": busy,
        "pool": _pool_alive(),
        "warmPairs": warm_held(),
        "radioCuts": radio_held(),
        "rssMb": rss_mb(),
    }


def _janitor_loop() -> None:
    while True:
        time.sleep(SWEEP_SEC)
        try:
            with _gate:
                busy = _busy
                idle = time.time() - _last_active
            if busy == 0 and idle >= IDLE_SEC and _needs_reclaim():
                reclaim()
        except Exception:
            continue


def start_janitor() -> None:
    global _started, _janitor
    with _gate:
        if _started:
            return
        _started = True
        _janitor = threading.Thread(
            target=_janitor_loop, name="clash-idle-reclaim", daemon=True
        )
        _janitor.start()
