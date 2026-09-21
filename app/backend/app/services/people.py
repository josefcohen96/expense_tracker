"""The two people who share the app, as the finances `users` table knows them.

Wedding task owners reuse this list (the finances payer field) rather than a
second one. Colors are assigned by the users' id order, so both people see the
same color for the same person.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from .access import display_name, is_module_only_user, normalise_username

PERSON_COLORS = ("#4f46e5", "#0d9488", "#d97706")
PERSON_TINTS = ("#eef2ff", "#f0fdfa", "#fffbeb")

# Everyone with an arena: the household plus the workouts-only login (see access.py).
WORKOUT_PARTICIPANTS = ("Yosef", "Karina", "Yonatan")


def household(conn: sqlite3.Connection) -> list[dict]:
    """Main users (Yosef, Karina), each with display name, initial and colors."""
    rows = conn.execute(
        "SELECT id, name FROM users WHERE name IN ('Yosef','Karina') ORDER BY id"
    ).fetchall()
    if not rows:
        rows = conn.execute("SELECT id, name FROM users ORDER BY id LIMIT 2").fetchall()
    people = []
    for idx, row in enumerate(rows):
        shown = display_name(row["name"])
        people.append({
            "id": row["id"],
            "name": row["name"],
            "display": shown,
            "initial": shown[:1],
            "color": PERSON_COLORS[idx % len(PERSON_COLORS)],
            "tint": PERSON_TINTS[idx % len(PERSON_TINTS)],
        })
    return people


def workout_people(conn: sqlite3.Connection, viewer: Any = None) -> list[dict]:
    """Who the workouts back office may manage, as seen by `viewer`.

    The household sees everyone who trains (Yosef, Karina, Yonatan); a login that
    owns only the workouts module sees just their own entry.
    """
    placeholders = ",".join("?" * len(WORKOUT_PARTICIPANTS))
    rows = conn.execute(
        f"SELECT id, name FROM users WHERE name IN ({placeholders}) ORDER BY id",
        WORKOUT_PARTICIPANTS,
    ).fetchall()
    people = []
    for idx, row in enumerate(rows):
        shown = display_name(row["name"])
        people.append({
            "id": row["id"],
            "name": row["name"],
            "display": shown,
            "initial": shown[:1],
            "color": PERSON_COLORS[idx % len(PERSON_COLORS)],
            "tint": PERSON_TINTS[idx % len(PERSON_TINTS)],
        })
    if is_module_only_user(viewer):
        own = find_person(people, viewer)
        return [own] if own else []
    return people


def find_person(people: list[dict], user: Any) -> Optional[dict]:
    """The household entry matching a session user / username / owner value."""
    key = normalise_username(user)
    if not key:
        return None
    return next((p for p in people if p["name"].upper() == key), None)


def valid_owner(conn: sqlite3.Connection, owner: Optional[str]) -> Optional[str]:
    """Canonical users.name for an owner value, or None for unassigned.

    Raises ValueError for a name that is not one of the household.
    """
    if owner is None or not str(owner).strip():
        return None
    person = find_person(household(conn), owner)
    if not person:
        raise ValueError("owner must be one of the household users")
    return person["name"]
