import json
import math
import mimetypes
import re
import sqlite3
import struct
import logging
from datetime import date as date_cls, timedelta
from statistics import median
from typing import Dict, List, Any, Iterable, Optional, Set, Tuple
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path as FSPath

from ..db import get_db_conn
from ..schemas.workouts import WorkoutCreateSchema, WorkoutLegacyProgressSchema
from ..services.people import household

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
        {"name": "Handstand Push-ups", "hebrew": "שכיבות סמיכה בעמידת ידיים"},
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

# Calisthenics skill progressions.
# Every station carries the way it is trained: `unit` ("reps" or "sec" for a static hold),
# the target that conquers it, the rest after a set, one "how it is done" line and two
# short form cues of its own. Station order follows the accepted progression for each
# skill — an easier lever always comes before a longer one.

def _station(name, hebrew, reps, rest, how, cues, unit="reps"):
    """One quest station. `reps` is a count, or seconds when unit is 'sec'."""
    return {"name": name, "hebrew": hebrew, "unit": unit, "reps": reps, "rest": rest,
            "how": how, "cues": [{"pin": pin, "text": text} for pin, text in cues]}


SKILL_PROGRESSIONS = {
    "muscle_up": {
        "title": "עליית כוח (Muscle-Up)",
        "difficulty": "רמת קושי: בינוני-מתקדם",
        "muscles": "שרירים עיקריים: רחב גבי, כתפיים, יד אחורית, חזה",
        "warmup": "זמן חימום מומלץ: 10-12 דקות — שכמות, שורש כף היד ומרפקים",
        "prereq": "תנאי סף למסלול: 8-10 עליות מתח נקיות, 8-10 מקבילים ו-20 שניות תלייה באחיזה כוזבת.",
        "cues": [
            "אחיזה כוזבת (False Grip): פרק כף היד עולה מעל המוט עוד לפני המשיכה — היא מקצרת את המעבר ומייתרת סיבוב של כף היד באמצע התנועה.",
            "המשיכה קשתית: מושכים את המוט אל עצם החזה תוך הטיית הגוף אחורה, ולא אנכית כמו בעליית מתח רגילה.",
            "המעבר (Transition) הוא מה שנתקע — לא המשיכה ולא המקבילים. מתאמנים עליו בנפרד על מוט נמוך.",
            "תנופת רגליים (Kipping) מותרת בשלבים הראשונים, אבל היעד הוא עלייה נקייה מכוח הכתף והגב.",
        ],
        "progressions": [
            _station("Basic Pull-ups", "עליות מתח בסיסיות", 10, 90,
                     "תלייה מלאה בתחתית, משיכה עד שהסנטר עובר את המוט, בלי תנופה מהאגן.",
                     [("שכמות קודם", "מתחילים מהורדת השכמות ורק אז מכופפים מרפקים."),
                      ("טווח מלא", "יורדים לזרועות ישרות בכל חזרה — חצי טווח לא נספר.")]),
            _station("Basic Dips", "מקבילים", 12, 90,
                     "יורדים עד שהמרפק בזווית 90 מעלות והכתף בגובה המרפק, ודוחפים לנעילה מלאה.",
                     [("כתפיים למטה", "כתפיים רחוק מהאוזניים לאורך כל התנועה."),
                      ("נטייה קדימה", "הטיית גו קלה קדימה מכינה את מנח התמיכה של עליית הכוח.")]),
            _station("False Grip Hang", "תלייה באחיזה כוזבת", 25, 90,
                     "בסיס כף היד מונח מעל המוט והשורש מכופף סביבו — נתלים כך שהמוט יושב על השורש ולא על האצבעות.",
                     [("שורש מעל המוט", "המוט יושב על בסיס כף היד, האגודל מעליו."),
                      ("להעלות בהדרגה", "מתחילים ב-15 שניות ומוסיפים — העור והגידים צריכים זמן.")],
                     unit="sec"),
            _station("Straight Bar Dips", "מקבילים על מוט ישר", 8, 90,
                     "תמיכה על מוט ישר בגובה האגן: יורדים כשהמוט כמעט נוגע בחזה ודוחפים חזרה לנעילה.",
                     [("מוט קרוב לחזה", "המוט מלווה את הגוף — לא מתרחק ממנו."),
                      ("גו מעט קדימה", "נטייה קדימה שומרת על מרכז הכובד מעל כפות הידיים.")]),
            _station("False Grip Pull-ups", "עליות מתח באחיזה כוזבת", 6, 120,
                     "עליית מתח מלאה בלי לשחרר את האחיזה הכוזבת, עד שהחזה התחתון מגיע אל המוט.",
                     [("חזה למוט", "היעד הוא עצם החזה במוט, לא הסנטר."),
                      ("שורש נעול", "פרק כף היד נשאר כפוף מעל המוט לאורך כל החזרה.")]),
            _station("Explosive Pull-ups", "מתח מתפרץ לגובה החזה", 5, 120,
                     "משיכה מתפרצת שמביאה את המוט לגובה עצם החזה, עם ירידה בשליטה מלאה.",
                     [("להאיץ מהתחתית", "ההאצה מתחילה למטה — לא נתירה בסוף התנועה."),
                      ("צוואר ניטרלי", "לא זורקים את הראש אחורה — העבודה בגב ובכתף.")]),
            _station("Low Bar Transitions", "מעבר על מוט נמוך", 5, 120,
                     "מוט בגובה החזה: קפיצה קלה מהרגליים ותרגול רגע המעבר בלבד — חזה מעל המוט ומרפקים נפתחים לתמיכה.",
                     [("חזה נכנס ראשון", "מכניסים את החזה מעל המוט לפני שפותחים מרפקים."),
                      ("מהר בנקודה התקועה", "המעבר נעשה מהר — עצירה באמצע היא הכישלון עצמו.")]),
            _station("Assisted Muscle-Up (Band)", "עליית כוח עם גומייה", 5, 120,
                     "גומייה מתחת לכפות הרגליים או לברכיים; מבצעים עלייה מלאה ומדקקים את הגומייה ככל שמתחזקים.",
                     [("גומייה דקה יותר", "עוברים לגומייה דקה ברגע שיוצאות 5 חזרות נקיות."),
                      ("אותו מסלול", "הגומייה לא משנה את התנועה — עדיין חזה למוט ומעבר מהיר.")]),
            _station("Negative Muscle-Up", "עליית כוח שלילית איטית", 3, 150,
                     "מתחילים מתמיכה מעל המוט ויורדים כ-5 שניות דרך המעבר עד לתלייה מלאה באחיזה כוזבת.",
                     [("5 שניות", "הירידה נשלטת לכל אורכה — במיוחד ברגע המעבר."),
                      ("לא לשחרר", "האחיזה הכוזבת נשמרת גם בדרך למטה.")]),
            _station("Full Muscle-Up", "עליית כוח מלאה", 3, 180,
                     "מתלייה מלאה: משיכה קשתית אל החזה, מעבר מהיר ונעילת מרפקים בתמיכה מעל המוט.",
                     [("קשת ולא קו", "מושכים את המוט אל החזה תוך הטיה אחורה."),
                      ("נעילה למעלה", "החזרה נספרת רק עם מרפקים נעולים בתמיכה.")]),
        ],
    },
    "front_lever": {
        "title": "סמיכה קדמית (Front Lever)",
        "difficulty": "רמת קושי: מתקדם",
        "muscles": "שרירים עיקריים: רחב גבי, כתף אחורית, גב עליון, ליבה",
        "warmup": "זמן חימום מומלץ: 10-12 דקות — שכמות, מרפקים וליבה",
        "prereq": "תנאי סף למסלול: 10 עליות מתח נקיות, 15 משיכות שכמות ותלייה הפוכה יציבה.",
        "cues": [
            "הבסיס הוא תלייה פעילה: שכמות מכווצות לאחור ומטה לפני שהגוף מתחיל לעלות.",
            "מרפקים נעולים לאורך כל ההחזקה — כיפוף מרפק מקצר את המנוף והופך את התרגיל לתרגיל אחר.",
            "אגן באגירה אחורית וצלעות למטה; גב תחתון שמתקשת הוא הסימן הראשון לאובדן המנח.",
            "עוברים לתחנה הבאה כשיוצאות 15-20 שניות נקיות במנח הנוכחי — הזמן הוא המדד, לא התחושה.",
        ],
        "progressions": [
            _station("Active Scapula Hangs", "תלייה פעילה וכיווץ שכמות", 12, 90,
                     "בתלייה עם מרפקים ישרים מורידים את הכתפיים מהאוזניים ומרימים את הגוף כמה סנטימטרים, בלי לכופף מרפק.",
                     [("מרפקים ישרים", "רק השכמות זזות — המרפקים נעולים."),
                      ("למטה ואחורה", "מושכים את השכמות מטה ואחורה, לא למעלה.")]),
            _station("Hanging Leg Raises", "הרמות רגליים ישרות למוט", 10, 90,
                     "מתלייה שקטה מרימים רגליים ישרות עד מעל גובה המותן, עם גלגול אגן בסוף התנועה.",
                     [("בלי תנופה", "כל חזרה מתחילה מעצירה מוחלטת בתחתית."),
                      ("אגן מתגלגל", "סיום החזרה הוא גלגול אגן, לא רק הרמת רגליים.")]),
            _station("Tuck Front Lever Hold", "סמיכה קדמית מקופלת", 15, 90,
                     "ברכיים אל החזה והגב מקביל לקרקע — מחזיקים את הגו אופקי ולא באלכסון.",
                     [("גב מקביל", "הגב אופקי לקרקע — אלכסון הוא תחנה קלה יותר."),
                      ("משיכה למטה", "מושכים את המוט לכיוון האגן לאורך כל ההחזקה.")],
                     unit="sec"),
            _station("Advanced Tuck FL Hold", "סמיכה קדמית מקופלת מתקדמת", 12, 90,
                     "מאותו מנח מיישרים את הגב לגמרי ופותחים את הירך עד שהברכיים מעל האגן.",
                     [("ברכיים מעל האגן", "הירך נפתחת — הברך יוצאת מהחזה."),
                      ("גב שטוח", "הגב שטוח לגמרי, בלי קימור כלפי מעלה.")],
                     unit="sec"),
            _station("Tuck FL Rows", "חתירות בסמיכה קדמית מקופלת", 6, 120,
                     "במנח המקופל מושכים את החזה אל המוט ויורדים בשליטה, בלי לאבד את גובה האגן.",
                     [("אגן לא צונח", "הגוף נשאר אופקי גם כשהמרפקים מתכופפים."),
                      ("ירידה איטית", "הירידה נמשכת 2-3 שניות לפחות.")]),
            _station("Reversed Deadlift (FL Pulls)", "דדליפט הפוך בתלייה", 5, 120,
                     "מתלייה מלאה מרימים את הגוף עם מרפקים נעולים עד מנח מקופל מתקדם, ומורידים בשליטה.",
                     [("מרפקים נעולים", "כל התנועה מגיעה מהכתף ומהשכמה."),
                      ("קצב שווה", "עלייה וירידה באותו קצב — בלי תנופה.")]),
            _station("One-Legged FL Hold", "סמיכה קדמית רגל אחת", 10, 120,
                     "ממנח מקופל מתקדם מיישרים רגל אחת לגמרי והשנייה נשארת מקופלת; מחליפים רגל בין הסטים.",
                     [("אגן ישר", "האגן לא מסתובב — שתי הירכיים באותו גובה."),
                      ("להחליף צד", "אותו מספר שניות לכל רגל.")],
                     unit="sec"),
            _station("Straddle Front Lever Hold", "סמיכה קדמית בפיסוק", 10, 150,
                     "שתי הרגליים ישרות ופתוחות לצדדים — הפיסוק מקצר את המנוף ביחס לרגליים צמודות.",
                     [("לפתוח רחב", "ככל שהפיסוק רחב יותר, ההחזקה קלה יותר."),
                      ("ברכיים נעולות", "רגליים ישרות ומתוחות עד קצות האצבעות.")],
                     unit="sec"),
            _station("Half Lay Front Lever Hold", "סמיכה קדמית חצי פשוטה", 8, 150,
                     "רגליים צמודות עם ברכיים כפופות ב-90 מעלות — כמעט מנוף מלא, בלי העומס של רגליים ישרות.",
                     [("ירך פשוטה", "הירך נפתחת לגמרי, רק הברך כפופה."),
                      ("רגליים צמודות", "הברכיים והקרסוליים נוגעים זה בזה.")],
                     unit="sec"),
            _station("Full Front Lever Hold", "סמיכה קדמית מלאה", 8, 180,
                     "גוף ישר לגמרי ומקביל לקרקע, מרפקים נעולים, מהעורף ועד קצות האצבעות בקו אחד.",
                     [("קו אחד", "הכתפיים, האגן והעקבים באותו גובה."),
                      ("לנשום", "נושמים לצלעות — עצירת נשימה מקצרת את ההחזקה.")],
                     unit="sec"),
        ],
    },
    "planche": {
        "title": "פלאנץ' (Planche)",
        "difficulty": "רמת קושי: מתקדם מאוד / עילית",
        "muscles": "שרירים עיקריים: כתף קדמית, חזה, שכמות, דו-ראשי, ליבה",
        "warmup": "זמן חימום מומלץ: 8-10 דקות ייעודיות לשורש כף היד",
        "prereq": "תנאי סף למסלול: פלאנק יציב, 20 שניות הישענות פלאנץ' ושורש כף יד שסובל עומס מלא בהארכה.",
        "cues": [
            "חימום שורש כף היד לפני כל אימון הוא חלק מהתרגיל ולא המלצה — הפלאנץ' מעמיס את השורש בהארכה מלאה.",
            "מרפקים נעולים ומסובבים קדימה; כיפוף מרפק מעביר את העומס מהגיד לשריר והופך את התרגיל לתרגיל אחר.",
            "הרחקת שכמות (Protraction): דוחפים את הרצפה ומעגלים קלות את הגב העליון. כיווץ שכמות מפיל את המנח.",
            "ההישענות קדימה היא שמאזנת את הרגליים — ככל שהכתפיים עוברות את קו כף היד, כך המנח יציב יותר.",
        ],
        "progressions": [
            _station("Planche Lean", "הישענות פלאנץ'", 25, 90,
                     "בפלאנק על כפות ידיים ואצבעות לכיוון הרגליים, מזיזים את הכתפיים קדימה מעבר לקו כף היד ומחזיקים.",
                     [("כתפיים מעבר לשורש", "הכתף עוברת את קו כף היד — זה כל התרגיל."),
                      ("גוף נעול", "ישבן ובטן נעולים, בלי שקיעה באגן.")],
                     unit="sec"),
            _station("Tucked L-Sit", "עמידת L מקופלת", 20, 90,
                     "בתמיכה על מקבילונים מרימים את האגן ומקפלים ברכיים לחזה, כתפיים למטה וזרועות נעולות.",
                     [("דחיפה למטה", "דוחפים את המקבילונים ומרחיקים את הכתפיים מהאוזניים."),
                      ("אגן באוויר", "הישבן לא נוגע — כל הגוף תלוי על הידיים.")],
                     unit="sec"),
            _station("Frog Stand", "עמידת צפרדע", 20, 90,
                     "כפות ידיים על הרצפה, ברכיים נשענות על המרפקים, ומעבירים משקל קדימה עד שהרגליים מתנתקות.",
                     [("להעביר משקל", "המשקל עובר לידיים בהדרגה — לא בקפיצה."),
                      ("מבט קדימה", "מבט מעט קדימה מייצב את האיזון.")],
                     unit="sec"),
            _station("Pseudo Planche Push-ups", "שכיבות סמיכה פסאודו-פלאנץ'", 8, 120,
                     "שכיבות סמיכה עם כפות ידיים בגובה המותן ואצבעות לאחור, כשהכתפיים נשארות קדימה מול כף היד.",
                     [("ידיים נמוך", "כפות הידיים בגובה המותן, לא מתחת לחזה."),
                      ("לשמור על הנטייה", "לא נסוגים אחורה בתחתית החזרה.")]),
            _station("Tuck Planche Hold", "פלאנץ' מקופל", 12, 120,
                     "מעמידת צפרדע מיישרים את המרפקים לגמרי כשהברכיים עדיין צמודות לחזה.",
                     [("מרפקים נעולים", "נעילה מלאה — זה ההבדל מעמידת צפרדע."),
                      ("להרחיק שכמות", "דוחפים את הרצפה ומעגלים קלות את הגב העליון.")],
                     unit="sec"),
            _station("Advanced Tuck Planche", "פלאנץ' מקופל מתקדם", 10, 120,
                     "פותחים את הירך עד שהגב שטוח והברכיים מעל האגן, עם אגירה אחורית של האגן.",
                     [("גב שטוח", "הגב מקביל לקרקע ולא מקומר."),
                      ("ברכיים מעל האגן", "הירך נפתחת לזווית של 90 מעלות.")],
                     unit="sec"),
            _station("One-Legged Advanced Tuck", "פלאנץ' מתקדם רגל אחת", 10, 120,
                     "ממנח מקופל מתקדם מיישרים רגל אחת לאחור והשנייה נשארת מקופלת; מחליפים בין הסטים.",
                     [("ישבן נעול", "הרגל הישרה מוחזקת בכיווץ ישבן, לא נגררת."),
                      ("אגן ישר", "האגן לא מסתובב לצד.")],
                     unit="sec"),
            _station("Straddle Planche Hold", "פלאנץ' בפיסוק", 8, 150,
                     "שתי הרגליים ישרות ופתוחות לצדדים, גוף אופקי והכתפיים הרבה מעבר לקו כף היד.",
                     [("לפתוח רחב", "פיסוק רחב מקצר את המנוף."),
                      ("להישען עוד", "ככל שהמנוף גדל, ההישענות קדימה גדלה איתו.")],
                     unit="sec"),
            _station("Half Lay Planche Hold", "פלאנץ' חצי פשוט", 6, 150,
                     "רגליים צמודות עם ברכיים כפופות ב-90 מעלות והירך פשוטה לגמרי.",
                     [("ירך פשוטה", "הירך נפתחת לגמרי — רק הברך כפופה."),
                      ("ישבן נעול", "נעילת הישבן היא שמחזיקה את קו הגוף.")],
                     unit="sec"),
            _station("Full Planche Hold", "פלאנץ' מלא", 5, 180,
                     "גוף ישר לגמרי ומקביל לקרקע על זרועות נעולות, מהכתפיים ועד קצות האצבעות.",
                     [("קו אחד", "כתפיים, אגן ועקבים בקו אחד."),
                      ("קצר ונקי", "עדיף 3 שניות נקיות מ-6 שניות שבורות.")],
                     unit="sec"),
        ],
    },
    "hspu": {
        "title": "שכיבות סמיכה בעמידת ידיים (HSPU)",
        "difficulty": "רמת קושי: בינוני-מתקדם",
        "muscles": "שרירים עיקריים: כתפיים, יד אחורית, שכמות, ליבה",
        "warmup": "זמן חימום מומלץ: 15-20 דקות — שורש כף היד, הכתף וחימום עמידת ידיים",
        "prereq": "תנאי סף למסלול: 30 שניות עמידת ידיים יציבה עם החזה לקיר ו-10 שכיבות סמיכה פייק.",
        "cues": [
            "עמידת ידיים עם החזה לקיר מלמדת את קו הגוף הנכון; גב לקיר מעודד קשת בגב התחתון.",
            "מרפקים פנימה ולא לצדדים — מרפק שנפתח החוצה מעמיס את הכתף בזווית גזירה.",
            "בסיס משולש: הראש נוגע מעט לפני קו כפות הידיים, כך שהראש והידיים יוצרים משולש יציב.",
            "ישבן ובטן נעולים לאורך כל החזרה — הקשת בגב התחתון היא מה שגונב את הטווח.",
        ],
        "progressions": [
            _station("Wall-Assisted Handstand Hold", "עמידת ידיים לקיר (החזקה)", 30, 90,
                     "חזה לקיר, ידיים ברוחב כתפיים, והולכים עם הרגליים במעלה הקיר עד שהגוף אנכי ונעול.",
                     [("חזה לקיר", "פונים אל הקיר — לא עם הגב אליו."),
                      ("כתפיים פתוחות", "דוחפים את הכתפיים אל האוזניים לגובה מלא.")],
                     unit="sec"),
            _station("Pike Push-ups", "שכיבות סמיכה פייק", 10, 90,
                     "מנח V הפוך עם אגן גבוה; יורדים עד שקודקוד הראש כמעט נוגע ברצפה מעט לפני הידיים.",
                     [("אגן גבוה", "ככל שהאגן גבוה יותר, העומס קרוב יותר לאנכי."),
                      ("ראש קדימה", "הראש יורד לפני קו כפות הידיים — בסיס משולש.")]),
            _station("Wall Walks (Holds)", "טיפוס קיר לעמידת ידיים", 5, 90,
                     "מפלאנק עם הרגליים על הקיר הולכים עם הידיים לעבר הקיר עד מנח כמעט אנכי, ועוצרים 3-5 שניות.",
                     [("צעדים קטנים", "צעדי יד קטנים שומרים על שליטה."),
                      ("לעצור למעלה", "עוצרים בנקודה הגבוהה לפני הירידה.")]),
            _station("Elevated Pike Push-ups", "שכיבות סמיכה פייק מוגבהות", 8, 90,
                     "רגליים על ספסל או מדרגה כך שהגו כמעט אנכי, וירידה לאותו בסיס משולש.",
                     [("גו אנכי", "ככל שההגבהה גבוהה יותר, התרגיל קרוב יותר ל-HSPU."),
                      ("טווח מלא", "הראש נוגע ברצפה בכל חזרה.")]),
            _station("Negative Wall HSPU", "ירידה אקסצנטרית לקיר", 4, 120,
                     "מעמידת ידיים לקיר יורדים 4-5 שניות עד שהראש נוגע ברצפה, ויוצאים מהמנח עם הרגליים.",
                     [("ירידה 4-5 שניות", "ככל שהירידה איטית יותר, כך נבנה הכוח."),
                      ("מרפקים פנימה", "המרפקים לא נפתחים החוצה בדרך למטה.")]),
            _station("Partial Wall HSPU", "שכיבות סמיכה לקיר בטווח חלקי", 6, 120,
                     "מניחים כרית או ספרים מתחת לראש ודוחפים מטווח קצר, ומנמיכים את ההגבהה ככל שמתחזקים.",
                     [("להנמיך בהדרגה", "מורידים את ההגבהה בכל פעם שיוצאות 6 חזרות."),
                      ("דחיפה מהידיים", "הדחיפה מתחילה מהידיים, לא מתנופת רגליים.")]),
            _station("Wall-Assisted HSPU", "שכיבות סמיכה בעמידת ידיים לקיר", 5, 120,
                     "ירידה מלאה עד שהראש נוגע ברצפה ודחיפה חזרה לנעילת מרפקים, כשהרגליים רק נוגעות בקיר.",
                     [("נעילה למעלה", "כל חזרה מסתיימת במרפקים נעולים."),
                      ("קיר לאיזון", "הרגליים נוגעות בקיר קלות — לא נשענות עליו.")]),
            _station("Freestanding Handstand Hold", "עמידת ידיים חופשית (החזקה)", 20, 120,
                     "עמידת ידיים בלי קיר: מאזנים בלחיצת אצבעות ובשורש כף היד, גוף נעול בקו אחד.",
                     [("אצבעות מאזנות", "האיזון נעשה בלחיצת אצבעות, לא בתנועת גוף."),
                      ("מבט בין הידיים", "המבט על הרצפה בין כפות הידיים.")],
                     unit="sec"),
            _station("Straddle Freestanding HSPU", "שכיבות סמיכה חופשיות בפיסוק", 3, 150,
                     "עמידת ידיים חופשית עם רגליים פתוחות לצדדים לאיזון קל יותר, וירידה מלאה לבסיס המשולש.",
                     [("פיסוק מאזן", "רגליים פתוחות מורידות את מרכז הכובד."),
                      ("ירידה נשלטת", "הירידה האיטית היא שמחזיקה את האיזון.")]),
            _station("Full Freestanding HSPU", "שכיבות סמיכה בעמידת ידיים מלאה", 3, 180,
                     "עמידת ידיים חופשית עם רגליים צמודות: ירידה עד הראש ודחיפה לנעילה מלאה.",
                     [("קו גוף נעול", "ישבן ובטן נעולים לאורך כל החזרה."),
                      ("דחיפה שלמה", "מסיימים בכתפיים פתוחות ומרפקים נעולים.")]),
        ],
    },
    "human_flag": {
        "title": "דגל אנושי (Human Flag)",
        "difficulty": "רמת קושי: מתקדם",
        "muscles": "שרירים עיקריים: כתפיים, אלכסוני הבטן, רחב גבי, ליבה צדית",
        "warmup": "זמן חימום מומלץ: 10-12 דקות — כתף, שכמה וליבה צדית",
        "prereq": "תנאי סף למסלול: 30 שניות פלאנק צד לכל צד, תמיכה יציבה ביד אחת ואחיזה חזקה.",
        "cues": [
            "פעולה א-סימטרית: היד התחתונה דוחפת את העמוד במרפק נעול, והיד העליונה מושכת אליו — שני כוחות מנוגדים.",
            "היד התחתונה עושה את רוב העבודה; מי שנתקע בדרך כלל מנסה למשוך במקום לדחוף.",
            "כיווץ אלכסונים וישבן הוא שמרים את האגן — בלעדיו הרגליים נשארות למטה גם עם כתפיים חזקות.",
            "סולם שוודי או שתי ידיות בגבהים שונים נוחים בהרבה מעמוד עגול, במיוחד בשלבים הראשונים.",
        ],
        "progressions": [
            _station("One Arm Active Hang", "תלייה פעילה ביד אחת", 20, 90,
                     "תלייה ביד אחת עם שכמה פעילה — הכתף נמשכת מטה ולא נתלית רפויה על המפרק.",
                     [("שכמה פעילה", "הכתף רחוק מהאוזן לאורך כל ההחזקה."),
                      ("להחליף יד", "אותו מספר שניות לכל יד.")],
                     unit="sec"),
            _station("One Arm Inverted Support", "תמיכה הפוכה ביד אחת", 15, 90,
                     "אוחזים בעמוד ביד עליונה ותחתונה, מרימים את הרגליים לצד העמוד ומחזיקים גוף אנכי הפוך.",
                     [("מרפק תחתון נעול", "היד התחתונה נעולה ודוחפת."),
                      ("גוף צמוד לעמוד", "ככל שהגוף קרוב לעמוד, ההחזקה יציבה יותר.")],
                     unit="sec"),
            _station("Vertical Flag Hold", "דגל אנכי (רגליים למעלה)", 15, 90,
                     "מהתמיכה ההפוכה מורידים את הרגליים מעט מהאנכי ומחזיקים — זה המנח הקל ביותר בדגל.",
                     [("להתחיל גבוה", "ככל שהרגליים גבוהות יותר, כך קל יותר."),
                      ("דוחף ומושך", "תחתונה דוחפת, עליונה מושכת — כבר מהמנח הזה.")],
                     unit="sec"),
            _station("Vertical Flag Negatives", "ירידות מדגל אנכי", 5, 120,
                     "מהדגל האנכי מורידים את הרגליים לאט לכיוון האופק, עוצרים בנקודה הנמוכה שאפשר וחוזרים למעלה.",
                     [("ירידה 3-5 שניות", "הירידה היא התרגיל — לא הנפילה."),
                      ("לעצור בשליטה", "עוצרים לפני שהמנח נשבר, לא אחרי.")]),
            _station("Angled Tucked Flag Hold", "דגל מקופל בזווית", 12, 120,
                     "ברכיים אל החזה והגוף באלכסון כלפי מעלה; מקטינים את הזווית בהדרגה בין האימונים.",
                     [("ברכיים לחזה", "קיפול הדוק מקצר את המנוף."),
                      ("להוריד זווית", "כל אימון קצת יותר קרוב לאופק.")],
                     unit="sec"),
            _station("Tuck Human Flag Hold", "דגל אנושי מקופל (אופקי)", 10, 120,
                     "אותו קיפול, אבל הגו כבר מקביל לקרקע — האגן בגובה הכתפיים.",
                     [("אגן בגובה כתף", "הגוף אופקי, לא אלכסוני."),
                      ("אלכסונים נעולים", "צד הבטן העליון מכווץ חזק.")],
                     unit="sec"),
            _station("One-Legged Human Flag Hold", "דגל אנושי רגל אחת", 8, 150,
                     "ממנח מקופל אופקי מיישרים רגל אחת — בדרך כלל העליונה — והשנייה נשארת מקופלת.",
                     [("העליונה קודם", "מתחילים מיישור הרגל העליונה, היא הקלה יותר."),
                      ("להחליף צד", "מבצעים לשני הכיוונים.")],
                     unit="sec"),
            _station("Straddle Human Flag Hold", "דגל אנושי בפיסוק", 8, 150,
                     "שתי הרגליים ישרות ופתוחות לצדדים, גוף אופקי והאגן לא מסובב.",
                     [("פיסוק רחב", "פיסוק רחב מקצר את המנוף."),
                      ("אגן לא מסתובב", "הירכיים בקו אחד עם החזה.")],
                     unit="sec"),
            _station("Full Human Flag Hold", "דגל אנושי מלא", 5, 180,
                     "רגליים ישרות וצמודות, גוף אופקי מלא, ומרפק תחתון נעול לאורך כל ההחזקה.",
                     [("צמודות ונעולות", "רגליים צמודות עם ישבן נעול."),
                      ("לנשום", "נשימה שקטה — עצירת נשימה מקצרת את ההחזקה.")],
                     unit="sec"),
        ],
    },
}

