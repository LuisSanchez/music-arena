"""Clash API — per-session electronic soundclash, no persistence."""

from __future__ import annotations

import os
import secrets
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .engine.generate import generate_match
from .store import MatchRecord, TrackRecord, store

app = FastAPI(title="Clash", version="0.1.0")

_DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]


def _cors_origins() -> list[str]:
    """Comma-separated CORS_ORIGINS env, e.g. https://clash.vercel.app,http://localhost:5173"""
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if not raw:
        return list(_DEFAULT_ORIGINS)
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    # Always keep local Vite for hybrid dev
    for local in _DEFAULT_ORIGINS:
        if local not in origins:
            origins.append(local)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Pace = Literal["slow", "lofi", "hifi", "trance", "dance", "auto"]


class BiasIn(BaseModel):
    styles: list[str] = Field(default_factory=list)
    strength: float = 0.8


class MatchIn(BaseModel):
    sessionId: str | None = None
    pace: Pace = "auto"
    bias: BiasIn | None = None


class VoteIn(BaseModel):
    sessionId: str
    matchId: str
    choice: Literal["A", "B", "skip"]


def _public_track(track: TrackRecord, reveal: bool) -> dict[str, Any]:
    meta = track.meta
    payload: dict[str, Any] = {
        "id": track.id,
        "audioUrl": f"/api/audio/{track.id}",
        "duration": meta["duration"],
        "bpm": meta["bpm"],
        "key": meta["key"],
        "title": "sealed cut",
        "style": None,
        "tags": [],
        "producer": None,
    }
    if reveal:
        payload.update(
            {
                "title": meta["title"],
                "style": meta["style"],
                "tags": meta["tags"],
                "producer": meta["producerLabel"],
            }
        )
    return payload


def _public_match(match: MatchRecord, reveal: bool) -> dict[str, Any]:
    return {
        "matchId": match.id,
        "roundTitle": match.round_title,
        "pace": match.pace,
        "sealed": not reveal,
        "trackA": _public_track(match.track_a, reveal),
        "trackB": _public_track(match.track_b, reveal),
        "voted": match.voted,
        "choice": match.choice,
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"ok": "clash"}


@app.post("/api/session")
def create_session() -> dict[str, str]:
    session = store.new_session()
    return {"sessionId": session.id}


@app.post("/api/match")
def create_match(body: MatchIn) -> dict[str, Any]:
    session = store.require(body.sessionId) if body.sessionId else store.new_session()
    seed = secrets.randbits(32)
    bias_styles = body.bias.styles if body.bias and body.bias.styles else None
    raw = generate_match(seed=seed, pace=body.pace, bias_styles=bias_styles, target_sec=90.0)

    def pack(side: str, blob: dict[str, Any]) -> TrackRecord:
        tid = secrets.token_hex(8)
        # randomized filename so a producer cannot leak through the URL
        fname = f"{secrets.token_hex(5)}.wav"
        rec = TrackRecord(id=tid, wav=blob["wav"], meta=blob["meta"], filename=fname)
        session.tracks[tid] = rec
        return rec

    match = MatchRecord(
        id=secrets.token_hex(8),
        created=__import__("time").time(),
        pace=body.pace,
        round_title=raw["roundTitle"],
        track_a=pack("A", raw["trackA"]),
        track_b=pack("B", raw["trackB"]),
    )
    session.matches[match.id] = match
    payload = _public_match(match, reveal=False)
    payload["sessionId"] = session.id
    return payload


@app.get("/api/audio/{track_id}")
def audio(track_id: str) -> Response:
    for session in store.sessions.values():
        track = session.tracks.get(track_id)
        if track:
            return Response(
                content=track.wav,
                media_type="audio/wav",
                headers={
                    "Cache-Control": "no-store",
                    "Content-Disposition": f'inline; filename="{track.filename}"',
                },
            )
    raise HTTPException(status_code=404, detail="cut not on the desk")


@app.post("/api/vote")
def vote(body: VoteIn) -> dict[str, Any]:
    session = store.get(body.sessionId)
    if session is None:
        raise HTTPException(status_code=404, detail="session expired")
    match = session.matches.get(body.matchId)
    if match is None:
        raise HTTPException(status_code=404, detail="match not on the desk")
    match.voted = True
    match.choice = body.choice
    winner_meta = None
    if body.choice == "A":
        winner_meta = match.track_a.meta
    elif body.choice == "B":
        winner_meta = match.track_b.meta
    return {
        **_public_match(match, reveal=True),
        "sessionId": session.id,
        "winnerTags": winner_meta["tags"] if winner_meta else [],
        "winnerStyle": winner_meta["style"] if winner_meta else None,
    }
