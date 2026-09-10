import sqlite3
import logging
from datetime import date as date_cls, timedelta
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

# ====================== GAMIFICATION ENGINE ======================
# XP is derived deterministically from workout history, so no schema change
# is needed — every saved workout "earns" points retroactively as well.

XP_BASE_PER_WORKOUT = 50   # showing up is most of the battle
XP_PER_SET = 10
XP_PER_REP = 1
XP_PER_MINUTE = 2
XP_MINUTES_CAP = 120       # don't reward leaving the timer running overnight

# Rank titles unlocked by level (level -> title)
RANKS = [
    (1, "טירון ברזל", "fa-seedling"),
    (3, "חניך מתאמן", "fa-user-ninja"),
    (5, "לוחם רחוב", "fa-hand-fist"),
    (8, "לוחם מתקדם", "fa-shield-halved"),
    (12, "אלוף השכונה", "fa-medal"),
    (16, "מאסטר קליסטניקס", "fa-trophy"),
    (20, "אגדה חיה", "fa-crown"),
]


def _session_xp(total_sets: int, total_reps: int, duration_minutes: int) -> int:
    """XP earned by a single workout session."""
    return (
        XP_BASE_PER_WORKOUT
        + XP_PER_SET * max(0, total_sets)
        + XP_PER_REP * max(0, total_reps)
        + XP_PER_MINUTE * min(max(0, duration_minutes), XP_MINUTES_CAP)
    )


def _xp_needed_for_level(level: int) -> int:
    """XP needed to advance FROM the given level to the next one."""
    return 100 + (level - 1) * 75


def _level_from_xp(total_xp: int) -> Dict[str, int]:
    """Convert total XP into level + progress inside the current level."""
    level = 1
    remaining = total_xp
    while remaining >= _xp_needed_for_level(level):
        remaining -= _xp_needed_for_level(level)
        level += 1
    needed = _xp_needed_for_level(level)
    return {
        "level": level,
        "xp_in_level": remaining,
        "xp_for_next": needed,
        "progress_pct": min(100, round(remaining * 100 / needed)),
    }


def _rank_for_level(level: int) -> Dict[str, str]:
    title, icon = RANKS[0][1], RANKS[0][2]
    for min_level, rank_title, rank_icon in RANKS:
        if level >= min_level:
            title, icon = rank_title, rank_icon
    return {"title": title, "icon": icon}


def _next_rank_for_level(level: int) -> Dict[str, Any]:
    for min_level, rank_title, _ in RANKS:
        if level < min_level:
            return {"title": rank_title, "level": min_level}
    return {}


def _compute_streak(dates: List[str]) -> int:
    """Longest run of consecutive workout days ending at the most recent workout."""
    day_set = set()
    for d in dates:
        try:
            day_set.add(date_cls.fromisoformat(d[:10]))
        except (ValueError, TypeError):
            continue
    if not day_set:
        return 0
    streak = 1
    day = max(day_set)
    while day - timedelta(days=1) in day_set:
        streak += 1
        day -= timedelta(days=1)
    return streak