# Stations whose Hebrew label changed here. A saved row carries the name it was saved
# under, so these keep counting towards the same station. Stations that were dropped
# from a path on purpose (Toes to Bar, the low and twisted flags) are not listed:
# their rows stay in the history but no longer count towards a path.
# (skill, the name it was saved under, the station it is today)
STATION_RENAMES = [
    ("muscle_up", "שכיבות סמיכה במקבילים", "Basic Dips", "Basic Dips"),
    ("muscle_up", "מתח מתפרץ / מחיאת כף", "Explosive Pull-ups", "Explosive Pull-ups"),
    ("front_lever", "סמיכה קדמית מקופלת (החזקה)", "Tuck Front Lever Hold", "Tuck Front Lever Hold"),
    ("front_lever", "סמיכה קדמית - רגל אחת מיושרת", "One-Legged FL Hold", "One-Legged FL Hold"),
    ("planche", "הישענות פלאנץ' על הקרקע", "Planche Lean", "Planche Lean"),
    ("planche", "פלאנץ' מקופל (החזקה)", "Tuck Planche Hold", "Tuck Planche Hold"),
    ("planche", "פלאנץ' מתקדם רגל אחת שלוחה", "One-Legged Advanced Tuck", "One-Legged Advanced Tuck"),
    ("hspu", "עמידת ידיים נתמכת קיר (החזקה)", "Wall-Assisted Handstand Hold", "Wall-Assisted Handstand Hold"),
    ("hspu", "שכיבות סמיכה בעמידת ידיים (קיר)", "Wall-Assisted HSPU", "Wall-Assisted HSPU"),
    ("human_flag", "דגל עליון אנכי (עזרה)", "High Flag Hold (Wall Walk)", "Vertical Flag Hold"),
]

