"""Back-office grouping of saved workout rows into sessions (/workouts/admin)."""
import sqlite3
from collections.abc import Iterable
from typing import Any

from .catalog import DEFAULT_EXERCISES, PATHS, SKILL_PROGRESSIONS, WORKOUT_TYPE_LABELS, station_exercise_name
from .legacy import _legacy_to_current, _stored_legacy_progress
from .progress import _exercise_title, _session_xp, _station_for

# ====================== ADMIN (back office) ======================
# /workouts/admin edits the rows everything else is derived from. A session is the
# group of rows sharing (user_id, date, workout_type, total_duration) — the same
# grouping _fetch_history uses — so any row id identifies the session it belongs to.
# The JSON writes behind the screen live in api/workouts.py.

ADMIN_ROW_COLUMNS = (
    "id, user_id, date, workout_type, total_duration, exercise_name, "
    "total_sets, total_reps, skill_key, stage_index, max_reps"
)


def _session_key(row: sqlite3.Row) -> tuple[Any, ...]:
    return (row["user_id"], row["date"], row["workout_type"], row["total_duration"])


def _admin_exercise(row: sqlite3.Row) -> dict[str, Any]:
    station = _station_for(row["skill_key"], row["stage_index"], row["exercise_name"])
    return {
        "id": row["id"],
        "exercise_name": row["exercise_name"],
        "title": _exercise_title(row["exercise_name"], station),
        "total_sets": row["total_sets"],
        "total_reps": row["total_reps"],
        "max_reps": row["max_reps"],
        "skill_key": station[0] if station else None,
        "stage_index": station[1] if station else None,
        "path": PATHS[station[0]]["name"] if station else None,
    }


def _group_admin_rows(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    """Exercise rows → sessions, in the order the rows arrive."""
    sessions: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        session = sessions.setdefault(_session_key(row), {
            "id": row["id"],  # any row of the group addresses the session
            "user_id": row["user_id"],
            "date": row["date"],
            "workout_type": row["workout_type"],
            "type_label": WORKOUT_TYPE_LABELS.get(row["workout_type"], row["workout_type"]),
            "total_duration": row["total_duration"],
            "exercises": [],
        })
        session["exercises"].append(_admin_exercise(row))
    for session in sessions.values():
        # Rows arrive newest first so sessions are; inside one, keep the order they were saved in
        session["exercises"].sort(key=lambda ex: ex["id"])
        session["id"] = session["exercises"][0]["id"]
        session["sets"] = sum(ex["total_sets"] for ex in session["exercises"])
        session["reps"] = sum(ex["total_reps"] for ex in session["exercises"])
        session["xp"] = _session_xp(session["sets"], session["reps"], session["total_duration"])
    return list(sessions.values())


def admin_sessions(db_conn: sqlite3.Connection, user_id: int | None = None) -> list[dict[str, Any]]:
    """Saved sessions, newest first, in the shape the admin screen lists and edits."""
    where, params = "", []
    if user_id is not None:
        where, params = "WHERE user_id = ?", [user_id]
    rows = db_conn.execute(
        f"SELECT {ADMIN_ROW_COLUMNS} FROM workouts {where} ORDER BY date DESC, id DESC", params
    ).fetchall()
    return _group_admin_rows(rows)


def admin_session_rows(db_conn: sqlite3.Connection, row_id: int) -> list[sqlite3.Row]:
    """Every row of the session a row id belongs to; empty when that row is gone."""
    row = db_conn.execute(
        f"SELECT {ADMIN_ROW_COLUMNS} FROM workouts WHERE id = ?", (row_id,)
    ).fetchone()
    if not row:
        return []
    return db_conn.execute(
        f"SELECT {ADMIN_ROW_COLUMNS} FROM workouts "
        "WHERE user_id = ? AND date = ? AND workout_type = ? AND total_duration = ? ORDER BY id",
        _session_key(row),
    ).fetchall()


def admin_session(db_conn: sqlite3.Connection, row_id: int) -> dict[str, Any] | None:
    """One session by any of its row ids, or None when it no longer exists."""
    rows = admin_session_rows(db_conn, row_id)
    return _group_admin_rows(rows)[0] if rows else None


def admin_exercise_options() -> list[dict[str, Any]]:
    """Picker groups for the editor: every quest station first, then the free-workout catalog."""
    groups: list[dict[str, Any]] = []
    for skill_key, skill in SKILL_PROGRESSIONS.items():
        groups.append({
            "group": f"{PATHS[skill_key]['icon']} {skill['title']}",
            "options": [
                {
                    "value": station_exercise_name(step),
                    "label": f"{idx + 1}. {step['hebrew']}",
                    "skill_key": skill_key,
                    "stage_index": idx,
                }
                for idx, step in enumerate(skill["progressions"])
            ],
        })
    for category, exercises in DEFAULT_EXERCISES.items():
        groups.append({
            "group": category,
            "options": [
                {"value": ex["name"], "label": ex["hebrew"], "skill_key": None, "stage_index": None}
                for ex in exercises
            ],
        })
    return groups


def admin_legacy_stations(db_conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    """Stations imported from the old browser-only "כבשתי!" flags, as rows the admin can clear.

    `stage_index` stays the legacy index the flag is stored under, so a chip sent back
    to PUT /api/workouts/legacy-progress names the same station after a path changes.
    """
    rows = []
    for skill_key, indexes in _stored_legacy_progress(db_conn, user_id).items():
        steps = SKILL_PROGRESSIONS[skill_key]["progressions"]
        for legacy_idx in indexes:
            current = _legacy_to_current({skill_key: [legacy_idx]}).get(skill_key)
            if not current:
                continue  # a station dropped from the path
            rows.append({
                "skill_key": skill_key,
                "path": PATHS[skill_key]["name"],
                "icon": PATHS[skill_key]["icon"],
                "stage_index": legacy_idx,
                "station": steps[current[0]]["hebrew"],
            })
    return rows
