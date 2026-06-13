import sqlite3
import logging
from typing import Dict, List, Any
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path as FSPath

from ..db import get_db_conn
from ..schemas.workouts import WorkoutCreateSchema

logger = logging.getLogger(__name__)

# Resolve template paths matching existing routes style
ROOT_DIR = FSPath(__file__).resolve().parents[3]
FRONTEND_DIR = ROOT_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["workouts"])

# Default Calisthenics Exercises categorized by muscle groups (with Hebrew equivalents for localized UI)
DEFAULT_EXERCISES = {
    "Push (דחיפה)": [
        {"name": "Push-ups", "hebrew": "שכיבות סמיכה"},
        {"name": "Dips", "hebrew": "מקבילים"},
        {"name": "Pike Push-ups", "hebrew": "שכיבות סמיכה פייק"},
        {"name": "Handstand Push-ups", "hebrew": "עמידת ידיים שכיבות סמיכה"},
        {"name": "Diamond Push-ups", "hebrew": "שכיבות סמיכה יהלום"}
    ],
    "Pull (משיכה)": [
        {"name": "Pull-ups", "hebrew": "עליות מתח"},
        {"name": "Muscle-ups", "hebrew": "עליות כוח"},
        {"name": "Chin-ups", "hebrew": "מתח באחיזה הפוכה"},
        {"name": "Australian Pull-ups / Rows", "hebrew": "חתירה אוסטרלית"},
        {"name": "Scapula Shrugs", "hebrew": "משיכות שכמות"}
    ],
    "Core (בטן וליבה)": [
        {"name": "L-Sit", "hebrew": "אל-סיט"},
        {"name": "Hanging Leg Raises", "hebrew": "הרמות רגליים בתלייה"},
        {"name": "Plank", "hebrew": "פלאנק"},
        {"name": "Ab Wheel Rollouts", "hebrew": "גלגל בטן"},
        {"name": "Toes to Bar", "hebrew": "אצבעות למתח"}
    ],
    "Legs (רגליים)": [
        {"name": "Pistol Squats", "hebrew": "פיסטול סקוואט"},
        {"name": "Bulgarian Split Squats", "hebrew": "סקוואט בולגרי"},
        {"name": "Shrimp Squats", "hebrew": "שרימפ סקוואט"},
        {"name": "Airborne Squats", "hebrew": "איירבורן סקוואט"},
        {"name": "Calf Raises", "hebrew": "עליות תאומים"},
        {"name": "Bodyweight Squats", "hebrew": "סקוואט משקל גוף"}
    ]
}

@router.get("/workouts", response_class=HTMLResponse)
async def workout_page(
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> HTMLResponse:
    """Render the main workout tracker page with active UI and history of workouts."""
    # Resolve the logged-in user to fetch their workouts only
    user_obj = request.session.get("user")
    import os
    auth_enabled = os.environ.get("AUTH_ENABLED", "1") == "1"
    if not user_obj and auth_enabled:
        # AuthMiddleware will redirect, but as defensive fallback
        return HTMLResponse("Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)
        
    username = (user_obj.get("username") if user_obj else "Yosef").title()
    user_row = db_conn.execute("SELECT id FROM users WHERE name = ?", (username,)).fetchone()
    user_id = user_row["id"] if user_row else 1

    # Fetch workout logs from the database
    rows = db_conn.execute(
        """
        SELECT date, workout_type, total_duration, exercise_name, total_sets, total_reps
        FROM workouts
        WHERE user_id = ?
        ORDER BY date DESC, id DESC
        """,
        (user_id,)
    ).fetchall()

    # Aggregate exercises by workout session (grouped by date, type, and duration)
    workout_sessions = {}
    for r in rows:
        session_key = (r["date"], r["workout_type"], r["total_duration"])
        if session_key not in workout_sessions:
            workout_sessions[session_key] = {
                "date": r["date"],
                "workout_type": r["workout_type"],
                "total_duration": r["total_duration"],
                "exercises": []
            }
        workout_sessions[session_key]["exercises"].append({
            "name": r["exercise_name"],
            "sets": r["total_sets"],
            "reps": r["total_reps"]
        })
        
    history = list(workout_sessions.values())

    return templates.TemplateResponse(
        "pages/workout.html",
        {
            "request": request,
            "default_exercises": DEFAULT_EXERCISES,
            "history": history,
            "show_sidebar": False,  # Hide standard finance sidebar to give space for mobile-first workout UI
        }
    )

@router.post("/workouts")
async def save_workout(
    payload: WorkoutCreateSchema,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn)
):
    """Save aggregate workout data to the database."""
    user_obj = request.session.get("user")
    import os
    auth_enabled = os.environ.get("AUTH_ENABLED", "1") == "1"
    if not user_obj and auth_enabled:
        return JSONResponse({"status": "error", "message": "Not authenticated"}, status_code=status.HTTP_401_UNAUTHORIZED)

    username = (user_obj.get("username") if user_obj else "Yosef").title()
    user_row = db_conn.execute("SELECT id FROM users WHERE name = ?", (username,)).fetchone()
    user_id = user_row["id"] if user_row else 1

    if not payload.exercises:
        return JSONResponse({"status": "error", "message": "No exercises performed in this workout."}, status_code=status.HTTP_400_BAD_REQUEST)

    try:
        # Insert each exercise row
        for ex in payload.exercises:
            if ex.total_sets > 0:
                db_conn.execute(
                    """
                    INSERT INTO workouts (user_id, date, workout_type, total_duration, exercise_name, total_sets, total_reps)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        payload.date,
                        payload.workout_type,
                        payload.total_duration,
                        ex.exercise_name,
                        ex.total_sets,
                        ex.total_reps
                    )
                )
        db_conn.commit()
        return {"status": "success", "message": "Workout saved successfully!"}
    except Exception as e:
        logger.exception("Failed to save workout session")
        return JSONResponse({"status": "error", "message": f"Database error: {str(e)}"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