# ====================== QUEST PATHS ======================
# Every SKILL_PROGRESSIONS entry is a path and its progressions are the stations.
# A station is conquered by completing STATION_SESSIONS_TO_CONQUER workouts with it
# in its rep range — counted from history, never marked by hand.

STATION_SESSIONS_TO_CONQUER = 5
STATION_REP_FLOOR = 0.8     # a session counts once its average set reaches 80% of the target
PLAN_FOCUS_SETS = 4         # sets of the station being conquered
PLAN_SUPPORT_SETS = 3       # sets of each earlier station, trained as volume
PLAN_SUPPORT_STATIONS = 2
PLAN_SECONDS_PER_SET = 40   # work time on top of the station's rest
PLAN_DURATION_SAMPLE = 5    # recent path sessions the time estimate is taken from
ETA_MIN_SESSIONS = 3        # below this the pace is a guess, so no estimate is shown

# Emoji are the icon language of paths/stations; ranks and achievements keep their fa-* icons.
PATHS = {
    "muscle_up": {"name": "עליית כוח", "icon": "🧗", "tint": "rgba(79,70,229,.36)", "unlock_level": 1, "workout_type": "Pull"},
    "hspu": {"name": "עמידת ידיים", "icon": "🤸", "tint": "rgba(124,58,237,.35)", "unlock_level": 1, "workout_type": "Push"},
    "front_lever": {"name": "סמיכה קדמית", "icon": "🦅", "tint": "rgba(13,148,136,.32)", "unlock_level": 1, "workout_type": "Pull"},
    "human_flag": {"name": "דגל אנושי", "icon": "🚩", "tint": "rgba(2,132,199,.32)", "unlock_level": 5, "workout_type": "Core"},
    "planche": {"name": "פלאנץ'", "icon": "✈️", "tint": "rgba(217,119,6,.32)", "unlock_level": 10, "workout_type": "Push"},
}

