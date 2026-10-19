"""Everything the arena derives from saved workout rows: XP, levels, ranks, streaks, paths, plan, boss."""
import math
import sqlite3
from collections.abc import Iterable
from datetime import date as date_cls
from datetime import timedelta
from statistics import median
from typing import Any

from ..hebrew_dates import in_days_label
from .catalog import (
    ETA_MIN_SESSIONS,
    EXERCISE_CATALOG,
    PATHS,
    PLAN_DURATION_SAMPLE,
    PLAN_FOCUS_SETS,
    PLAN_SECONDS_PER_SET,
    PLAN_SUPPORT_SETS,
    PLAN_SUPPORT_STATIONS,
    SKILL_PROGRESSIONS,
    STATION_BY_NAME,
    STATION_INDEX,
    STATION_REP_FLOOR,
    STATION_SESSIONS_TO_CONQUER,
    TYPE_LABELS,
    WARMUP_MINUTES,
    WARMUPS,
    exercise_tempo,
    station_exercise_name,
    unit_label,
)

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


def _level_from_xp(total_xp: int) -> dict[str, int]:
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


def _rank_for_level(level: int) -> dict[str, str]:
    title, icon = RANKS[0][1], RANKS[0][2]
    for min_level, rank_title, rank_icon in RANKS:
        if level >= min_level:
            title, icon = rank_title, rank_icon
    return {"title": title, "icon": icon}


def _next_rank_for_level(level: int) -> dict[str, Any]:
    for min_level, rank_title, _ in RANKS:
        if level < min_level:
            return {"title": rank_title, "level": min_level}
    return {}


def _total_xp_for_level(level: int) -> int:
    """Total XP at which the given level starts."""
    return sum(_xp_needed_for_level(lvl) for lvl in range(1, level))


def _rank_ladder(level: int, total_xp: int) -> list[dict[str, Any]]:
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


def _parse_day(value: Any) -> date_cls | None:
    try:
        return date_cls.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _workout_days(dates: Iterable[str]) -> set[date_cls]:
    return {d for d in (_parse_day(v) for v in dates) if d}


def _compute_streak(dates: list[str]) -> int:
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


def _current_streak(day_set: set[date_cls], today: date_cls) -> int:
    """Run of workout days that is still alive (trained today or yesterday)."""
    day = today if today in day_set else today - timedelta(days=1)
    streak = 0
    while day in day_set:
        streak += 1
        day -= timedelta(days=1)
    return streak


STREAK_MILESTONES = (7, 14, 21, 30, 60, 100, 365)   # the next one is the streak card's goal


def _streak_details(current: int, best: int, day_set: set[date_cls], today: date_cls) -> dict[str, Any]:
    """What the streak card shows once a run is longer than the 7-day strip can tell.

    weeks/extra_days split the run for the Hebrew label ("שבועיים ו-3 ימים"); the next
    milestone drives a progress bar; ``at_risk`` means the run is alive only thanks to
    yesterday, so today's workout is what keeps it; ``grid`` is the last 4 weeks, oldest
    row first, for the long-streak variant of the card.
    """
    nxt = next((m for m in STREAK_MILESTONES if m > current), None)
    prev = max((m for m in STREAK_MILESTONES if m <= current), default=0)
    milestone = None
    if nxt:
        milestone = {
            "target": nxt,
            "remaining": nxt - current,
            "pct": round(100 * (current - prev) / (nxt - prev)) if current else 0,
        }
    grid = [
        [
            {"date": d.isoformat(), "trained": d in day_set, "is_today": d == today}
            for d in (today - timedelta(days=offset) for offset in range(week_end, week_end - 7, -1))
        ]
        for week_end in (27, 20, 13, 6)
    ]
    return {
        "streak_weeks": current // 7,
        "streak_extra_days": current % 7,
        "streak_milestone": milestone,
        "streak_at_risk": current > 0 and today not in day_set,
        "streak_is_best": current > 0 and current >= best,
        "streak_grid": grid,
        "streak_grid_count": sum(1 for row in grid for d in row if d["trained"]),
    }


def _best_streak(day_set: set[date_cls]) -> int:
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


def compute_gamification(
    history: list[dict[str, Any]],
    today: date_cls | None = None,
    spanish_in_pocket: int = 0,
) -> dict[str, Any]:
    """Aggregate workout history into the full player-profile game state.

    `spanish_in_pocket` is the derived "words in your pocket" count (services/spanish.py),
    passed in so the one Spanish achievement sits in the same list as the training ones.
    """
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
        ("spanish_50", "fa-language", "50 מילים בכיס", "50 מילים בספרדית ששרדו שבוע בלי לשכוח", spanish_in_pocket, 50),
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

    current_streak = _current_streak(days, today)
    best_streak = _best_streak(days)

    return {
        **_streak_details(current_streak, best_streak, days, today),
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
        "current_streak": current_streak,
        "best_streak": best_streak,
        "week": week,
        "week_count": sum(1 for d in week if d["trained"]),
        "total_workouts": total_workouts,
        "total_sets": total_sets,
        "total_reps": total_reps,
        "total_minutes": total_minutes,
        "achievements": achievements,
        "unlocked_count": sum(1 for a in achievements if a["unlocked"]),
    }


