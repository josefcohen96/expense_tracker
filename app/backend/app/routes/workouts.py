import json
import logging
import sqlite3
from datetime import date as date_cls
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, JSONResponse

from ..db import get_db_conn
from ..schemas.workouts import WorkoutCreateSchema, WorkoutLegacyProgressSchema
from ..services import spanish as spanish_service
from ..services.access import USER_YOSEF, is_module_only_user, normalise_username
from ..services.people import workout_people
from ..services.wedding_plan import get_wedding_date
from ..services.workouts.admin import admin_exercise_options, admin_legacy_stations, admin_sessions
from ..services.workouts.catalog import (
    DEFAULT_EXERCISES,
    EXERCISE_CATALOG,
    SKILL_PROGRESSIONS,
    STATION_SESSIONS_TO_CONQUER,
    WORKOUT_TYPE_LABELS,
    exercise_form_data,
)
from ..services.workouts.holo import HOLO_MODEL_URL, _holo_clip_cache, holo_clip_bounds, holo_clips, holo_front_clips
from ..services.workouts.legacy import (
    _clean_progress,
    _legacy_progress_key,
    _load_legacy_progress,
    _stored_legacy_progress,
)
from ..services.workouts.progress import (
    _ago_label,
    _exercise_title,
    _fetch_history,
    _parse_day,
    _station_for,
    _station_progress,
    compute_gamification,
    compute_paths,
    compute_records,
    plan_today,
    wedding_boss,
)
from ..templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workouts"])


def _session_user(request: Request) -> dict[str, Any] | None:
    """The logged-in user as AuthMiddleware resolved it (session, or the signed-cookie fallback)."""
    return getattr(request.state, "user", None) or request.session.get("user")


def _resolve_user_id(request: Request, db_conn: sqlite3.Connection):
    """Resolve logged-in user id, or None when auth is enabled and no session."""
    import os
    user_obj = _session_user(request)
    auth_enabled = os.environ.get("AUTH_ENABLED", "1") == "1"
    if not user_obj and auth_enabled:
        return None
    username = (user_obj.get("username") if user_obj else "Yosef").title()
    user_row = db_conn.execute("SELECT id FROM users WHERE name = ?", (username,)).fetchone()
    if user_row:
        return user_row["id"]
    # A login without a users row yet (a DB restored from before it was seeded):
    # give it one rather than silently crediting its workouts to user 1.
    cur = db_conn.execute("INSERT INTO users (name) VALUES (?)", (username,))
    db_conn.commit()
    return cur.lastrowid


SPANISH_QUEUE_IN_PAGE = 12  # cards rendered into client_data; the JS tops up from the queue endpoint