# Hebrew label per stored workouts.workout_type value
WORKOUT_TYPE_LABELS = {
    "Calisthenics": "קליסטניקס",
    "Push": "דחיפה",
    "Pull": "משיכה",
    "Core": "ליבה",
    "Legs": "רגליים",
    "Full Body": "גוף מלא",
}


def station_exercise_name(step: Dict[str, Any]) -> str:
    """The exercise name a station is saved under (the format the page has always sent)."""
    return f"{step['hebrew']} ({step['name']})"


# A saved row carries the exercise name, so the name — not the stored index — is what
# survives a change to the order of a path. Both maps are built from it.
STATION_BY_NAME: Dict[str, Tuple[str, int]] = {}          # name -> (skill, index)
STATION_INDEX: Dict[Tuple[str, str], int] = {}            # (skill, name) -> index
for _skill_key, _skill in SKILL_PROGRESSIONS.items():
    for _idx, _step in enumerate(_skill["progressions"]):
        STATION_BY_NAME.setdefault(station_exercise_name(_step), (_skill_key, _idx))
        STATION_INDEX[(_skill_key, station_exercise_name(_step))] = _idx

RENAMED_ENGLISH: Dict[Tuple[str, str], str] = {}   # (skill, old English name) -> today's name
for _skill_key, _old_hebrew, _old_english, _english in STATION_RENAMES:
    _steps = SKILL_PROGRESSIONS[_skill_key]["progressions"]
    _idx = next(i for i, s in enumerate(_steps) if s["name"] == _english)
    _old_name = f"{_old_hebrew} ({_old_english})"
    STATION_BY_NAME.setdefault(_old_name, (_skill_key, _idx))
    STATION_INDEX.setdefault((_skill_key, _old_name), _idx)
    RENAMED_ENGLISH[(_skill_key, _old_english)] = _english

