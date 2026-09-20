"""
Workouts admin API — CRUD over saved workout sessions.

The arena saves what it just did through `POST /workouts`; this router is the back
office behind `/workouts/admin`: fixing a wrong date, correcting sets/reps, moving a
session to the other person, deleting a session, and clearing the stations that were
imported from the old browser-only "כבשתי!" flags.

Everything the workouts module shows (XP, levels, streaks, conquered stations) is
derived from these rows, so every write here moves the game state with it.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date as date_cls
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException

from ..db import get_db_conn
from ..routes.workouts import (
    _clean_progress,
    _legacy_progress_key,
    _load_legacy_progress,
    _station_for,
    admin_session,
    admin_session_rows,
    admin_sessions,
)
from ..schemas.workouts import (
    WorkoutAdminExerciseSchema,
    WorkoutLegacyProgressWriteSchema,
    WorkoutSessionWriteSchema,
)

router = APIRouter(prefix="/api/workouts", tags=["workouts"])


def _valid_user_id(db_conn: sqlite3.Connection, user_id: int) -> int:
    row = db_conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="Unknown user_id")
    return row["id"]


def _valid_date(value: str) -> str:
    try:
        return date_cls.fromisoformat(str(value)[:10]).isoformat()
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")


def _exercise_values(ex: WorkoutAdminExerciseSchema) -> Tuple[str, int, int, Optional[str], Optional[int], Optional[int]]:
    """Exercise payload → the columns a workouts row stores, with its station resolved."""
    name = ex.exercise_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="exercise_name must not be empty")
    station = _station_for(ex.skill_key, ex.stage_index, name)
    max_reps = None if ex.max_reps is None else max(0, min(ex.max_reps, ex.total_reps))
    return (
        name,
        ex.total_sets,
        ex.total_reps,
        station[0] if station else None,
        station[1] if station else None,
        max_reps,
    )


def _validated_session(body: WorkoutSessionWriteSchema, db_conn: sqlite3.Connection) -> Dict[str, Any]:
    """Session payload → the values every row of the session shares, plus its exercises."""
    if not body.exercises:
        raise HTTPException(status_code=400, detail="A session needs at least one exercise")
    workout_type = body.workout_type.strip()
    if not workout_type:
        raise HTTPException(status_code=400, detail="workout_type must not be empty")
    return {
        "user_id": _valid_user_id(db_conn, body.user_id),
        "date": _valid_date(body.date),
        "workout_type": workout_type,
        "total_duration": body.total_duration,
        "exercises": [_exercise_values(ex) for ex in body.exercises],
    }


def _insert_row(db_conn: sqlite3.Connection, session: Dict[str, Any], values: Tuple) -> int:
    name, sets, reps, skill_key, stage_index, max_reps = values
    cur = db_conn.execute(
        """
        INSERT INTO workouts (user_id, date, workout_type, total_duration, exercise_name,
                              total_sets, total_reps, skill_key, stage_index, max_reps)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (session["user_id"], session["date"], session["workout_type"], session["total_duration"],
         name, sets, reps, skill_key, stage_index, max_reps),
    )
    return cur.lastrowid


@router.get("/sessions")
async def list_sessions(
    user_id: Optional[int] = None,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> List[Dict[str, Any]]:
    """Saved sessions, newest first — all of them, or one person's."""
    if user_id is not None:
        _valid_user_id(db_conn, user_id)
    return admin_sessions(db_conn, user_id)


@router.post("/sessions", status_code=201)
async def create_session(
    body: WorkoutSessionWriteSchema,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> Dict[str, Any]:
    """Add a session by hand — one that was trained away from the arena, say."""
    session = _validated_session(body, db_conn)
    row_ids = [_insert_row(db_conn, session, values) for values in session["exercises"]]
    db_conn.commit()
    return admin_session(db_conn, row_ids[0])


@router.put("/sessions/{row_id}")
async def update_session(
    row_id: int,
    body: WorkoutSessionWriteSchema,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> Dict[str, Any]:
    """Replace a session: its details move to every row, and its exercise list becomes the payload."""
    existing = {row["id"] for row in admin_session_rows(db_conn, row_id)}
    if not existing:
        raise HTTPException(status_code=404, detail="Workout session not found")

    session = _validated_session(body, db_conn)
    edited = [ex.id for ex in body.exercises if ex.id is not None]
    kept = set(edited)
    if len(kept) != len(edited):
        raise HTTPException(status_code=400, detail="An exercise row appears twice in the payload")
    stranger = sorted(kept - existing)
    if stranger:
        raise HTTPException(status_code=400, detail=f"Exercise rows not in this session: {stranger}")

    for gone in existing - kept:
        db_conn.execute("DELETE FROM workouts WHERE id = ?", (gone,))

    row_ids: List[int] = []
    for ex, values in zip(body.exercises, session["exercises"]):
        name, sets, reps, skill_key, stage_index, max_reps = values
        if ex.id is None:
            row_ids.append(_insert_row(db_conn, session, values))
            continue
        db_conn.execute(
            """
            UPDATE workouts
               SET user_id = ?, date = ?, workout_type = ?, total_duration = ?, exercise_name = ?,
                   total_sets = ?, total_reps = ?, skill_key = ?, stage_index = ?, max_reps = ?
             WHERE id = ?
            """,
            (session["user_id"], session["date"], session["workout_type"], session["total_duration"],
             name, sets, reps, skill_key, stage_index, max_reps, ex.id),
        )
        row_ids.append(ex.id)
    db_conn.commit()
    return admin_session(db_conn, row_ids[0])


@router.delete("/sessions/{row_id}")
async def delete_session(
    row_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> Dict[str, Any]:
    """Delete a whole session — every exercise row saved under it."""
    rows = admin_session_rows(db_conn, row_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Workout session not found")
    for row in rows:
        db_conn.execute("DELETE FROM workouts WHERE id = ?", (row["id"],))
    db_conn.commit()
    return {"deleted": True, "exercises": len(rows)}


@router.put("/legacy-progress")
async def replace_legacy_progress(
    body: WorkoutLegacyProgressWriteSchema,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> Dict[str, Any]:
    """Replace a user's imported "conquered by hand" stations — an empty progress clears them."""
    user_id = _valid_user_id(db_conn, body.user_id)
    progress = _clean_progress(body.progress)
    key = _legacy_progress_key(user_id)
    if progress:
        db_conn.execute(
            "INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, json.dumps(progress)),
        )
    else:
        db_conn.execute("DELETE FROM system_settings WHERE key = ?", (key,))
    db_conn.commit()
    return {
        "status": "success",
        "progress": _load_legacy_progress(db_conn, user_id),
        "stations": sum(len(v) for v in progress.values()),
    }
