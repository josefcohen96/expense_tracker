"""Print a before/after picture of the app for move-only refactors.

    python tools/refactor_baseline.py routes   # every HTTP route + the public (auth-bypassing) matchers
    python tools/refactor_baseline.py schema   # schema of a freshly initialised DB + the rows it seeds

Run it from the repo root with the project's test interpreter, redirect the output to a file under
docs/refactor/ before the change, and diff a fresh run against that file after it. Both pictures are
sorted so registration/creation order is not part of the contract; the schema picture masks
timestamps so it is reproducible.

The script needs no environment: it points the app at a throwaway database and satisfies the
startup checks itself (auth is irrelevant, nothing is served).
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?(\.\d+)?)?$")


def _prepare_env() -> str:
    tmp_dir = tempfile.mkdtemp(prefix="refactor-baseline-")
    db_path = os.path.join(tmp_dir, "baseline.sqlite3")
    os.environ["BUDGET_DB_PATH"] = db_path
    os.environ.setdefault("PYTEST_CURRENT_TEST", "refactor_baseline")  # lets main.py start without a secret
    os.environ.setdefault("AUTH_ENABLED", "0")
    sys.path.insert(0, str(ROOT))
    return db_path


def routes() -> None:
    _prepare_env()
    import app.backend.app.main as m  # noqa: PLC0415 - imported after the env is prepared on purpose

    rows = sorted(
        (r.path, ",".join(sorted(r.methods or [])), getattr(r, "name", ""))
        for r in m.app.routes
        if hasattr(r, "methods")
    )
    print("# Every HTTP route the app registers: path, methods, handler name. Sorted; order of registration is not part of the contract")
    print("# (no two routes here share a path pattern with overlapping methods, so order cannot change matching).")
    for row in rows:
        print(*row, sep="\t")
    print("# public (auth-bypassing) route matchers:")
    for pattern, methods in sorted(
        (p.pattern, ",".join(sorted(ms)) if ms else "*") for p, ms in m.PUBLIC_ROUTE_MATCHERS
    ):
        print("public", pattern, methods, sep="\t")


def schema() -> None:
    db_path = _prepare_env()
    import app.backend.app.db as db  # noqa: PLC0415

    db.initialise_database()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    print("# Schema of a freshly initialised database (sqlite_master, sorted by type then name), then every seeded row.")
    objects = conn.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"
    ).fetchall()
    for o in objects:
        sql = " ".join(o["sql"].split())  # whitespace-insensitive: only the statement matters
        print(f"{o['type']}\t{o['name']}\t{o['tbl_name']}\t{sql}")
    print("# Seeded rows per table (timestamps masked):")
    tables = [o["name"] for o in objects if o["type"] == "table" and not o["name"].startswith("sqlite_")]
    for t in sorted(tables):
        rows = conn.execute(f'SELECT * FROM "{t}" ORDER BY rowid').fetchall()
        print(f"table {t}: {len(rows)} rows")
        for r in rows:
            cells = []
            for k in r.keys():
                v = r[k]
                if isinstance(v, str) and _TIMESTAMP.match(v):
                    v = "<timestamp>"
                cells.append(f"{k}={v!r}")
            print("   ", ", ".join(cells))
    conn.close()


def main() -> None:
    # Seed data is Hebrew (and has the odd emoji); never let a cp1252 console truncate the picture.
    sys.stdout.reconfigure(encoding="utf-8")
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    if what == "routes":
        routes()
    elif what == "schema":
        schema()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
