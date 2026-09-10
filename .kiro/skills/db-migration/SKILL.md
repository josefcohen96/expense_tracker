---
name: db-migration
description: Add a new column or table to the SQLite database following the project's inline migration pattern. Use this when adding new fields to existing tables, creating new tables, or backfilling data for new columns.
metadata:
  author: kiro
  version: 1.0.0
---

## Context

This project uses SQLite with **no migration framework**. All schema changes live in `app/backend/app/db.py` inside the `initialise_database()` function. Migrations run at every app startup — they must be **idempotent** and **non-destructive**.

The `CREATE TABLE IF NOT EXISTS` pattern handles new tables. The `PRAGMA table_info()` + `ALTER TABLE ADD COLUMN` pattern handles new columns on existing tables.

**Important constraints:**
- SQLite does not support `ALTER TABLE DROP COLUMN` (only add)
- SQLite does not support adding a NOT NULL column without a DEFAULT to an existing table
- `PRAGMA foreign_keys = ON` is set per-connection — not a permanent DB setting
- Amounts are stored as negative for expenses, positive for income

## Workflow

### Adding a new column to an existing table

1. Read `app/backend/app/db.py` to understand the current schema for the target table
2. Find the relevant `CREATE TABLE IF NOT EXISTS` block — add the column there first (so new databases get it from the start)
3. Below the `CREATE TABLE` block, add an inline migration inside the `# --- Migrations ---` section using this exact pattern:

```python
try:
    cols = [r[1] for r in cur.execute("PRAGMA table_info('table_name')").fetchall()]
    if "new_column_name" not in cols:
        cur.execute("ALTER TABLE table_name ADD COLUMN new_column_name TYPE DEFAULT value")
        # Backfill if needed:
        # cur.execute("UPDATE table_name SET new_column_name = ? WHERE condition", (value,))
except Exception:
    pass  # Migration best-effort; do not fail app startup
```

4. If the new column needs a backfill (e.g., computing a value from existing data), add the `UPDATE` statement inside the `if` block
5. If the new column is referenced in a Pydantic schema, update the relevant file in `app/backend/app/schemas/`
6. If the column is exposed via an API endpoint, update the relevant file in `app/backend/app/api/`

### Adding a new table

1. Add a `CREATE TABLE IF NOT EXISTS` block inside `initialise_database()` — place it after its parent tables (respect FK order)
2. If the table needs seed data, add an `if not cur.execute("SELECT COUNT(*) FROM new_table").fetchone()[0]:` block with `INSERT` statements
3. Create a Pydantic schema in `app/backend/app/schemas/` if the table will be exposed via API
4. Create an API router in `app/backend/app/api/` if needed
5. Register the router in `app/backend/app/main.py`

## Checklist before finishing

- [ ] The `CREATE TABLE IF NOT EXISTS` block has the new column/table
- [ ] The inline migration check uses `PRAGMA table_info()` and is wrapped in `try/except`
- [ ] New nullable columns use `DEFAULT NULL`; boolean columns use `DEFAULT 0`
- [ ] If a FK is added, verify the referenced table is created first in `initialise_database()`
- [ ] Any Pydantic schema that represents this table is updated
- [ ] Run the app locally (`uvicorn app.backend.app.main:app --reload`) and verify startup completes without errors
- [ ] Verify the column appears: `sqlite3 app/backend/data/budget.db ".schema table_name"`

## Common pitfalls

- Never use `NOT NULL` on a new column without `DEFAULT` — SQLite will reject it for existing rows
- The migration `try/except` must swallow all exceptions — a migration failure must not crash startup
- Do not add `FOREIGN KEY` constraints via `ALTER TABLE` — SQLite doesn't support it; add FKs only in `CREATE TABLE`
- Always keep the `CREATE TABLE` block and the migration in sync — the `CREATE TABLE` is the source of truth for new databases
