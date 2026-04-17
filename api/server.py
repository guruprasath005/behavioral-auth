"""
FastAPI read-only API over behavioral_auth.db.

Run from the ``behavioral-auth`` directory::

    uvicorn api.server:app --reload --port 8000
"""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from typing import Annotated, Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from storage.database import Database


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = "ok"


class SessionItem(BaseModel):
    session_id: str
    user_id: str
    started_at: float
    ended_at: Optional[float] = None
    risk_level: str

    @classmethod
    def from_row(cls, row: dict) -> "SessionItem":
        return cls(
            session_id=row["session_id"],
            user_id=row["user_id"],
            started_at=row["started_at"],
            ended_at=row.get("ended_at"),
            risk_level=row.get("risk_level") or "UNKNOWN",
        )


class SessionsListResponse(BaseModel):
    sessions: list[SessionItem]


class AlertItem(BaseModel):
    id: int
    session_id: str
    window_index: int
    risk_level: str
    confidence: float
    anomalous_features: list[str]
    reasoning: str
    timestamp: float

    @classmethod
    def from_row(cls, row: dict) -> "AlertItem":
        raw = row.get("anomalous_features_json") or "[]"
        try:
            parsed = json.loads(raw)
            anom = parsed if isinstance(parsed, list) else []
            anom = [str(x) for x in anom]
        except json.JSONDecodeError:
            anom = []
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            window_index=row["window_index"],
            risk_level=row["risk_level"],
            confidence=float(row["confidence"]),
            anomalous_features=anom,
            reasoning=row["reasoning"],
            timestamp=float(row["timestamp"]),
        )


class AlertsListResponse(BaseModel):
    alerts: list[AlertItem]


class RadarPoint(BaseModel):
    feature: str
    value: float


class BaselineResponse(BaseModel):
    """``baseline`` maps feature name to mean/std; ``radar_data`` uses mean as chart value."""

    baseline: dict[str, dict[str, float]]
    radar_data: list[RadarPoint]


class FeatureWindowItem(BaseModel):
    id: int
    session_id: str
    window_index: int
    window_start: float
    window_end: float
    is_warmup: bool
    features: dict[str, Any]

    @classmethod
    def from_row(cls, row: dict) -> "FeatureWindowItem":
        raw = row.get("features_json") or "{}"
        try:
            feats = json.loads(raw)
            if not isinstance(feats, dict):
                feats = {}
        except json.JSONDecodeError:
            feats = {}
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            window_index=row["window_index"],
            window_start=float(row["window_start"]),
            window_end=float(row["window_end"]),
            is_warmup=bool(row["is_warmup"]),
            features=feats,
        )


class FeatureWindowsResponse(BaseModel):
    windows: list[FeatureWindowItem]


class ShellEventItem(BaseModel):
    id: int
    session_id: str
    command: str
    timestamp: float

    @classmethod
    def from_row(cls, row: dict) -> "ShellEventItem":
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            command=row["command"],
            timestamp=float(row["timestamp"]),
        )


class ShellEventsResponse(BaseModel):
    events: list[ShellEventItem]


class LiveResponse(BaseModel):
    latest_alert: Optional[AlertItem] = None
    latest_feature_window: Optional[FeatureWindowItem] = None
    idle_seconds: Optional[float] = None


# ---------------------------------------------------------------------------
# App factory & dependencies
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = Database()
    try:
        yield
    finally:
        app.state.db.close()


app = FastAPI(title="Behavioral Auth API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db(request: Request) -> Database:
    return request.app.state.db


DbDep = Annotated[Database, Depends(get_db)]


def require_session(db: Database, session_id: str) -> dict:
    row = db.get_session(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return row


def _idle_seconds_from_mouse(db: Database, session_id: str) -> Optional[float]:
    events = db.get_mouse_events(session_id)
    if not events:
        return None
    last_ts = max(float(e["timestamp"]) for e in events)
    return max(0.0, time.time() - last_ts)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse()


@app.get("/sessions", response_model=SessionsListResponse)
def list_sessions(db: DbDep):
    rows = db.get_all_sessions()
    return SessionsListResponse(
        sessions=[SessionItem.from_row(r) for r in rows],
    )


@app.get("/sessions/{session_id}/alerts", response_model=AlertsListResponse)
def session_alerts(session_id: str, db: DbDep):
    require_session(db, session_id)
    rows = db.get_alerts_for_session(session_id)
    return AlertsListResponse(alerts=[AlertItem.from_row(r) for r in rows])


@app.get("/sessions/{session_id}/baseline", response_model=BaselineResponse)
def session_baseline(session_id: str, db: DbDep):
    sess = require_session(db, session_id)
    user_id = sess["user_id"]
    profile = db.get_baseline_profile(user_id)
    radar = [
        RadarPoint(feature=name, value=stats["mean"])
        for name, stats in sorted(profile.items())
    ]
    return BaselineResponse(baseline=profile, radar_data=radar)


@app.get("/sessions/{session_id}/windows", response_model=FeatureWindowsResponse)
def session_windows(session_id: str, db: DbDep):
    require_session(db, session_id)
    rows = db.get_feature_windows(session_id)
    return FeatureWindowsResponse(
        windows=[FeatureWindowItem.from_row(r) for r in rows],
    )


@app.get("/sessions/{session_id}/shell", response_model=ShellEventsResponse)
def session_shell(session_id: str, db: DbDep):
    require_session(db, session_id)
    rows = db.get_shell_events(session_id)
    return ShellEventsResponse(events=[ShellEventItem.from_row(r) for r in rows])


@app.get("/sessions/{session_id}/live", response_model=LiveResponse)
def session_live(session_id: str, db: DbDep):
    require_session(db, session_id)
    alerts = db.get_alerts_for_session(session_id)
    latest_alert = AlertItem.from_row(alerts[-1]) if alerts else None

    windows = db.get_feature_windows(session_id)
    latest_win = (
        FeatureWindowItem.from_row(windows[-1]) if windows else None
    )

    idle = _idle_seconds_from_mouse(db, session_id)
    return LiveResponse(
        latest_alert=latest_alert,
        latest_feature_window=latest_win,
        idle_seconds=idle,
    )
