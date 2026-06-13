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

# Calisthenics Skill Progressions and Biomechanical cues
SKILL_PROGRESSIONS = {
    "muscle_up": {
        "title": "עליית כוח (Muscle-Up)",
        "difficulty": "רמת קושי: בינוני-מתקדם",
        "muscles": "שרירים עיקריים: גב, כתפיים, יד אחורית, חזה",
        "warmup": "זמן חימום מומלץ: 10-12 דקות",
        "cues": [
            "תנאי סף: יכולת ביצוע של 10-11 עליות מתח נקיות לגובה החזה ו-15 מקבילים.",
            "אחיזה כוזבת (False Grip) מונעת את הצורך לסובב את כף היד במעבר הקריטי ומייצבת את שורש כף היד.",
            "תנועת משיכה קשתית מתפרצת להבאת הגוף מעבר לגובה המוט, תוך השתחלות קדימה מעל המוט בסיום.",
            "ניתן להשתמש בתנופת רגליים קלה (Kipping) או מנח L-Sit בשלבים הראשונים לצמצום העומס."
        ],
        "progressions": [
            {"name": "Basic Pull-ups", "hebrew": "עליות מתח בסיסיות", "reps": 10, "rest": 90},
            {"name": "Basic Dips", "hebrew": "שכיבות סמיכה במקבילים", "reps": 12, "rest": 90},
            {"name": "Toes to Bar", "hebrew": "הרמת אצבעות למתח", "reps": 8, "rest": 90},
            {"name": "Straight Bar Dips", "hebrew": "מקבילים על מוט ישר", "reps": 8, "rest": 90},
            {"name": "Explosive Pull-ups", "hebrew": "מתח מתפרץ / מחיאת כף", "reps": 5, "rest": 120},
            {"name": "Negative Muscle-Up", "hebrew": "עליית כוח שלילית איטית", "reps": 3, "rest": 120},
            {"name": "Assisted Muscle-Up (Band)", "hebrew": "עליית כוח עם גומייה", "reps": 5, "rest": 120},
            {"name": "Full Muscle-Up", "hebrew": "עליית כוח מלאה", "reps": 3, "rest": 180}
        ]
    },
    "front_lever": {
        "title": "סמיכה קדמית (Front Lever)",
        "difficulty": "רמת קושי: מתקדם",
        "muscles": "שרירים עיקריים: רחב גבי, כתף אחורית, גב עליון, ליבה",
        "warmup": "זמן חימום מומלץ: 10-12 דקות",
        "cues": [
            "הבסיס הביומכני מתחיל ב'תלייה פעילה' (Active Hang) - שכמות מכווצות לאחור ומטה.",
            "משיכה קבועה של המוט כלפי מטה לעבר האגן תוך נעילת מרפקים מלאה ('לשבור את המוט לשניים').",
            "התקדמות במנופים מאפשרת הארכה הדרגתית של הגוף תוך הגדלת מומנט הכוח בכתף.",
            "שילוב תרגילים דינמיים כמו דדליפט הפוך או חתירות מנוף מסייע בבניית כוח אבסולוטי."
        ],
        "progressions": [
            {"name": "Active Scapula Hangs", "hebrew": "תלייה פעילה וכיווץ שכמות", "reps": 12, "rest": 90},
            {"name": "Tuck Front Lever Hold", "hebrew": "סמיכה קדמית מקופלת (החזקה)", "reps": 15, "rest": 90},
            {"name": "Advanced Tuck FL Hold", "hebrew": "סמיכה קדמית מקופלת מתקדמת", "reps": 12, "rest": 90},
            {"name": "Hanging Leg Raises", "hebrew": "הרמות רגליים ישרות למוט", "reps": 10, "rest": 90},
            {"name": "Reversed Deadlift (FL Pulls)", "hebrew": "דדליפט הפוך בתלייה", "reps": 5, "rest": 120},
            {"name": "Tuck FL Rows", "hebrew": "חתירות בסמיכה קדמית מקופלת", "reps": 6, "rest": 120},
            {"name": "Straddle Front Lever Hold", "hebrew": "סמיכה קדמית בפיסוק רגליים", "reps": 8, "rest": 120},
            {"name": "One-Legged FL Hold", "hebrew": "סמיכה קדמית - רגל אחת מיושרת", "reps": 8, "rest": 120},
            {"name": "Full Front Lever Hold", "hebrew": "סמיכה קדמית מלאה", "reps": 5, "rest": 180}
        ]
    },
    "planche": {
        "title": "פלאנץ' (Planche)",
        "difficulty": "רמת קושי: מתקדם מאוד / עילית",
        "muscles": "שרירים עיקריים: כתפיים קדמיות, חזה, שכמות, דו-ראשי",
        "warmup": "זמן חימום מומלץ: 8-10 דקות לשורש כף היד",
        "cues": [
            "נעילת מרפקים מלאה וסיבובם קדימה כדי להעביר את העומס הסטטי לגיד הדו-ראשי.",
            "הרחקה שכמתית עמוקה (Scapular Protraction) - עיגול קל של הגב העליון ודחיפה חזקה של הרצפה.",
            "הישענות קדימה אל מעבר לקו האצבעות כדי לפצות על משקל פלג הגוף התחתון.",
            "תרגול עמידת L מקופלת (Tucked L-Sit) מסייע בבניית הרמה והרחקת שכמות בטוחה."
        ],
        "progressions": [
            {"name": "Planche Lean", "hebrew": "הישענות פלאנץ' על הקרקע", "reps": 20, "rest": 90},
            {"name": "Tucked L-Sit", "hebrew": "עמידת L מקופלת", "reps": 15, "rest": 90},
            {"name": "Frog Stand", "hebrew": "עמידת צפרדע", "reps": 15, "rest": 90},
            {"name": "Tuck Planche Hold", "hebrew": "פלאנץ' מקופל (החזקה)", "reps": 10, "rest": 120},
            {"name": "One-Legged Advanced Tuck", "hebrew": "פלאנץ' מתקדם רגל אחת שלוחה", "reps": 8, "rest": 120},
            {"name": "Advanced Tuck Planche", "hebrew": "פלאנץ' מקופל מתקדם", "reps": 8, "rest": 120},
            {"name": "Straddle Planche Hold", "hebrew": "פלאנץ' בפיסוק", "reps": 5, "rest": 150},
            {"name": "Full Planche Hold", "hebrew": "פלאנץ' מלא", "reps": 3, "rest": 180}
        ]
    },
    "hspu": {
        "title": "שכיבות סמיכה בעמידת ידיים (HSPU)",
        "difficulty": "רמת קושי: בינוני-מתקדם",
        "muscles": "שרירים עיקריים: כתפיים, יד אחורית, שכמות, ליבה",
        "warmup": "זמן חימום מומלץ: 15-20 דקות (שורש כף היד והכתף)",
        "cues": [
            "שמירה על מרפקים צמודים לגוף/פנימה במהלך הירידה למניעת עומסי גזירה בכתף.",
            "ביצוע ירידה זוויתית לפנים ליצירת 'בסיס משולש' (הראש מונח קדימה מקו הידיים ברצפה).",
            "כיווץ מוחלט של הישבן והרגליים לשמירת קו גוף ישר ומניעת הקשתת יתר בגב התחתון.",
            "שימוש בתמיכת קיר מאפשר בידוד של כוח הלחיצה לפני שילוב האיזון החופשי."
        ],
        "progressions": [
            {"name": "Wall-Assisted Handstand Hold", "hebrew": "עמידת ידיים נתמכת קיר (החזקה)", "reps": 30, "rest": 90},
            {"name": "Wall Walks (Holds)", "hebrew": "טיפוס קיר לעמידת ידיים", "reps": 5, "rest": 90},
            {"name": "Pike Push-ups", "hebrew": "שכיבות סמיכה פייק", "reps": 10, "rest": 90},
            {"name": "Elevated Pike Push-ups", "hebrew": "שכיבות סמיכה פייק מוגבהות", "reps": 8, "rest": 90},
            {"name": "Negative Wall HSPU", "hebrew": "ירידה אקסצנטרית לקיר", "reps": 4, "rest": 120},
            {"name": "Wall-Assisted HSPU", "hebrew": "שכיבות סמיכה בעמידת ידיים (קיר)", "reps": 5, "rest": 120},
            {"name": "Straddle Freestanding HSPU", "hebrew": "שכיבות סמיכה חופשיות בפיסוק", "reps": 3, "rest": 150},
            {"name": "Full Freestanding HSPU", "hebrew": "שכיבות סמיכה בעמידת ידיים מלאה", "reps": 3, "rest": 180}
        ]
    },
    "human_flag": {
        "title": "דגל אנושי (Human Flag)",
        "difficulty": "רמת קושי: מתקדם",
        "muscles": "שרירים עיקריים: כתפיים, אלכסוני הבטן, רחב גבי, יד קדמית",
        "warmup": "זמן חימום מומלץ: 10-12 דקות (גיוס שכמה וצד גוף)",
        "cues": [
            "פעולה א-סימטרית: זרוע תחתונה דוחפת בעוצמה (מרפק ישר), זרוע עליונה מושכת חזק.",
            "כיווץ אגרסיבי של האלכסונים (Obliques) והשרשרת הצדית להרמת הירך והרגליים.",
            "הקפדה על יישור אנכי של הידיים למניעת רוטציה (פיתול) של האגן הצידה.",
            "אחיזה בסולם שווקי (Stall Bars) נוחה ומומלצת בהרבה מאשר עמוד אנכי בודד."
        ],
        "progressions": [
            {"name": "One Arm Active Hang", "hebrew": "תלייה פעילה ביד אחת", "reps": 20, "rest": 90},
            {"name": "One Arm Inverted Support", "hebrew": "תמיכה הפוכה ביד אחת", "reps": 15, "rest": 90},
            {"name": "Low Flag Hold", "hebrew": "החזקת דגל נמוך (אלכסוני)", "reps": 10, "rest": 90},
            {"name": "High Flag Hold (Wall Walk)", "hebrew": "דגל עליון אנכי (עזרה)", "reps": 12, "rest": 90},
            {"name": "Angled Tucked Flag Hold", "hebrew": "דגל מקופל בזווית גבוהה", "reps": 10, "rest": 120},
            {"name": "Twisted Flag Hold", "hebrew": "דגל מפותל (חזה למעלה)", "reps": 8, "rest": 120},
            {"name": "Tuck Human Flag Hold", "hebrew": "דגל אנושי מקופל (אופקי)", "reps": 8, "rest": 120},
            {"name": "Straddle Human Flag Hold", "hebrew": "דגל אנושי בפיסוק", "reps": 5, "rest": 150},
            {"name": "Full Human Flag Hold", "hebrew": "דגל אנושי מלא", "reps": 5, "rest": 180}
        ]
    }
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
            "skills_guide": SKILL_PROGRESSIONS,
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