def compute_gamification(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate workout history into the full player-profile game state."""
    total_workouts = len(history)
    total_sets = 0
    total_reps = 0
    total_minutes = 0
    total_xp = 0
    longest_session = 0
    max_exercises_in_session = 0

    for session in history:
        session_sets = sum(ex["sets"] for ex in session["exercises"])
        session_reps = sum(ex["reps"] for ex in session["exercises"])
        duration = session.get("total_duration") or 0
        total_sets += session_sets
        total_reps += session_reps
        total_minutes += duration
        longest_session = max(longest_session, duration)
        max_exercises_in_session = max(max_exercises_in_session, len(session["exercises"]))
        total_xp += _session_xp(session_sets, session_reps, duration)

    streak = _compute_streak([s["date"] for s in history])
    level_info = _level_from_xp(total_xp)
    level = level_info["level"]

    achievement_defs = [
        ("first_steps", "fa-shoe-prints", "צעד ראשון", "השלם אימון ראשון", total_workouts, 1),
        ("warming_up", "fa-fire", "מתחמם", "השלם 5 אימונים", total_workouts, 5),
        ("iron_addict", "fa-dumbbell", "מכור לברזל", "השלם 15 אימונים", total_workouts, 15),
        ("local_legend", "fa-crown", "אגדה מקומית", "השלם 50 אימונים", total_workouts, 50),
        ("set_collector", "fa-layer-group", "אספן סטים", "בצע 100 סטים במצטבר", total_sets, 100),
        ("set_machine", "fa-industry", "מכונת סטים", "בצע 500 סטים במצטבר", total_sets, 500),
        ("rep_1000", "fa-bolt", "אלף חזרות", "בצע 1,000 חזרות במצטבר", total_reps, 1000),
        ("rep_5000", "fa-meteor", "5,000 חזרות", "בצע 5,000 חזרות במצטבר", total_reps, 5000),
        ("streak_3", "fa-fire-flame-curved", "על הגל", "3 ימי אימון ברצף", streak, 3),
        ("streak_7", "fa-calendar-week", "שבוע מושלם", "7 ימי אימון ברצף", streak, 7),
        ("marathon", "fa-stopwatch", "מרתוניסט", "אימון של 60 דקות ומעלה", longest_session, 60),
        ("variety", "fa-shapes", "מגוון אישי", "5 תרגילים שונים באימון אחד", max_exercises_in_session, 5),
    ]
    achievements = [
        {
            "id": a_id,
            "icon": icon,
            "title": title,
            "desc": desc,
            "current": min(current, target),
            "target": target,
            "unlocked": current >= target,
        }
        for a_id, icon, title, desc, current, target in achievement_defs
    ]

    return {
        "total_xp": total_xp,
        "level": level,
        "xp_in_level": level_info["xp_in_level"],
        "xp_for_next": level_info["xp_for_next"],
        "progress_pct": level_info["progress_pct"],
        "rank": _rank_for_level(level),
        "next_rank": _next_rank_for_level(level),
        "streak": streak,
        "total_workouts": total_workouts,
        "total_sets": total_sets,
        "total_reps": total_reps,
        "total_minutes": total_minutes,
        "achievements": achievements,
        "unlocked_count": sum(1 for a in achievements if a["unlocked"]),
    }


def _resolve_user_id(request: Request, db_conn: sqlite3.Connection):
    """Resolve logged-in user id, or None when auth is enabled and no session."""
    import os
    user_obj = request.session.get("user")
    auth_enabled = os.environ.get("AUTH_ENABLED", "1") == "1"
    if not user_obj and auth_enabled:
        return None
    username = (user_obj.get("username") if user_obj else "Yosef").title()
    user_row = db_conn.execute("SELECT id FROM users WHERE name = ?", (username,)).fetchone()
    return user_row["id"] if user_row else 1


def _fetch_history(db_conn: sqlite3.Connection, user_id: int) -> List[Dict[str, Any]]:
    """Fetch workout rows and aggregate them into per-session dicts."""
    rows = db_conn.execute(
        """
        SELECT date, workout_type, total_duration, exercise_name, total_sets, total_reps
        FROM workouts
        WHERE user_id = ?
        ORDER BY date DESC, id DESC
        """,
        (user_id,)
    ).fetchall()

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
    return list(workout_sessions.values())


@router.get("/workouts", response_class=HTMLResponse)
async def workout_page(
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> HTMLResponse:
    """Render the main workout tracker page with active UI and history of workouts."""
    user_id = _resolve_user_id(request, db_conn)
    if user_id is None:
        # AuthMiddleware will redirect, but as defensive fallback
        return HTMLResponse("Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

    history = _fetch_history(db_conn, user_id)
    game = compute_gamification(history)

    return templates.TemplateResponse(
        "pages/workout.html",
        {
            "request": request,
            "default_exercises": DEFAULT_EXERCISES,
            "history": history,
            "skills_guide": SKILL_PROGRESSIONS,
            "game": game,
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
        # Snapshot game state before saving to detect level-ups and new badges
        game_before = compute_gamification(_fetch_history(db_conn, user_id))

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

        game_after = compute_gamification(_fetch_history(db_conn, user_id))
        unlocked_before = {a["id"] for a in game_before["achievements"] if a["unlocked"]}
        new_achievements = [
            {"icon": a["icon"], "title": a["title"], "desc": a["desc"]}
            for a in game_after["achievements"]
            if a["unlocked"] and a["id"] not in unlocked_before
        ]

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
                "xp_in_level": game_after["xp_in_level"],
                "xp_for_next": game_after["xp_for_next"],
                "progress_pct": game_after["progress_pct"],
                "streak": game_after["streak"],
                "new_achievements": new_achievements,
            },
        }
    except Exception as e:
        logger.exception("Failed to save workout session")
        return JSONResponse({"status": "error", "message": f"Database error: {str(e)}"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
