"""Home renovation module schema: tables, migrations and the starter rooms."""

import sqlite3


def ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # --- Home Renovation Module Tables ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS renovation_rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            icon TEXT DEFAULT '🏠',
            notes TEXT,
            image_url TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS renovation_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            room_id INTEGER REFERENCES renovation_rooms(id) ON DELETE SET NULL,
            status TEXT NOT NULL DEFAULT 'todo',
            priority TEXT NOT NULL DEFAULT 'medium',
            due_date TEXT,
            notes TEXT,
            link_url TEXT,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS renovation_ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            room_id INTEGER REFERENCES renovation_rooms(id) ON DELETE SET NULL,
            status TEXT NOT NULL DEFAULT 'new',
            color TEXT NOT NULL DEFAULT 'white',
            image_url TEXT,
            link_url TEXT,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Equipment/materials needed for a task or a room ("ציוד"). Rows survive the
    # task or room they belong to — the shopping list matters more than the link.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS renovation_supplies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            quantity TEXT,
            status TEXT NOT NULL DEFAULT 'needed',
            room_id INTEGER REFERENCES renovation_rooms(id) ON DELETE SET NULL,
            task_id INTEGER REFERENCES renovation_tasks(id) ON DELETE SET NULL,
            notes TEXT,
            link_url TEXT,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Before/after journal. An entry usually starts life with only a "before"
    # photo — the "after" one lands weeks later — so both photo columns are
    # nullable and hold the stored (UUID) filename, never a user-supplied name.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS renovation_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            room_id INTEGER REFERENCES renovation_rooms(id) ON DELETE SET NULL,
            entry_date TEXT,
            notes TEXT,
            before_photo TEXT,
            after_photo TEXT,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Seed a starter set of rooms so the site is usable from the first visit.
    try:
        has_rooms = cur.execute("SELECT COUNT(*) FROM renovation_rooms").fetchone()[0]
        if not has_rooms:
            for idx, (room_name, room_icon) in enumerate([
                ("סלון", "🛋️"),
                ("מטבח", "🍳"),
                ("חדר שינה", "🛏️"),
                ("חדר אמבטיה", "🛁"),
                ("שירותים", "🚽"),
                ("מרפסת", "🪴"),
                ("מסדרון", "🚪"),
            ]):
                cur.execute(
                    "INSERT INTO renovation_rooms (name, icon, sort_order) VALUES (?,?,?)",
                    (room_name, room_icon, idx),
                )
    except Exception:
        pass

    # One-time: the original seed shipped a catch-all "כללי" room, which is
    # redundant now that a task can simply have no room. Turn it into a real
    # room instead, keeping anything already filed under it. Guarded by a
    # settings flag so a room the user creates later with that name is left be.
    try:
        done = cur.execute(
            "SELECT 1 FROM system_settings WHERE key='renovation_general_room_replaced'"
        ).fetchone()
        if not done:
            general = cur.execute("SELECT id FROM renovation_rooms WHERE name='כללי'").fetchone()
            taken = cur.execute("SELECT 1 FROM renovation_rooms WHERE name='מסדרון'").fetchone()
            if general and not taken:
                cur.execute(
                    "UPDATE renovation_rooms SET name='מסדרון', icon='🚪' WHERE id=?",
                    (general[0],),
                )
            cur.execute(
                "INSERT OR REPLACE INTO system_settings (key, value) VALUES "
                "('renovation_general_room_replaced', '1')"
            )
    except Exception:
        pass
