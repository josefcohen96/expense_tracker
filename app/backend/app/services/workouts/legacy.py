"""The one-time import of the old browser-only "כבשתי!" station flags."""
import json
import sqlite3
from typing import Any

from .catalog import LEGACY_STATION_ORDER, RENAMED_ENGLISH, SKILL_PROGRESSIONS


def _legacy_progress_key(user_id: int) -> str:
    return f"workouts_legacy_conquered:{user_id}"


def _clean_progress(data: Any) -> dict[str, list[int]]:
    """Keep only real skill keys and in-range legacy stage indexes."""
    clean: dict[str, list[int]] = {}
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


def _legacy_to_current(progress: dict[str, list[int]]) -> dict[str, list[int]]:
    """Translate legacy stage indexes into today's ones; a dropped station is dropped."""
    current: dict[str, list[int]] = {}
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


def _stored_legacy_progress(db_conn: sqlite3.Connection, user_id: int) -> dict[str, list[int]]:
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


def _load_legacy_progress(db_conn: sqlite3.Connection, user_id: int) -> dict[str, list[int]]:
    """Stations a browser had marked conquered by hand, in today's station order."""
    return _legacy_to_current(_stored_legacy_progress(db_conn, user_id))