def _rep_range(target: int) -> tuple[int, int]:
    return max(1, math.ceil(target * STATION_REP_FLOOR)), target


def _station_for(skill_key: str | None, stage_index: int | None, exercise_name: str) -> tuple[str, int] | None:
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


def _exercise_title(exercise_name: str, station: tuple[str, int] | None) -> str:
    """Hebrew display name for a saved exercise."""
    if station:
        return SKILL_PROGRESSIONS[station[0]]["progressions"][station[1]]["hebrew"]
    if exercise_name in EXERCISE_CATALOG:
        return EXERCISE_CATALOG[exercise_name]["title"]
    return exercise_name


def _exercise_unit(exercise_name: str, station: tuple[str, int] | None) -> str:
    """What the saved number counts: 'sec' for a static hold, 'reps' otherwise."""
    if station:
        return SKILL_PROGRESSIONS[station[0]]["progressions"][station[1]]["unit"]
    return "sec" if exercise_tempo(exercise_name) is None else "reps"


def _best_set(exercise: dict[str, Any]) -> int:
    """Best single set of a saved exercise; rows from before max_reps fall back to the average set."""
    if exercise.get("max_reps") is not None:
        return exercise["max_reps"]
    return exercise["reps"] // exercise["sets"] if exercise["sets"] else 0


def compute_records(history: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per exercise name: best single set (and when it was first reached) and the latest session's best set."""
    records: dict[str, dict[str, Any]] = {}
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
    history: list[dict[str, Any]],
    level: int,
    legacy_conquered: dict[str, list[int]] | None = None,
    today: date_cls | None = None,
) -> list[dict[str, Any]]:
    """Quest paths with per-station progress counted from history, plus today's plan for each path."""
    today = today or date_cls.today()
    legacy_conquered = legacy_conquered or {}

    tally: dict[tuple[str, int], dict[str, int]] = {}
    path_sessions: dict[str, list[dict[str, Any]]] = {}
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
                "skipped": False,
            })
        # From the top down, so a run of prep stations is credited all the way back
        for step, st, after in reversed(list(zip(skill["progressions"], stations, stations[1:]))):
            if step["prep"] and not st["conquered"] and after["conquered"]:
                st["conquered"] = st["skipped"] = True

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
            if focus["index"] - back >= 0 and not stations[focus["index"] - back]["skipped"]
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
            "warmup": WARMUPS.get(skill_key, []),
            "warmup_minutes": WARMUP_MINUTES,
            "sessions": len(sessions),
            "last_date": last_day.isoformat() if last_day else None,
            "last_ago": _ago_label((today - last_day).days) if last_day else None,
        })
    return paths


RECOVERY_STREAK_DAYS = 3   # this many training days in a row earns a rest-day nudge


def plan_today(paths: list[dict[str, Any]], history: list[dict[str, Any]], today: date_cls) -> tuple[str, str | None]:
    """The path for today's mission card and a one-line recovery note (or None).

    Strength skills grow between sessions, not during them: after a pull day the mission
    moves to a push path (and vice versa), and a long run of daily sessions gets a
    rest-day nudge. A path already trained today stays put so the user can keep going.
    """
    unlocked = [p for p in paths if p["unlocked"]]
    trained = [p for p in unlocked if p["last_date"]]
    fallback = max(trained, key=lambda p: p["last_date"]) if trained else unlocked[0]
    days = _workout_days(s["date"] for s in history)
    if not days:
        return fallback["key"], None
    last = max(days)
    gap = (today - last).days
    if gap == 0 or gap >= 2:
        return fallback["key"], None

    # Trained yesterday: pick a path that loads a different muscle group.
    yesterday_types = {s["workout_type"] for s in history if _parse_day(s["date"]) == last}
    fresh = [p for p in unlocked if p["workout_type"] not in yesterday_types]
    if fresh:
        fresh_trained = [p for p in fresh if p["last_date"]]
        if fresh_trained:
            chosen = max(fresh_trained, key=lambda p: p["last_date"])
        else:
            # Never trained any of them: start with the easiest path (lowest unlock level)
            chosen = min(fresh, key=lambda p: (p["unlock_level"], list(PATHS).index(p["key"])))
    else:
        chosen = fallback

    run = _current_streak(days, today - timedelta(days=1)) if last == today - timedelta(days=1) else 0
    if run >= RECOVERY_STREAK_DAYS:
        note = (f"{run} ימים ברצף — הכוח נבנה בזמן המנוחה. יום חופש היום הוא חלק מהתוכנית, "
                "ואם מתאמנים: קצר וקל.")
    elif chosen is not fallback:
        was = " ו".join(TYPE_LABELS.get(t, t) for t in sorted(yesterday_types) if t in TYPE_LABELS) or "אימון"
        note = f"אתמול היה יום {was} — היום {TYPE_LABELS.get(chosen['workout_type'], chosen['workout_type'])}, השרירים של אתמול נחים."
    else:
        note = None
    return chosen["key"], note


