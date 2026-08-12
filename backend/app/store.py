"""Session store with on-disk WAV cache (keeps RAM down for ~120s stereo cuts)."""

from __future__ import annotations

import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


TTL_SECONDS = 2 * 60 * 60


def _cache_root() -> Path:
    raw = os.getenv("CLASH_CACHE_DIR", "").strip()
    if raw:
        root = Path(raw)
    else:
        root = Path(os.getenv("TMPDIR", "/tmp")) / "clash-wav-cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass
class TrackRecord:
    id: str
    path: str
    meta: dict[str, Any]
    filename: str

    def read_wav(self) -> bytes:
        return Path(self.path).read_bytes()


@dataclass
class MatchRecord:
    id: str
    created: float
    pace: str
    round_title: str
    track_a: TrackRecord
    track_b: TrackRecord
    voted: bool = False
    choice: str | None = None


@dataclass
class Session:
    id: str
    created: float
    matches: dict[str, MatchRecord] = field(default_factory=dict)
    tracks: dict[str, TrackRecord] = field(default_factory=dict)


class MemoryStore:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self._root = _cache_root()

    def _session_dir(self, session_id: str) -> Path:
        d = self._root / session_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_track(
        self,
        session_id: str,
        track_id: str,
        wav: bytes,
        meta: dict[str, Any],
        filename: str,
    ) -> TrackRecord:
        path = self._session_dir(session_id) / f"{track_id}.wav"
        path.write_bytes(wav)
        return TrackRecord(id=track_id, path=str(path), meta=meta, filename=filename)

    def _purge_session_files(self, session_id: str) -> None:
        d = self._root / session_id
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)

    def _purge(self) -> None:
        now = time.time()
        dead = [sid for sid, s in self.sessions.items() if now - s.created > TTL_SECONDS]
        for sid in dead:
            self._purge_session_files(sid)
            del self.sessions[sid]
        # Sweep orphan cache dirs older than TTL
        try:
            for child in self._root.iterdir():
                if not child.is_dir():
                    continue
                if child.name in self.sessions:
                    continue
                age = now - child.stat().st_mtime
                if age > TTL_SECONDS:
                    shutil.rmtree(child, ignore_errors=True)
        except OSError:
            pass

    def new_session(self) -> Session:
        self._purge()
        sid = uuid.uuid4().hex
        session = Session(id=sid, created=time.time())
        self.sessions[sid] = session
        self._session_dir(sid)
        return session

    def get(self, session_id: str) -> Session | None:
        self._purge()
        return self.sessions.get(session_id)

    def require(self, session_id: str) -> Session:
        session = self.get(session_id)
        if session is None:
            session = self.new_session()
        return session


store = MemoryStore()
