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
from .engine.quality import STATIONS
from .radio_queue import ensure_track, is_generating, queue_depth, schedule_fill
from .store import MatchRecord, TrackRecord, store
from .warm import schedule_warm, take_warm

app = FastAPI(title="Clash", version="0.1.0")

_DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
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
Station = Literal["slow", "lofi", "hifi", "trance", "dance"]


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


class RadioSessionIn(BaseModel):
    sessionId: str | None = None
    station: Station


class RadioNextIn(BaseModel):
    sessionId: str
    station: Station


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
        "sampleRate": meta.get("sampleRate"),
        "profile": meta.get("profile"),
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


def _pack_radio_track(session_id: str, blob: dict[str, Any]) -> TrackRecord:
    tid = secrets.token_hex(8)
    fname = f"{secrets.token_hex(5)}.wav"
    rec = store.write_track(session_id, tid, blob["wav"], blob["meta"], fname)
    session = store.require(session_id)
    session.tracks[tid] = rec
    return rec


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
    bias_styles = body.bias.styles if body.bias and body.bias.styles else None
    target_sec = 120.0

    # Prefer a warm pair if the background pool already pressed one
    raw = take_warm(body.pace, bias_styles)
    if raw is None:
        seed = secrets.randbits(32)
        raw = generate_match(
            seed=seed, pace=body.pace, bias_styles=bias_styles, target_sec=target_sec
        )

    def pack(blob: dict[str, Any]):
        tid = secrets.token_hex(8)
        fname = f"{secrets.token_hex(5)}.wav"
        rec = store.write_track(
            session.id, tid, blob["wav"], blob["meta"], fname
        )
        session.tracks[tid] = rec
        return rec

    match = MatchRecord(
        id=secrets.token_hex(8),
        created=__import__("time").time(),
        pace=body.pace,
        round_title=raw["roundTitle"],
        track_a=pack(raw["trackA"]),
        track_b=pack(raw["trackB"]),
    )
    session.matches[match.id] = match
    # Top up the warm pool for the next press on this lane
    schedule_warm(body.pace, bias_styles, target_sec=target_sec)
    payload = _public_match(match, reveal=False)
    payload["sessionId"] = session.id
    return payload


@app.post("/api/radio/session")
def radio_session(body: RadioSessionIn) -> dict[str, Any]:
    if body.station not in STATIONS:
        raise HTTPException(status_code=400, detail="pick a station — auto is not allowed")
    session = store.require(body.sessionId) if body.sessionId else store.new_session()
    schedule_fill(body.station)
    # Seed client with up to 2 ready cuts (generate cold if needed for first)
    queue: list[dict[str, Any]] = []
    for _ in range(2):
        try:
            blob = ensure_track(body.station)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        rec = _pack_radio_track(session.id, blob)
        queue.append(_public_track(rec, reveal=True))
    schedule_fill(body.station)
    return {
        "sessionId": session.id,
        "station": body.station,
        "queue": queue,
        "queueDepth": queue_depth(body.station),
        "generating": is_generating(body.station),
    }


@app.post("/api/radio/next")
def radio_next(body: RadioNextIn) -> dict[str, Any]:
    if body.station not in STATIONS:
        raise HTTPException(status_code=400, detail="pick a station — auto is not allowed")
    session = store.get(body.sessionId)
    if session is None:
        raise HTTPException(status_code=404, detail="session expired")
    try:
        blob = ensure_track(body.station)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rec = _pack_radio_track(session.id, blob)
    schedule_fill(body.station)
    return {
        "sessionId": session.id,
        "station": body.station,
        "track": _public_track(rec, reveal=True),
        "queueDepth": queue_depth(body.station),
        "generating": is_generating(body.station),
    }


@app.get("/api/radio/status")
def radio_status(sessionId: str | None = None, station: str | None = None) -> dict[str, Any]:
    st = (station or "").lower().strip()
    if st and st not in STATIONS:
        raise HTTPException(status_code=400, detail="invalid station")
    return {
        "sessionId": sessionId,
        "station": st or None,
        "queueDepth": queue_depth(st) if st else 0,
        "generating": is_generating(st) if st else False,
        "stations": list(STATIONS),
    }


@app.get("/api/audio/{track_id}")
def audio(track_id: str) -> Response:
    for session in store.sessions.values():
        track = session.tracks.get(track_id)
        if track:
            try:
                content = track.read_wav()
            except OSError as exc:
                raise HTTPException(status_code=404, detail="cut file missing") from exc
            return Response(
                content=content,
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
