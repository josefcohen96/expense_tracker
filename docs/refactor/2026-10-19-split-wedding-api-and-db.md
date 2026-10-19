# Refactor spec — `api/wedding.py` → package per feature, `db.py` → package per module (phase 3)

**Kind:** pure refactor. No behaviour change, no UI change, no schema change, no new dependency.
**Branch:** `claude/split-wedding-api-and-db` (stacked on `claude/split-route-modules`, PR #46). You do not touch git.
**Definition of done:** the Acceptance criteria section, all of it.

## Why

`api/wedding.py` (1,060 lines) is one router for fifteen wedding features; its own `# ─── Section ───` dividers
already show where the seams are. `db.py` is one 790-line function, `initialise_database()`, that creates and
migrates the tables of four unrelated modules in sequence. Both are the files every wedding or schema change
has to touch, so both get the most merge conflicts and the longest reviews.

## Rules for this refactor

1. **Move, don't edit.** Handler bodies, SQL strings, comments and constants move verbatim. No renames, no
   signature changes, no reordering of statements inside a function, no "while I'm here" fixes. The reviewer
   diffs every non-import line of the new files against the old ones; anything that is not a pure move must
   be explainable in one line in your report.
2. **Imports follow the code.** Each new module imports only what its code uses; `ruff check .` must pass.
   No `import *`, no re-export shims. Update importers instead (they are listed below).
3. **Order of execution is preserved** wherever it can matter: the sequence in which tables are created,
   migrated and seeded is exactly today's sequence (SQLite enforces foreign keys per connection, and a
   migration can read a table an earlier section created). Route registration order within the wedding API
   does not matter (no two wedding API routes share a path pattern with the same method), but keep the
   sections in today's order anyway.
4. `main.py` keeps importing `router as wedding_api` from `.api.wedding` — the package exposes the same name.
5. Hebrew UI / English code. No template, CSS or JS changes.

## Part A — `api/wedding.py` → `api/wedding/` package

Delete `app/backend/app/api/wedding.py`; create `app/backend/app/api/wedding/` with one module per section.
Split exactly at the existing `# ─── … ───` divider comments (keep each divider as the first comment of its
module):

| Module | Divider(s) → routes | Module-level names that move with it |
|---|---|---|
| `vendors.py` | *Vendors* + *Quote Items*: `/vendors` GET/POST, `/vendors/{vendor_id}` PATCH/DELETE, `/vendors/{vendor_id}/quote-items` GET/POST | `VAT_RATE` |
| `guests.py` | *Guests* + *Invite Tokens*: `/guests` GET/POST, `/guests/{guest_id}` PATCH/DELETE, `/guests/{guest_id}/generate-invite`, `/guests/{guest_id}/invite-link` | `DEFAULT_BASE_URL` |
| `rooms.py` | *Rooms*: `/rooms`…, `/rooms/{room_id}/assign/{guest_id}`, `/rooms/assignments/{guest_id}` | — |
| `tasks.py` | *Tasks* | — |
| `budget.py` | *Budget Items* | — |
| `settings.py` | *Settings*: `/settings` GET/POST | — |
| `files.py` | *Vendor File Attachments*: `/vendors/{vendor_id}/files` GET/POST, `/files/{file_id}` GET/DELETE | `_UPLOADS_DIR` (same path expression — note `parents[...]` must still resolve to `app/uploads/vendor_files`; the file is one directory deeper now, so the index changes from 3 to 4 and you prove it with a one-line `python -c` print in your report), `_ALLOWED_MIME`, `_ALLOWED_EXT`, `_MAX_SIZE_MB`, the `_sniff_mime` import |
| `notes.py` | *Notes* | — |
| `ideas.py` | *Ideas* | — |
| `overseas.py` | *Overseas orders*: `/overseas`…, `/overseas/{item_id}/comments` | `_clean_text`, `_clean_url` |
| `timeline.py` | *Timeline Events* | — |
| `milestones.py` | *Milestones* | — |
| `seating.py` | *Seating Chart*: `/seating`, `/seating/tables`…, `/seating/assign`… | — |

Each module starts with its own `router = APIRouter(prefix="/api/wedding", tags=["wedding"])` and imports the
schemas it uses from `...schemas.wedding` and the services it uses (`overseas`, `wedding_plan`, `people`).

`api/wedding/__init__.py`:

```python
"""The wedding module's JSON API, one router per feature, exposed as a single router for main.py."""
from fastapi import APIRouter

from . import budget, files, guests, ideas, milestones, notes, overseas, rooms, seating, settings, tasks, timeline, vendors

router = APIRouter()
for _module in (vendors, guests, rooms, tasks, budget, settings, files, notes, ideas, overseas, timeline, milestones, seating):
    router.include_router(_module.router)
```

(Nesting is fine here: no wedding API route is `@public`, so the `build_public_route_matchers` caveat in
requirements.txt does not apply. Say so in a comment above the loop.)

Importers: only `main.py` (`from .api.wedding import router as wedding_api`) — unchanged.

## Part B — `db.py` → `db/` package

Delete `app/backend/app/db.py`; create `app/backend/app/db/`:

