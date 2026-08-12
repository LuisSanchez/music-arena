"""In-memory session store. Nothing is written to disk."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


TTL_SECONDS = 2 * 60 * 60


@dataclass
class TrackRecord:
    id: str
    wav: bytes
    meta: dict[str, Any]
    filename: str


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

    def _purge(self) -> None:
        now = time.time()
        dead = [sid for sid, s in self.sessions.items() if now - s.created > TTL_SECONDS]
        for sid in dead:
            del self.sessions[sid]

    def new_session(self) -> Session:
        self._purge()
        sid = uuid.uuid4().hex
        session = Session(id=sid, created=time.time())
        self.sessions[sid] = session
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