BOSS_PACE_WINDOW_DAYS = 56   # cadence is measured over the last 8 weeks at most
BOSS_PACE_MIN_WINDOW_DAYS = 7  # ...and over the last week at least, so a fresh start reads as a pace
BOSS_BAR_WINDOW_DAYS = 28    # trainings done shown on the banner's bar
BOSS_MIN_PACE_DAYS = 3       # below this many training days the pace is assumed
BOSS_ASSUMED_PER_WEEK = 2.0


def _days_in_window(days: set[date_cls], today: date_cls, window: int) -> int:
    return sum(1 for d in days if 0 <= (today - d).days < window)


def _pace_window(days: set[date_cls], today: date_cls) -> int:
    """How many days the cadence is measured over: the last 8 weeks, or, for someone who
    started (or started over) more recently, the days since their first training — so five
    trainings in the first five days count as a daily pace, not as five spread over two months."""
    past = [d for d in days if d <= today]
    if not past:
        return BOSS_PACE_WINDOW_DAYS
    since_first = (today - min(past)).days + 1
    return max(BOSS_PACE_MIN_WINDOW_DAYS, min(BOSS_PACE_WINDOW_DAYS, since_first))


def wedding_boss(
    history: list[dict[str, Any]],
    paths: list[dict[str, Any]],
    wedding_date: date_cls,
    today: date_cls,
) -> dict[str, Any] | None:
    """The wedding as the game's final boss: trainings left at the user's own pace, and
    where each unlocked, unfinished path will stand on the wedding day. None once it passed."""
    days_left = (wedding_date - today).days
    if days_left < 0:
        return None

    days = _workout_days(s["date"] for s in history)
    window = _pace_window(days, today)
    pace_days = _days_in_window(days, today, window)
    assumed = pace_days < BOSS_MIN_PACE_DAYS
    per_week = BOSS_ASSUMED_PER_WEEK if assumed else round(pace_days / (window / 7), 1)
    trainings_left = max(0, round(per_week * days_left / 7))

    forecasts: dict[str, dict[str, Any]] = {}
    for path in paths:
        if not path["unlocked"] or path["complete"]:
            continue
        budget = trainings_left
        reached = None
        for st in path["stations"]:
            if st["conquered"]:
                continue
            if budget >= st["remaining"]:
                budget -= st["remaining"]
                continue
            reached = st
            break
        forecasts[path["key"]] = {
            "finishes": reached is None,
            "station_number": reached["number"] if reached else None,
            "station_hebrew": reached["hebrew"] if reached else None,
        }

    return {
        "days_left": days_left,
        "days_label": in_days_label(days_left),
        "per_week": per_week,
        "assumed": assumed,
        "pace_window_days": window,
        "trainings_left": trainings_left,
        "recent_28": _days_in_window(days, today, BOSS_BAR_WINDOW_DAYS),
        "paths": forecasts,
    }


def _fetch_history(db_conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
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


def _station_progress(exercises: list[Any], paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Whether each station trained in a just-saved session counted towards conquering it.

    The rule is the one compute_paths applies: the average set has to reach the station's
    rep floor, and only the first exercise of a station in a session is looked at. The
    reward screen uses this to say so right away instead of leaving the map to be silent.
    """
    stations = {(p["key"], st["index"]): (p, st) for p in paths for st in p["stations"]}
    verdicts = []
    seen = set()
    for ex in exercises:
        if ex.total_sets <= 0:
            continue
        station = _station_for(ex.skill_key, ex.stage_index, ex.exercise_name)
        if not station or station in seen or station not in stations:
            continue
        seen.add(station)
        path, st = stations[station]
        low, high = _rep_range(st["reps"])
        average = ex.total_reps / ex.total_sets
        verdicts.append({
            "path": path["name"],
            "icon": path["icon"],
            "station": st["hebrew"],
            "unit_label": st["unit_label"],
            "average": round(average, 1),
            "floor": low,
            "target": high,
            "counted": average >= low,
            "in_range": st["in_range"],
            "to_conquer": STATION_SESSIONS_TO_CONQUER,
            "conquered": st["conquered"],
        })
    return verdicts