@router.get("/workouts", response_class=HTMLResponse)
async def workout_page(
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> HTMLResponse:
    """Render the workout page: quest select, map, profile, history, and the arena shell."""
    user_id = _resolve_user_id(request, db_conn)
    if user_id is None:
        # AuthMiddleware will redirect, but as defensive fallback
        return HTMLResponse("Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

    today = date_cls.today()
    history = _fetch_history(db_conn, user_id)
    # Spanish between sets: the first cards ship with the page so a rest never waits on the network
    spanish = spanish_service.snapshot(db_conn, user_id, today, limit=SPANISH_QUEUE_IN_PAGE)
    game = compute_gamification(history, today, spanish_in_pocket=spanish["stats"]["in_pocket"])
    paths = compute_paths(history, game["level"], _load_legacy_progress(db_conn, user_id), today)
    records = compute_records(history)
    unlocked = [p for p in paths if p["unlocked"]]
    default_path, coach_note = plan_today(paths, history, today)
    first_workout = game["total_workouts"] == 0

    # The wedding as the final boss is Yosef's alone; everyone else gets None.
    boss = None
    if normalise_username(_session_user(request)) == USER_YOSEF:
        wedding_date = get_wedding_date(db_conn)
        if wedding_date:
            boss = wedding_boss(history, paths, wedding_date, today)

    for session in history:
        day = _parse_day(session["date"])
        session["ago"] = _ago_label((today - day).days) if day else ""

    # Everything the arena needs without a request per set
    client_data = {
        "default_path": default_path,
        "paths": {
            p["key"]: {
                "name": p["name"],
                "icon": p["icon"],
                "unlocked": p["unlocked"],
                "workout_type": p["workout_type"],
                "category": p["category"],
                "plan": p["plan"],
                "warmup": p["warmup"],
                "warmup_minutes": p["warmup_minutes"],
            }
            for p in paths
        },
        "stations": {
            p["key"]: [
                {"name": st["exercise_name"], "title": st["hebrew"], "reps": st["reps"],
                 "rest": st["rest"], "unit": st["unit"], "unit_label": st["unit_label"]}
                for st in p["stations"]
            ]
            for p in paths
        },
        "records": {name: {"best": r["best"], "last": r["last"]} for name, r in records.items()},
        "catalog": EXERCISE_CATALOG,
        "form": exercise_form_data(),
        "first_workout": first_workout,
        "spanish": {
            "queue": spanish["items"],
            "stats": spanish["stats"],
            "study_new_cap": spanish_service.STUDY_NEW_CAP,
        },
    }
    clips = holo_clips()
    if clips:
        version = _holo_clip_cache["stamp"][0]  # mtime, so a new model busts the cache
        client_data["holo"] = {"model": f"{HOLO_MODEL_URL}?v={version}", "clips": sorted(clips),
                               "front": sorted(holo_front_clips() & clips),
                               "bounds": holo_clip_bounds()}

    return templates.TemplateResponse(
        request,
        "pages/workout.html",
        {
            "request": request,
            "default_exercises": DEFAULT_EXERCISES,
            "type_labels": WORKOUT_TYPE_LABELS,
            "history": history,
            "skills_guide": SKILL_PROGRESSIONS,
            "paths": paths,
            "paths_by_key": {p["key"]: p for p in paths},
            "default_path": default_path,
            "coach_note": coach_note,
            "wedding_boss": boss,
            "first_workout": first_workout,
            "first_workout_xp": min(p["plan"]["xp"] for p in unlocked),
            "sessions_to_conquer": STATION_SESSIONS_TO_CONQUER,
            "game": game,
            "spanish": {
                **spanish["stats"],
                "themes": spanish_service.theme_progress(spanish_service.load_deck(), spanish["stats"]),
            },
            "client_data": client_data,
            "module_only": is_module_only_user(_session_user(request)),
            "show_sidebar": False,  # Hide standard finance sidebar to give space for mobile-first workout UI
        }
    )


@router.post("/workouts")
async def save_workout(
    payload: WorkoutCreateSchema,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn)
):
    """Save aggregate workout data and return the game rewards it earned."""
    user_id = _resolve_user_id(request, db_conn)
    if user_id is None:
        return JSONResponse({"status": "error", "message": "Not authenticated"}, status_code=status.HTTP_401_UNAUTHORIZED)

    if not payload.exercises:
        return JSONResponse({"status": "error", "message": "No exercises performed in this workout."}, status_code=status.HTTP_400_BAD_REQUEST)

    try:
        today = date_cls.today()
        legacy = _load_legacy_progress(db_conn, user_id)

        # Snapshot game state before saving to detect level-ups, new badges, stations and records
        history_before = _fetch_history(db_conn, user_id)
        game_before = compute_gamification(history_before, today)
        records_before = compute_records(history_before)
        conquered_before = {
            (p["key"], st["index"])
            for p in compute_paths(history_before, game_before["level"], legacy, today)
            for st in p["stations"] if st["conquered"]
        }

        # Insert each exercise row
        session_best: dict[str, tuple[int, str]] = {}
        for ex in payload.exercises:
            if ex.total_sets > 0:
                station = _station_for(ex.skill_key, ex.stage_index, ex.exercise_name)
                max_reps = None if ex.max_reps is None else max(0, min(ex.max_reps, ex.total_reps))
                db_conn.execute(
                    """
                    INSERT INTO workouts (user_id, date, workout_type, total_duration, exercise_name,
                                          total_sets, total_reps, skill_key, stage_index, max_reps)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        payload.date,
                        payload.workout_type,
                        payload.total_duration,
                        ex.exercise_name,
                        ex.total_sets,
                        ex.total_reps,
                        station[0] if station else None,
                        station[1] if station else None,
                        max_reps,
                    )
                )
                if max_reps and max_reps > session_best.get(ex.exercise_name, (0, ""))[0]:
                    session_best[ex.exercise_name] = (max_reps, _exercise_title(ex.exercise_name, station))
        db_conn.commit()

        history_after = _fetch_history(db_conn, user_id)
        game_after = compute_gamification(history_after, today)
        unlocked_before = {a["id"] for a in game_before["achievements"] if a["unlocked"]}
        new_achievements = [
            {"icon": a["icon"], "title": a["title"], "desc": a["desc"]}
            for a in game_after["achievements"]
            if a["unlocked"] and a["id"] not in unlocked_before
        ]

        paths_after = compute_paths(history_after, game_after["level"], legacy, today)
        new_stations = []
        for p in paths_after:
            for st in p["stations"]:
                if st["conquered"] and not st["skipped"] and (p["key"], st["index"]) not in conquered_before:
                    new_stations.append({
                        "path": p["name"],
                        "icon": p["icon"],
                        "station": st["hebrew"],
                        "next": p["current"]["hebrew"] if p["current"] else None,
                    })
        station_progress = _station_progress(payload.exercises, paths_after)

        # Personal records only count against real history for the same exercise
        new_records = []
        for name, (reps, title) in session_best.items():
            previous = records_before.get(name)
            if previous and reps > previous["best"]:
                previous_day = _parse_day(previous["best_date"])
                new_records.append({
                    "exercise_name": name,
                    "title": title,
                    "reps": reps,
                    "previous": previous["best"],
                    "previous_ago": _ago_label((today - previous_day).days) if previous_day else None,
                })

        return {
            "status": "success",
            "message": "Workout saved successfully!",
            "rewards": {
                "xp_gained": game_after["total_xp"] - game_before["total_xp"],
                "total_xp": game_after["total_xp"],
                "old_level": game_before["level"],
                "new_level": game_after["level"],
                "leveled_up": game_after["level"] > game_before["level"],
                "rank": game_after["rank"],
                "next_rank": game_after["next_rank"],
                "xp_in_level": game_after["xp_in_level"],
                "xp_for_next": game_after["xp_for_next"],
                "progress_pct": game_after["progress_pct"],
                "streak": game_after["streak"],
                "new_achievements": new_achievements,
                "new_stations": new_stations,
                "station_progress": station_progress,
                "new_records": new_records,
            },
        }
    except Exception as e:
        logger.exception("Failed to save workout session")
        return JSONResponse({"status": "error", "message": f"Database error: {str(e)}"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.get("/workouts/admin", response_class=HTMLResponse)
async def workout_admin_page(
    request: Request,
    user: int | None = None,
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> HTMLResponse:
    """Back office for the workouts module: every saved session, editable row by row."""
    viewer_id = _resolve_user_id(request, db_conn)
    if viewer_id is None:
        return HTMLResponse("Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

    # A workouts-only login (Yonatan) manages just their own sessions; the
    # household picks anyone who trains.
    people = workout_people(db_conn, _session_user(request))
    ids = [p["id"] for p in people]
    selected_id = user if user in ids else (viewer_id if viewer_id in ids else (ids[0] if ids else viewer_id))
    selected_person = next((p for p in people if p["id"] == selected_id), None)

    today = date_cls.today()
    sessions = admin_sessions(db_conn, selected_id)
    for session in sessions:
        day = _parse_day(session["date"])
        session["ago"] = _ago_label((today - day).days) if day else ""
    game = compute_gamification(_fetch_history(db_conn, selected_id), today)

    return templates.TemplateResponse(
        request,
        "pages/workout_admin.html",
        {
            "request": request,
            "people": people,
            "selected_id": selected_id,
            "selected_person": selected_person,
            "sessions": sessions,
            "game": game,
            "legacy_stations": admin_legacy_stations(db_conn, selected_id),
            "type_labels": WORKOUT_TYPE_LABELS,
            "client_data": {
                "user_id": selected_id,
                "sessions": sessions,
                "exercise_options": admin_exercise_options(),
                "type_labels": WORKOUT_TYPE_LABELS,
            },
            "show_sidebar": False,
        }
    )


@router.post("/workouts/legacy-progress")
async def import_legacy_progress(
    payload: WorkoutLegacyProgressSchema,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn)
):
    """One-time import of stations a browser had marked "כבשתי!" before conquering was counted."""
    user_id = _resolve_user_id(request, db_conn)
    if user_id is None:
        return JSONResponse({"status": "error", "message": "Not authenticated"}, status_code=status.HTTP_401_UNAUTHORIZED)

    merged = _stored_legacy_progress(db_conn, user_id)  # merged and stored in legacy indexes
    for skill_key, indexes in _clean_progress(payload.progress).items():
        merged[skill_key] = sorted(set(merged.get(skill_key, [])) | set(indexes))
    db_conn.execute(
        "INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
        (_legacy_progress_key(user_id), json.dumps(merged)),
    )
    db_conn.commit()
    return {"status": "success", "stations": sum(len(v) for v in merged.values())}