# Hebrew title + coach-tip category for the free-workout exercise list
EXERCISE_CATALOG = {
    ex["name"]: {"title": ex["hebrew"], "category": category.split(" ")[0].lower()}
    for category, exercises in DEFAULT_EXERCISES.items()
    for ex in exercises
}

# ====================== EXERCISE HOLOGRAM ======================
# One shared glTF-binary model with an animation clip per exercise, named by holo_key().
# An exercise without a clip keeps the plain arena — the hologram only appears when its
# clip exists. Each clip is one rep, authored as lowering → pause → pushing, so the
# arena can play it at the exercise's tempo.

HOLO_MODEL_PATH = FRONTEND_DIR / "static" / "holo" / "exercises.glb"
HOLO_MODEL_URL = "/static/holo/exercises.glb"
mimetypes.add_type("model/gltf-binary", ".glb")  # StaticFiles would serve it as text/plain

TEMPO_DEFAULT = (3, 1, 1)   # seconds: lowering, pause, pushing
TEMPO_BY_EXERCISE = {
    "Explosive Pull-ups": (2, 0, 1),
    "Assisted Muscle-Up (Band)": (2, 0, 1),
    "Full Muscle-Up": (2, 0, 1),
    "Muscle-ups": (2, 0, 1),
    "Negative Muscle-Up": (5, 1, 1),
    "Negative Wall HSPU": (5, 1, 1),
    "Low Bar Transitions": (2, 0, 1),
    "Vertical Flag Negatives": (4, 1, 1),
    "Active Scapula Hangs": (2, 1, 1),
    "Scapula Shrugs": (2, 1, 1),
    "Toes to Bar": (2, 1, 1),
    "Calf Raises": (2, 1, 1),
}
# Static positions among the free-workout exercises: the clip is the hold itself, so
# there is no rep tempo. A path station says so itself, through its "sec" unit.
HOLD_EXERCISES = {
    "Planche Lean", "Tucked L-Sit", "Frog Stand", "One-Legged Advanced Tuck", "Advanced Tuck Planche",
    "One Arm Active Hang", "One Arm Inverted Support", "Wall Walks (Holds)", "L-Sit", "Plank",
    "False Grip Hang",
}

# Two form cues per free-workout exercise: a short pin for the hologram + the full
# sentence. Path stations carry their own two cues inside SKILL_PROGRESSIONS.
FORM_CUES = {
    "Push-ups": (("גב ישר", "קו ישר מהעורף לעקבים — בלי לשקוע באגן."),
                 ("מרפקים 45°", "מרפקים ב-45° לגוף, לא פתוחים לצדדים.")),
    "Dips": (("כתפיים למטה", "כתפיים רחוק מהאוזניים לאורך כל התנועה."),
             ("עומק 90°", "יורדים עד מרפק ב-90°, לא עמוק יותר.")),
    "Pike Push-ups": (("אגן גבוה", "אגן גבוה מעל הכתפיים, הגוף ב-V הפוכה."),
                      ("ראש קדימה", "הראש יורד מעט לפני כפות הידיים — בסיס משולש.")),
    "Handstand Push-ups": (("מרפקים צמודים", "מרפקים פנימה, לא פתוחים לצדדים."),
                           ("גוף נעול", "בטן וישבן נעולים — בלי קשת בגב.")),
    "Diamond Push-ups": (("ידיים מתחת לחזה", "אגודלים ואצבעות מורות נוגעים, מתחת לעצם החזה."),
                         ("מרפקים צמודים", "המרפקים נשארים קרובים לגוף בירידה.")),
    "Pull-ups": (("שכמות קודם", "מתחילים מהשכמות — למטה ואחורה, ורק אז הידיים."),
                 ("סנטר מעל המוט", "סנטר מעל המוט, בלי למתוח את הצוואר.")),
    "Muscle-ups": (("משיכה גבוהה", "משיכה מתפרצת עד גובה בית החזה."),
                   ("מעבר מהיר", "פרקי הידיים עוברים מעל המוט לפני שהמרפקים נפתחים.")),
    "Chin-ups": (("טווח מלא", "תלייה מלאה בתחתית, סנטר מעל המוט למעלה."),
                 ("בלי תנופה", "רגליים שקטות — בלי תנופה מהאגן.")),
    "Australian Pull-ups / Rows": (("גוף ישר", "גוף ישר כמו קרש מהכתפיים לעקבים."),
                                   ("חזה למוט", "מושכים את החזה אל המוט, מרפקים ליד הגוף.")),
    "Scapula Shrugs": (("ידיים ישרות", "מרפקים ישרים — רק השכמות זזות."),
                       ("למטה ואחורה", "מורידים את הכתפיים הרחק מהאוזניים.")),
    "L-Sit": (("ברכיים נעולות", "רגליים ישרות ומתוחות עד קצות האצבעות."),
              ("דחיפה למטה", "דוחפים את הרצפה ומרימים את הכתפיים.")),
    "Hanging Leg Raises": (("בלי נדנוד", "מתחילים מתלייה שקטה, בלי תנופה."),
                           ("אגן מתגלגל", "האגן מתגלגל למעלה בסוף התנועה.")),
    "Plank": (("קו ישר", "קו ישר מהעורף לעקבים."),
              ("צלעות למטה", "צלעות למטה ובטן אסופה — הגב התחתון לא שוקע.")),
    "Ab Wheel Rollouts": (("אגן פנימה", "גב עליון מעוגל קלות, אגן מגולגל פנימה."),
                          ("טווח בשליטה", "מתגלגלים רק עד שהגב התחתון מתחיל להתקשת.")),
    "Toes to Bar": (("שכמות פעילות", "שכמות מכווצות — לא תלייה רפויה."),
                    ("רגליים ישרות", "רגליים ישרות ככל האפשר עד המוט.")),
    "Pistol Squats": (("עקב על הרצפה", "העקב נשאר צמוד לרצפה לכל אורך הירידה."),
                      ("ברך מעל האצבעות", "הברך בכיוון האצבעות, לא קורסת פנימה.")),
    "Bulgarian Split Squats": (("גו זקוף", "גו זקוף, המשקל על הרגל הקדמית."),
                               ("ברך יציבה", "הברך הקדמית בקו האצבעות.")),
    "Shrimp Squats": (("ברך אחורית", "הברך האחורית נוגעת ברצפה בשליטה."),
                      ("גו קדימה", "הטיית גו קדימה שומרת על האיזון.")),
    "Airborne Squats": (("ברך אחורית", "הברך האחורית יורדת לרצפה בשליטה."),
                        ("זרועות קדימה", "זרועות קדימה לאיזון, גו זקוף ככל האפשר.")),
    "Calf Raises": (("טווח מלא", "מלמטה עמוק ועד קצות האצבעות."),
                    ("עצירה למעלה", "שנייה של עצירה בנקודה הגבוהה.")),
    "Bodyweight Squats": (("עקבים על הרצפה", "משקל על כל כף הרגל, העקבים לא מתרוממים."),
                          ("חזה פתוח", "חזה פתוח וגב ניטרלי בירידה.")),
}


def holo_key(english_name: str) -> str:
    """Animation clip name for an exercise: 'Negative Muscle-Up' -> 'negative_muscle_up'."""
    return re.sub(r"[^a-z0-9]+", "_", english_name.lower()).strip("_")