| Module | Contents |
|---|---|
| `__init__.py` | The module docstring and the Hebrew comments at the top, `_DEFAULT_DB_PATH`, `DB_PATH`, `get_connection`, `get_db_conn`, `get_db_path`, `_reset_database_if_requested` — all verbatim — and the new `initialise_database()` below. |
| `finance.py` | `def ensure_schema(conn: sqlite3.Connection) -> None:` whose body is lines **95–332** of today's function verbatim (from `# Create tables` through the Yonatan users row and the `# (removed) default challenges seed` comment), preceded by `cur = conn.cursor()`. Core tables (`categories`, `users`, `accounts`, `transactions`, `recurrences`, `recurrence_skips`, `system_settings`), finance migrations 1–4, default data. |
| `wedding.py` | `ensure_schema(conn)` = lines **333–699** (`# --- Wedding Module Tables ---` through the starter-milestones block). |
| `renovation.py` | `ensure_schema(conn)` = lines **700–823** (`# --- Home Renovation Module Tables ---` through the "כללי" room one-time fix). |
| `workouts.py` | `ensure_schema(conn)` = lines **824–880** (`# Workouts Tracker Table`, its migration, `spanish_reviews` + index, `push_subscriptions`). The arena's three tables live together on purpose; say so in the module docstring. |

Confirm the four line ranges with `grep -n` on the current file before slicing; they are from the revision this
spec was written against and must land on the section comments quoted above. The final `conn.commit()` /
`conn.close()` (lines 881–882) are **not** part of any section; they belong to the orchestrator.

The orchestrator in `db/__init__.py` (the only new code in this phase):

```python
def initialise_database() -> None:
    """Create database tables if they don't exist."""
    conn = get_connection()
    for module in (finance, wedding, renovation, workouts):
        module.ensure_schema(conn)
    conn.commit()
    conn.close()
```

Sections keep their own intermediate `conn.commit()` calls exactly where they are today. Each section only
uses `conn` and its own `cur = conn.cursor()`; if you find a local variable defined in one section and read in
a later one, **stop and report** — do not duplicate it or hoist it. (The ones I saw — `default_rooms`,
`_old_default_room_names` — are defined and used inside the wedding section.)

Importers (`grep -rn "\.db import\|import db\b\|app\.db\b" app tests tools`): every `from ..db import get_db_conn`,
`from ..db import get_connection`, `from . import db` and `import app.backend.app.db as db_module` keeps working
unchanged because the package's `__init__` exposes the same names. `tests/conftest.py` does
`importlib.reload(db_module)` to re-read `BUDGET_DB_PATH`; that reloads the package `__init__`, which is where
`DB_PATH` lives, so it still works — run the suite to prove it. `app/backend/app/scripts/create_minimal_db.py`
and `seed_data.py` open sqlite3 directly; check whether either imports `DB_PATH` or `db.py` and repoint if so.

## Docs and skills to update (the only non-code edits allowed)

- `CLAUDE.md`: in **Project Structure** replace the `db.py` line with the `db/` package (one line per file) and
  the `api/wedding.py` line with the `api/wedding/` package (one line: "package, one module per feature,
  `__init__` aggregates the routers"); in **Database Schema** change the sentence "**Migrations** are inline in
  `initialise_database()` in `db.py`…" to say they are inline in each module's `ensure_schema(conn)` under
  `app/backend/app/db/`, called in order by `initialise_database()`; in **Key Patterns and Conventions** item 3
  likewise. Nothing else in CLAUDE.md.
- `.claude/skills/db-migration/SKILL.md`: every `app/backend/app/db.py` / "inside `initialise_database()`"
  reference becomes "the module's `ensure_schema(conn)` in `app/backend/app/db/<finance|wedding|renovation|workouts>.py`";
  the "FK referenced table is created first" checklist line adds "…or in an earlier module in the
  `initialise_database()` order (finance → wedding → renovation → workouts)". Keep everything else.
- `.claude/skills/wedding-vendor-workflow/SKILL.md`: `app/backend/app/api/wedding.py` → `app/backend/app/api/wedding/vendors.py`
  (and `files.py` for the attachments routes); "inline migration in `db.py`" → `db/wedding.py`.
- `.claude/agents/implementer.md` line "Migrations are inline and idempotent in `initialise_database()`" →
  "in the module's `ensure_schema()` under `app/backend/app/db/`".
- `docs/refactor/schema-baseline.txt` and `docs/refactor/route-table-baseline.txt` stay as committed; they are
  the before-pictures. `tools/refactor_baseline.py` produces both (see criteria 5–6).

## Acceptance criteria

1. `api/wedding.py` and `db.py` no longer exist; the two packages exist with the modules and contents above.
2. `.venv/Scripts/python.exe -m ruff check .` → `All checks passed!`
3. `.venv/Scripts/python.exe -m pytest` → `307 passed, 1 skipped` (exact baseline).
4. `grep -rn "APIRouter(prefix=\"/api/wedding\"" app/backend/app/api/wedding/` returns exactly 13 lines, one per
   feature module, and `grep -c "include_router" app/backend/app/api/wedding/__init__.py` is 1 (the loop).
5. Route table unchanged:
   `.venv/Scripts/python.exe tools/refactor_baseline.py routes 2>/dev/null | sed '/^Session configuration:/d; /^SessionMiddleware added/d' | tr -d '\r' | diff - docs/refactor/route-table-baseline.txt`
   prints nothing.
6. Schema and seed rows unchanged:
   `.venv/Scripts/python.exe tools/refactor_baseline.py schema 2>/dev/null | sed '/^Session configuration:/d; /^SessionMiddleware added/d' | tr -d '\r' | diff - docs/refactor/schema-baseline.txt`
   prints nothing.
7. `_UPLOADS_DIR` in `api/wedding/files.py` resolves to the same absolute path as before
   (`<repo>/app/uploads/vendor_files`): paste the `python -c` output in your report.
8. `git status` shows no change under `app/frontend/`.

## Report

The four-section report from your agent instructions. In **Deviations and doubts**: every name the spec did not
list and where you put it, every line that is not a pure move, the criterion 5/6 diff output if not empty, and
the criterion 7 path.
