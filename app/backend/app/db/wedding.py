"""Wedding module schema: tables, migrations and default rows."""

import sqlite3


def ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # --- Wedding Module Tables ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wedding_vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            contact_name TEXT,
            phone TEXT,
            price_quoted REAL,
            what_included TEXT,
            status TEXT DEFAULT 'not_contacted',
            deposit_amount REAL,
            deposit_paid_date TEXT,
            notes TEXT,
            instagram_url TEXT,
            facebook_url TEXT,
            location TEXT,
            inclusions TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS vendor_quote_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            quantity REAL DEFAULT 1,
            unit_price REAL NOT NULL DEFAULT 0,
            apply_vat INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wedding_guests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            group_name TEXT,
            status TEXT DEFAULT 'pending',
            plus_one INTEGER DEFAULT 0,
            plus_one_name TEXT,
            children_count INTEGER DEFAULT 0,
            needs_transport INTEGER DEFAULT 0,
            table_number INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migration: add children_count if missing (existing DBs)
    try:
        cols = [r[1] for r in cur.execute("PRAGMA table_info('wedding_guests')").fetchall()]
        if "children_count" not in cols:
            conn.execute("ALTER TABLE wedding_guests ADD COLUMN children_count INTEGER DEFAULT 0")
            conn.commit()
    except Exception:
        pass

    # Migration: add venue/social fields to wedding_vendors if missing (existing DBs)
    try:
        vendor_cols = [r[1] for r in cur.execute("PRAGMA table_info('wedding_vendors')").fetchall()]
        # portions_ordered: meals the catering vendor was booked for, compared to confirmed guests.
        for col, typedef in [("instagram_url", "TEXT"), ("facebook_url", "TEXT"), ("location", "TEXT"), ("inclusions", "TEXT"),
                             ("portions_ordered", "INTEGER")]:
            if col not in vendor_cols:
                conn.execute(f"ALTER TABLE wedding_vendors ADD COLUMN {col} {typedef}")
        conn.commit()
    except Exception:
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wedding_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            due_date TEXT,
            completed INTEGER DEFAULT 0,
            priority TEXT DEFAULT 'medium',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migration: owner = which household member (users.name) took the task; NULL = unassigned.
    try:
        task_cols = [r[1] for r in cur.execute("PRAGMA table_info('wedding_tasks')").fetchall()]
        if "owner" not in task_cols:
            conn.execute("ALTER TABLE wedding_tasks ADD COLUMN owner TEXT")
            conn.commit()
    except Exception:
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wedding_budget_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT DEFAULT 'other',
            budgeted_amount REAL DEFAULT 0,
            actual_amount REAL DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wedding_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS vendor_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_id INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            file_size INTEGER,
            mime_type TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wedding_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT,
            color TEXT DEFAULT 'white',
            pinned INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wedding_ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT DEFAULT 'כללי',
            status TEXT DEFAULT 'new',
            color TEXT DEFAULT 'white',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Items ordered from abroad: one sample first, then the big order.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wedding_overseas_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT,
            store TEXT,
            sample_price REAL,
            quantity_needed INTEGER,
            stage TEXT NOT NULL DEFAULT 'to_order',
            ordered_at TEXT,
            arrived_at TEXT,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wedding_overseas_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES wedding_overseas_items(id) ON DELETE CASCADE,
            author TEXT,
            body TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wedding_timeline_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            start_time TEXT NOT NULL,
            end_time TEXT,
            category TEXT DEFAULT 'general',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Backwards schedule: dates are wedding_date + offset_days, so they follow the
    # wedding date. custom_date pins a milestone the user moved by hand.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wedding_milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            offset_days INTEGER NOT NULL,
            kind TEXT NOT NULL DEFAULT 'general',
            completed INTEGER NOT NULL DEFAULT 0,
            custom_date TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wedding_seating_tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            shape TEXT NOT NULL DEFAULT 'round',
            capacity INTEGER NOT NULL DEFAULT 8,
            x REAL NOT NULL DEFAULT 100,
            y REAL NOT NULL DEFAULT 100,
            color TEXT NOT NULL DEFAULT 'rose',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wedding_seating_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_id INTEGER NOT NULL REFERENCES wedding_seating_tables(id) ON DELETE CASCADE,
            seat_number INTEGER NOT NULL,
            guest_id INTEGER NOT NULL REFERENCES wedding_guests(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(table_id, seat_number)
        )
    """)

    # Migration: older DBs had UNIQUE(guest_id) on wedding_seating_assignments,
    # which prevented a single guest from occupying multiple seats (themselves +
    # plus_one + children at the same table). Rebuild the table to drop that
    # constraint while keeping data and the table-seat uniqueness.
    try:
        existing_sql = cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='wedding_seating_assignments'"
        ).fetchone()
        if existing_sql and "UNIQUE(guest_id)" in existing_sql[0].replace(" ", ""):
            cur.execute("PRAGMA foreign_keys = OFF")
            cur.execute("""
                CREATE TABLE wedding_seating_assignments_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_id INTEGER NOT NULL REFERENCES wedding_seating_tables(id) ON DELETE CASCADE,
                    seat_number INTEGER NOT NULL,
                    guest_id INTEGER NOT NULL REFERENCES wedding_guests(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(table_id, seat_number)
                )
            """)
            cur.execute(
                "INSERT INTO wedding_seating_assignments_new (id, table_id, seat_number, guest_id, created_at) "
                "SELECT id, table_id, seat_number, guest_id, created_at FROM wedding_seating_assignments"
            )
            cur.execute("DROP TABLE wedding_seating_assignments")
            cur.execute("ALTER TABLE wedding_seating_assignments_new RENAME TO wedding_seating_assignments")
            conn.commit()
            cur.execute("PRAGMA foreign_keys = ON")
    except Exception:
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wedding_rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            room_type TEXT NOT NULL DEFAULT 'יחידים',
            max_capacity INTEGER NOT NULL DEFAULT 2,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wedding_room_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL REFERENCES wedding_rooms(id) ON DELETE CASCADE,
            guest_id INTEGER NOT NULL REFERENCES wedding_guests(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(guest_id)
        )
    """)

    # Migration: add staying_overnight to wedding_guests
    try:
        guest_cols = [r[1] for r in cur.execute("PRAGMA table_info('wedding_guests')").fetchall()]
        if "staying_overnight" not in guest_cols:
            conn.execute("ALTER TABLE wedding_guests ADD COLUMN staying_overnight INTEGER DEFAULT 0")
            conn.commit()
    except Exception:
        pass

    # Migration: add RSVP invite + meal preference fields to wedding_guests
    try:
        guest_cols = [r[1] for r in cur.execute("PRAGMA table_info('wedding_guests')").fetchall()]
        for col, typedef in [
            ("invite_token", "TEXT"),
            ("food_preference", "TEXT"),
            ("food_allergies", "TEXT"),
            ("rsvp_submitted_at", "TEXT"),
            ("meal_type", "TEXT DEFAULT 'regular'"),
            ("food_notes", "TEXT"),
            ("plus_one_meal_type", "TEXT DEFAULT 'regular'"),
        ]:
            if col not in guest_cols:
                conn.execute(f"ALTER TABLE wedding_guests ADD COLUMN {col} {typedef}")
        conn.commit()
    except Exception:
        pass

    # Cleanup: remove orphaned seating assignments pointing to deleted tables
    try:
        conn.execute("""
            DELETE FROM wedding_seating_assignments
            WHERE table_id NOT IN (SELECT id FROM wedding_seating_tables)
        """)
        conn.commit()
    except Exception:
        pass

    # Default rooms for the venue: 3 caravans of 4, 3 tents of 10, 8 double rooms
    default_rooms = (
        [(f"קרוואן {i}", "קרוואן", 4) for i in range(1, 4)]
        + [(f"אוהל {i}", "אוהל", 10) for i in range(1, 4)]
        + [(f"חדר {i}", "זוגי", 2) for i in range(1, 9)]
    )

    # Names of the previous venue's default rooms — used to detect an
    # untouched old seed so it can be replaced with the current one.
    _old_default_room_names = {
        "בית התה", "בית המטפל", "בית הסופר", "בית הנווד",
        "בית אברהם", "בית המרפא", "בית שחרות", "בית השחר",
    }

    try:
        existing_names = {
            r[0] for r in cur.execute("SELECT name FROM wedding_rooms").fetchall()
        }
        if existing_names == _old_default_room_names:
            # DB still holds the old venue's stock rooms — replace them.
            # Room assignments to the old rooms are dropped; affected guests
            # reappear in the "waiting for a room" list on the lodging page.
            cur.execute(
                "DELETE FROM wedding_room_assignments WHERE room_id IN "
                "(SELECT id FROM wedding_rooms)"
            )
            cur.execute("DELETE FROM wedding_rooms")
            existing_names = set()
        if not existing_names:
            for name, room_type, capacity in default_rooms:
                cur.execute(
                    "INSERT INTO wedding_rooms (name, room_type, max_capacity) VALUES (?,?,?)",
                    (name, room_type, capacity)
                )
        conn.commit()
    except Exception:
        pass

    # Starter milestones, once a wedding date exists (also seeded when the date is first saved).
    try:
        from ..services import wedding_plan
        if wedding_plan.get_wedding_date(conn):
            wedding_plan.seed_default_milestones(conn)
            conn.commit()
    except Exception:
        pass