def exercise_tempo(english_name: str, unit: str = "reps") -> Optional[List[int]]:
    """Rep tempo in seconds (lowering, pause, pushing); None for static holds."""
    if unit == "sec" or "Hold" in english_name or english_name in HOLD_EXERCISES:
        return None
    return list(TEMPO_BY_EXERCISE.get(english_name, TEMPO_DEFAULT))


def unit_label(unit: str) -> str:
    """What a station's target counts: seconds for a hold, repetitions otherwise."""
    return "שניות" if unit == "sec" else "חזרות"


_holo_clip_cache: Dict[str, Any] = {"stamp": None, "clips": frozenset(), "front": frozenset()}


def holo_clips() -> frozenset:
    """Animation names inside the hologram model (read from the GLB's JSON chunk, cached by mtime)."""
    try:
        stat = HOLO_MODEL_PATH.stat()
    except OSError:
        return frozenset()
    stamp = (stat.st_mtime_ns, stat.st_size)
    if _holo_clip_cache["stamp"] != stamp:
        clips, front = frozenset(), frozenset()
        try:
            with open(HOLO_MODEL_PATH, "rb") as f:
                magic, _version, _length = struct.unpack("<4sII", f.read(12))
                chunk_length, chunk_type = struct.unpack("<I4s", f.read(8))
                if magic == b"glTF" and chunk_type == b"JSON":
                    gltf = json.loads(f.read(chunk_length))
                    clips = frozenset(a["name"] for a in gltf.get("animations", []) if a.get("name"))
                    front = frozenset(gltf.get("extras", {}).get("front_view_clips", ()))
        except (OSError, ValueError, struct.error):
            logger.warning("Unreadable hologram model at %s", HOLO_MODEL_PATH)
        _holo_clip_cache.update(stamp=stamp, clips=clips, front=front)
    return _holo_clip_cache["clips"]


def holo_front_clips() -> frozenset:
    """Clips the model asks to open on the front camera — a flag is edge-on from the side."""
    holo_clips()
    return _holo_clip_cache["front"]


def exercise_form_data() -> Dict[str, Dict[str, Any]]:
    """Per saved exercise name: hologram clip key, unit, tempo, how it is done and its cues."""
    data: Dict[str, Dict[str, Any]] = {}
    for name in EXERCISE_CATALOG:
        data[name] = {
            "holo_key": holo_key(name),
            "unit": "sec" if exercise_tempo(name) is None else "reps",
            "unit_label": unit_label("sec" if exercise_tempo(name) is None else "reps"),
            "tempo": exercise_tempo(name),
            "how": "",
            "cues": [{"pin": pin, "text": text} for pin, text in FORM_CUES.get(name, ())],
        }
    for skill in SKILL_PROGRESSIONS.values():
        for step in skill["progressions"]:
            entry = {
                "holo_key": holo_key(step["name"]),
                "unit": step["unit"],
                "unit_label": unit_label(step["unit"]),
                "tempo": exercise_tempo(step["name"], step["unit"]),
                "how": step["how"],
                "cues": [dict(cue) for cue in step["cues"]],
            }
            data[station_exercise_name(step)] = entry
    for skill_key, old_hebrew, old_english, english in STATION_RENAMES:
        step = next(s for s in SKILL_PROGRESSIONS[skill_key]["progressions"] if s["name"] == english)
        data.setdefault(f"{old_hebrew} ({old_english})", data[station_exercise_name(step)])
    return data

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


def _total_xp_for_level(level: int) -> int:
    """Total XP at which the given level starts."""
    return sum(_xp_needed_for_level(lvl) for lvl in range(1, level))


def _rank_ladder(level: int, total_xp: int) -> List[Dict[str, Any]]:
    """Every rank with its state for this player: achieved / current / next / locked."""
    current_idx = max(i for i, (min_level, _, _) in enumerate(RANKS) if level >= min_level)
    ladder = []
    for i, (min_level, rank_title, rank_icon) in enumerate(RANKS):
        if i < current_idx:
            state = "achieved"
        elif i == current_idx:
            state = "current"
        elif i == current_idx + 1:
            state = "next"
        else:
            state = "locked"
        ladder.append({
            "title": rank_title,
            "icon": rank_icon,
            "level": min_level,
            "state": state,
            "xp_needed": max(0, _total_xp_for_level(min_level) - total_xp),
        })
    return ladder


def _parse_day(value: Any) -> Optional[date_cls]:
    try:
        return date_cls.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _workout_days(dates: Iterable[str]) -> Set[date_cls]:
    return {d for d in (_parse_day(v) for v in dates) if d}


def _compute_streak(dates: List[str]) -> int:
    """Longest run of consecutive workout days ending at the most recent workout."""
    day_set = _workout_days(dates)
    if not day_set:
        return 0
    streak = 1
    day = max(day_set)
    while day - timedelta(days=1) in day_set:
        streak += 1
        day -= timedelta(days=1)
    return streak


def _current_streak(day_set: Set[date_cls], today: date_cls) -> int:
    """Run of workout days that is still alive (trained today or yesterday)."""
    day = today if today in day_set else today - timedelta(days=1)
    streak = 0
    while day in day_set:
        streak += 1
        day -= timedelta(days=1)
    return streak


def _best_streak(day_set: Set[date_cls]) -> int:
    best = 0
    for day in day_set:
        if day - timedelta(days=1) in day_set:
            continue  # not the start of a run
        length = 1
        while day + timedelta(days=length) in day_set:
            length += 1
        best = max(best, length)
    return best


def _ago_label(days: int) -> str:
    """'לפני 9 ימים' — how long ago something happened."""
    if days <= 0:
        return "היום"
    if days == 1:
        return "אתמול"
    if days == 2:
        return "לפני יומיים"
    if days < 14:
        return f"לפני {days} ימים"
    if days < 21:
        return "לפני שבועיים"
    if days < 60:
        return f"לפני {days // 7} שבועות"
    if days < 365:
        months = days // 30
        return "לפני חודשיים" if months == 2 else f"לפני {months} חודשים"
    return "לפני יותר משנה"


def _eta_label(weeks: float) -> str:
    """'בערך 4 חודשים' — a rough time-to-goal."""
    if weeks < 1.5:
        return "בערך שבוע"
    if weeks < 2.5:
        return "בערך שבועיים"
    if weeks < 7:
        return f"בערך {round(weeks)} שבועות"
    months = round(weeks / 4.345)
    if months >= 24:
        return "יותר משנתיים"
    return "בערך חודשיים" if months == 2 else f"בערך {months} חודשים"


def compute_gamification(history: List[Dict[str, Any]], today: Optional[date_cls] = None) -> Dict[str, Any]:
    """Aggregate workout history into the full player-profile game state."""
    today = today or date_cls.today()
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

    next_rank = _next_rank_for_level(level)
    if next_rank:
        next_rank["xp_needed"] = max(0, _total_xp_for_level(next_rank["level"]) - total_xp)
    ranks = _rank_ladder(level, total_xp)

    # Last 7 days, oldest first — the streak strip on the quest-select screen
    days = _workout_days(s["date"] for s in history)
    week = [
        {"date": d.isoformat(), "trained": d in days, "is_today": d == today}
        for d in (today - timedelta(days=offset) for offset in range(6, -1, -1))
    ]

    return {
        "total_xp": total_xp,
        "level": level,
        "xp_in_level": level_info["xp_in_level"],
        "xp_for_next": level_info["xp_for_next"],
        "progress_pct": level_info["progress_pct"],
        "rank": _rank_for_level(level),
        "next_rank": next_rank,
        "ranks": ranks,
        "rank_position": next(i for i, r in enumerate(ranks) if r["state"] == "current") + 1,
        "streak": streak,
        "current_streak": _current_streak(days, today),
        "best_streak": _best_streak(days),
        "week": week,
        "week_count": sum(1 for d in week if d["trained"]),
        "total_workouts": total_workouts,
        "total_sets": total_sets,
        "total_reps": total_reps,
        "total_minutes": total_minutes,
        "achievements": achievements,
        "unlocked_count": sum(1 for a in achievements if a["unlocked"]),
    }


def _rep_range(target: int) -> Tuple[int, int]:
    return max(1, math.ceil(target * STATION_REP_FLOOR)), target


def _station_for(skill_key: Optional[str], stage_index: Optional[int], exercise_name: str) -> Optional[Tuple[str, int]]:
    """The station an exercise row trained.

    The saved name is what identifies a station, so a row still lands on the right one
    after a path was re-ordered. Only a row whose name is not a station at all falls
    back to the index it was saved with.
    """
    skill = SKILL_PROGRESSIONS.get(skill_key or "")
    if skill:
        idx = STATION_INDEX.get((skill_key, exercise_name))
        if idx is not None:
            return (skill_key, idx)
    named = STATION_BY_NAME.get(exercise_name)
    if named:
        return named
    if skill and stage_index is not None and 0 <= stage_index < len(skill["progressions"]):
        return (skill_key, stage_index)
    return None


def _exercise_title(exercise_name: str, station: Optional[Tuple[str, int]]) -> str:
    """Hebrew display name for a saved exercise."""
    if station:
        return SKILL_PROGRESSIONS[station[0]]["progressions"][station[1]]["hebrew"]
    if exercise_name in EXERCISE_CATALOG:
        return EXERCISE_CATALOG[exercise_name]["title"]
    return exercise_name


def _exercise_unit(exercise_name: str, station: Optional[Tuple[str, int]]) -> str:
    """What the saved number counts: 'sec' for a static hold, 'reps' otherwise."""
    if station:
        return SKILL_PROGRESSIONS[station[0]]["progressions"][station[1]]["unit"]
    return "sec" if exercise_tempo(exercise_name) is None else "reps"


def _best_set(exercise: Dict[str, Any]) -> int:
    """Best single set of a saved exercise; rows from before max_reps fall back to the average set."""
    if exercise.get("max_reps") is not None:
        return exercise["max_reps"]
    return exercise["reps"] // exercise["sets"] if exercise["sets"] else 0


def compute_records(history: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Per exercise name: best single set (and when it was first reached) and the latest session's best set."""
    records: Dict[str, Dict[str, Any]] = {}
    for session in history:  # newest first
        for ex in session["exercises"]:
            best = _best_set(ex)
            if best <= 0:
                continue
            record = records.get(ex["name"])
            if record is None:
                records[ex["name"]] = {"best": best, "best_date": session["date"], "last": best}
            elif best >= record["best"]:
                # Ties move the date back, so it points at when the record was first set
                record["best"], record["best_date"] = best, session["date"]
    return records


def compute_paths(
    history: List[Dict[str, Any]],
    level: int,
    legacy_conquered: Optional[Dict[str, List[int]]] = None,
    today: Optional[date_cls] = None,
) -> List[Dict[str, Any]]:
    """Quest paths with per-station progress counted from history, plus today's plan for each path."""
    today = today or date_cls.today()
    legacy_conquered = legacy_conquered or {}

    tally: Dict[Tuple[str, int], Dict[str, int]] = {}
    path_sessions: Dict[str, List[Dict[str, Any]]] = {}
    for session in history:  # newest first
        seen_stations = set()
        for ex in session["exercises"]:
            station = ex.get("station")
            if not station or station in seen_stations:
                continue
            seen_stations.add(station)
            skill_key, idx = station
            target = SKILL_PROGRESSIONS[skill_key]["progressions"][idx]["reps"]
            counts = tally.setdefault(station, {"sessions": 0, "in_range": 0})
            counts["sessions"] += 1
            if ex["sets"] > 0 and ex["reps"] / ex["sets"] >= _rep_range(target)[0]:
                counts["in_range"] += 1
            sessions_on_path = path_sessions.setdefault(skill_key, [])
            if not sessions_on_path or sessions_on_path[-1] is not session:
                sessions_on_path.append(session)

    paths = []
    for skill_key, skill in SKILL_PROGRESSIONS.items():
        meta = PATHS[skill_key]
        sessions = path_sessions.get(skill_key, [])
        legacy_done = set(legacy_conquered.get(skill_key, []))

        stations = []
        for idx, step in enumerate(skill["progressions"]):
            counts = tally.get((skill_key, idx), {"sessions": 0, "in_range": 0})
            low, high = _rep_range(step["reps"])
            stations.append({
                "index": idx,
                "number": idx + 1,
                "name": step["name"],
                "hebrew": step["hebrew"],
                "exercise_name": station_exercise_name(step),
                "reps": step["reps"],
                "rest": step["rest"],
                "unit": step["unit"],
                "unit_label": unit_label(step["unit"]),
                "how": step["how"],
                "cues": step["cues"],
                "rep_label": f"{low}–{high}" if low < high else str(high),
                "sessions": counts["sessions"],
                "in_range": min(counts["in_range"], STATION_SESSIONS_TO_CONQUER),
                "remaining": max(0, STATION_SESSIONS_TO_CONQUER - counts["in_range"]),
                "conquered": counts["in_range"] >= STATION_SESSIONS_TO_CONQUER or idx in legacy_done,
            })

        current = next((st for st in stations if not st["conquered"]), None)
        for st in stations:
            if st["conquered"]:
                st["state"] = "conquered"
            elif st is current:
                st["state"] = "current"
            elif current is not None and st["index"] == current["index"] + 1:
                st["state"] = "next"
            else:
                st["state"] = "locked"

        # Today's plan: the station being conquered, then earlier stations as volume.
        # A finished path keeps training its goal.
        focus = current or stations[-1]
        planned = [(focus, PLAN_FOCUS_SETS)] + [
            (stations[focus["index"] - back], PLAN_SUPPORT_SETS)
            for back in range(1, PLAN_SUPPORT_STATIONS + 1)
            if focus["index"] - back >= 0
        ]
        plan_sets = sum(sets for _, sets in planned)
        plan_reps = sum(sets * st["reps"] for st, sets in planned)
        recent_durations = [s["total_duration"] for s in sessions[:PLAN_DURATION_SAMPLE] if s.get("total_duration")]
        if recent_durations:
            plan_minutes = round(median(recent_durations))
        else:
            # A hold's work time is the hold itself; a rep set gets the flat estimate.
            plan_seconds = sum(
                sets * ((st["reps"] if st["unit"] == "sec" else PLAN_SECONDS_PER_SET) + st["rest"])
                for st, sets in planned
            )
            plan_minutes = max(1, round(plan_seconds / 60))
        plan = {
            "exercises": [
                {
                    "name": st["exercise_name"],
                    "title": st["hebrew"],
                    "skill_key": skill_key,
                    "stage_index": st["index"],
                    "sets": sets,
                    "reps": st["reps"],
                    "rest": st["rest"],
                    "unit": st["unit"],
                    "unit_label": st["unit_label"],
                }
                for st, sets in planned
            ],
            "sets": plan_sets,
            "minutes": plan_minutes,
            "xp": _session_xp(plan_sets, plan_reps, plan_minutes),
        }

        # Time to the goal at the user's own pace on this path
        eta = None
        if current is not None and len(sessions) >= ETA_MIN_SESSIONS:
            taken = [st["sessions"] for st in stations if st["conquered"] and st["sessions"]]
            per_station = max(STATION_SESSIONS_TO_CONQUER, median(taken) if taken else 0)
            remaining_sessions = max(0, (len(stations) - current["index"]) * per_station - current["in_range"])
            first_day = _parse_day(sessions[-1]["date"]) or today
            weeks_active = max(1.0, (today - first_day).days / 7)
            eta = _eta_label(remaining_sessions / (len(sessions) / weeks_active))

        last_day = _parse_day(sessions[0]["date"]) if sessions else None
        paths.append({
            "key": skill_key,
            **meta,
            "title": skill["title"],
            "difficulty": skill["difficulty"],
            "muscles": skill["muscles"],
            "warmup": skill["warmup"],
            "prereq": skill["prereq"],
            "cues": skill["cues"],
            "category": meta["workout_type"].lower(),
            "unlocked": level >= meta["unlock_level"] or bool(sessions) or bool(legacy_done),
            "stations": stations,
            "total": len(stations),
            "current": current,
            "complete": current is None,
            "position": current["number"] if current else len(stations),
            "conquered_count": sum(1 for st in stations if st["conquered"]),
            "goal": stations[-1],
            "stations_to_goal": len(stations) - current["number"] if current else 0,
            "eta": eta,
            "plan": plan,
            "sessions": len(sessions),
            "last_date": last_day.isoformat() if last_day else None,
            "last_ago": _ago_label((today - last_day).days) if last_day else None,
        })
    return paths


def _legacy_progress_key(user_id: int) -> str:
    return f"workouts_legacy_conquered:{user_id}"


# The station order the browser-only "כבשתי!" flags were numbered against. Imported
# flags are stored — and stay stored — in these indexes, and are translated to today's
# order on the way out, so re-ordering a path never moves someone's old flags.
LEGACY_STATION_ORDER = {
    "muscle_up": ["Basic Pull-ups", "Basic Dips", "Toes to Bar", "Straight Bar Dips",
                  "Explosive Pull-ups", "Negative Muscle-Up", "Assisted Muscle-Up (Band)",
                  "Full Muscle-Up"],
    "front_lever": ["Active Scapula Hangs", "Tuck Front Lever Hold", "Advanced Tuck FL Hold",
                    "Hanging Leg Raises", "Reversed Deadlift (FL Pulls)", "Tuck FL Rows",
                    "Straddle Front Lever Hold", "One-Legged FL Hold", "Full Front Lever Hold"],
    "planche": ["Planche Lean", "Tucked L-Sit", "Frog Stand", "Tuck Planche Hold",
                "One-Legged Advanced Tuck", "Advanced Tuck Planche", "Straddle Planche Hold",
                "Full Planche Hold"],
    "hspu": ["Wall-Assisted Handstand Hold", "Wall Walks (Holds)", "Pike Push-ups",
             "Elevated Pike Push-ups", "Negative Wall HSPU", "Wall-Assisted HSPU",
             "Straddle Freestanding HSPU", "Full Freestanding HSPU"],
    "human_flag": ["One Arm Active Hang", "One Arm Inverted Support", "Low Flag Hold",
                   "High Flag Hold (Wall Walk)", "Angled Tucked Flag Hold", "Twisted Flag Hold",
                   "Tuck Human Flag Hold", "Straddle Human Flag Hold", "Full Human Flag Hold"],
}


def _clean_progress(data: Any) -> Dict[str, List[int]]:
    """Keep only real skill keys and in-range legacy stage indexes."""
    clean: Dict[str, List[int]] = {}
    if not isinstance(data, dict):
        return clean
    for skill_key, indexes in data.items():
        order = LEGACY_STATION_ORDER.get(skill_key)
        if not order or not isinstance(indexes, list):
            continue
        valid = sorted({
            i for i in indexes
            if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(order)
        })
        if valid:
            clean[skill_key] = valid
    return clean


def _legacy_to_current(progress: Dict[str, List[int]]) -> Dict[str, List[int]]:
    """Translate legacy stage indexes into today's ones; a dropped station is dropped."""
    current: Dict[str, List[int]] = {}
    for skill_key, indexes in progress.items():
        steps = SKILL_PROGRESSIONS[skill_key]["progressions"]
        by_name = {step["name"]: idx for idx, step in enumerate(steps)}
        names = [
            RENAMED_ENGLISH.get((skill_key, name), name)
            for name in (LEGACY_STATION_ORDER[skill_key][i] for i in indexes)
        ]
        mapped = sorted({by_name[name] for name in names if name in by_name})
        if mapped:
            current[skill_key] = mapped
    return current


def _stored_legacy_progress(db_conn: sqlite3.Connection, user_id: int) -> Dict[str, List[int]]:
    """The imported flags exactly as stored — in legacy station indexes."""
    row = db_conn.execute(
        "SELECT value FROM system_settings WHERE key = ?", (_legacy_progress_key(user_id),)
    ).fetchone()
    if not row:
        return {}
    try:
        return _clean_progress(json.loads(row["value"]))
    except (TypeError, ValueError):
        return {}


def _load_legacy_progress(db_conn: sqlite3.Connection, user_id: int) -> Dict[str, List[int]]:
    """Stations a browser had marked conquered by hand, in today's station order."""
    return _legacy_to_current(_stored_legacy_progress(db_conn, user_id))


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
        SELECT date, workout_type, total_duration, exercise_name, total_sets, total_reps,
               skill_key, stage_index, max_reps
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
        station = _station_for(r["skill_key"], r["stage_index"], r["exercise_name"])
        workout_sessions[session_key]["exercises"].append({
            "name": r["exercise_name"],
            "title": _exercise_title(r["exercise_name"], station),
            "sets": r["total_sets"],
            "reps": r["total_reps"],
            "max_reps": r["max_reps"],
            "unit_label": unit_label(_exercise_unit(r["exercise_name"], station)),
            "station": station,
        })
    return list(workout_sessions.values())


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
    game = compute_gamification(history, today)
    paths = compute_paths(history, game["level"], _load_legacy_progress(db_conn, user_id), today)
    records = compute_records(history)
    unlocked = [p for p in paths if p["unlocked"]]
    trained = [p for p in unlocked if p["last_date"]]
    default_path = max(trained, key=lambda p: p["last_date"])["key"] if trained else unlocked[0]["key"]
    first_workout = game["total_workouts"] == 0

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
    }
    clips = holo_clips()
    if clips:
        version = _holo_clip_cache["stamp"][0]  # mtime, so a new model busts the cache
        client_data["holo"] = {"model": f"{HOLO_MODEL_URL}?v={version}", "clips": sorted(clips),
                               "front": sorted(holo_front_clips() & clips)}

    return templates.TemplateResponse(
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
            "first_workout": first_workout,
            "first_workout_xp": min(p["plan"]["xp"] for p in unlocked),
            "sessions_to_conquer": STATION_SESSIONS_TO_CONQUER,
            "game": game,
            "client_data": client_data,
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
        session_best: Dict[str, Tuple[int, str]] = {}
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

        new_stations = []
        for p in compute_paths(history_after, game_after["level"], legacy, today):
            for st in p["stations"]:
                if st["conquered"] and (p["key"], st["index"]) not in conquered_before:
                    new_stations.append({
                        "path": p["name"],
                        "icon": p["icon"],
                        "station": st["hebrew"],
                        "next": p["current"]["hebrew"] if p["current"] else None,
                    })

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
                "new_records": new_records,
            },
        }
    except Exception as e:
        logger.exception("Failed to save workout session")
        return JSONResponse({"status": "error", "message": f"Database error: {str(e)}"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ====================== ADMIN (back office) ======================
# /workouts/admin edits the rows everything else is derived from. A session is the
# group of rows sharing (user_id, date, workout_type, total_duration) — the same
# grouping _fetch_history uses — so any row id identifies the session it belongs to.
# The JSON writes behind the screen live in api/workouts.py.

ADMIN_ROW_COLUMNS = (
    "id, user_id, date, workout_type, total_duration, exercise_name, "
    "total_sets, total_reps, skill_key, stage_index, max_reps"
)


def _session_key(row: sqlite3.Row) -> Tuple[Any, ...]:
    return (row["user_id"], row["date"], row["workout_type"], row["total_duration"])


def _admin_exercise(row: sqlite3.Row) -> Dict[str, Any]:
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


def _group_admin_rows(rows: Iterable[sqlite3.Row]) -> List[Dict[str, Any]]:
    """Exercise rows → sessions, in the order the rows arrive."""
    sessions: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
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


def admin_sessions(db_conn: sqlite3.Connection, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Saved sessions, newest first, in the shape the admin screen lists and edits."""
    where, params = "", []
    if user_id is not None:
        where, params = "WHERE user_id = ?", [user_id]
    rows = db_conn.execute(
        f"SELECT {ADMIN_ROW_COLUMNS} FROM workouts {where} ORDER BY date DESC, id DESC", params
    ).fetchall()
    return _group_admin_rows(rows)


def admin_session_rows(db_conn: sqlite3.Connection, row_id: int) -> List[sqlite3.Row]:
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


def admin_session(db_conn: sqlite3.Connection, row_id: int) -> Optional[Dict[str, Any]]:
    """One session by any of its row ids, or None when it no longer exists."""
    rows = admin_session_rows(db_conn, row_id)
    return _group_admin_rows(rows)[0] if rows else None


def admin_exercise_options() -> List[Dict[str, Any]]:
    """Picker groups for the editor: every quest station first, then the free-workout catalog."""
    groups: List[Dict[str, Any]] = []
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


def admin_legacy_stations(db_conn: sqlite3.Connection, user_id: int) -> List[Dict[str, Any]]:
    """Stations imported from the old browser-only "כבשתי!" flags, as rows the admin can clear."""
    return [
        {
            "skill_key": skill_key,
            "path": PATHS[skill_key]["name"],
            "icon": PATHS[skill_key]["icon"],
            "stage_index": idx,
            "station": SKILL_PROGRESSIONS[skill_key]["progressions"][idx]["hebrew"],
        }
        for skill_key, indexes in _load_legacy_progress(db_conn, user_id).items()
        for idx in indexes
    ]


@router.get("/workouts/admin", response_class=HTMLResponse)
async def workout_admin_page(
    request: Request,
    user: Optional[int] = None,
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> HTMLResponse:
    """Back office for the workouts module: every saved session, editable row by row."""
    viewer_id = _resolve_user_id(request, db_conn)
    if viewer_id is None:
        return HTMLResponse("Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

    people = household(db_conn)
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
