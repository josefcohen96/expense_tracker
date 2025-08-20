from pathlib import Path
from datetime import datetime, date
from typing import Optional, List, Dict, Tuple
import sqlite3
import logging
import zipfile
import shutil
import os

from openpyxl import Workbook

LOG = logging.getLogger(__name__)

# Prevent re-entrant / recursive backups
_IN_PROGRESS = False

ROOT_DIR = Path(__file__).resolve().parents[2]  # .../expense_tracker/app
BACKUP_DIR = ROOT_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
EXCEL_ROOT = BACKUP_DIR / "excel"
EXCEL_ROOT.mkdir(parents=True, exist_ok=True)

# Update HEADERS to match your actual table columns
HEADERS = [
    "id", "date", "amount", "category", "user_id", "account_id", "notes", "tags"
]


def _last_n_months(n: int) -> List[Tuple[int, int]]:
    """Return list of (year, month) for current month and previous n-1 months."""
    today = date.today()
    result = []
    for i in range(n):
        total_month = today.year * 12 + today.month - 1 - i
        y = total_month // 12
        m = total_month % 12 + 1
        result.append((y, m))
    return list(reversed(result))  # older -> newer


def _find_db_file() -> Optional[Path]:
    candidates = [
        os.getenv("COUPLEBUDGET_DB"),
        "data.db", "couplebudget.db", "db.sqlite3", "app.db", "database.db"
    ]
    for c in candidates:
        if not c:
            continue
        p = Path(c) if Path(c).is_absolute() else ROOT_DIR / c
        if p.exists():
            return p
    return None


def _open_conn_from_path_or_conn(db_conn: Optional[sqlite3.Connection]):
    if db_conn is not None:
        return db_conn
    db_path = _find_db_file()
    if not db_path:
        raise RuntimeError("No DB connection provided and DB file not found in known locations")
    return sqlite3.connect(str(db_path))


def create_backup_file(db_conn: Optional[sqlite3.Connection] = None) -> Path:
    """
    Create a dated folder (DD MM YYYY) under backups/ and write an Excel file for each of the
    last 6 months (including current) containing that month's transactions.
    Returns path to the created folder (Path).
    """
    global _IN_PROGRESS
    if _IN_PROGRESS:
        raise RuntimeError("Backup already in progress (re-entrant call detected)")
    _IN_PROGRESS = True

    conn_provided = db_conn is not None
    conn = None
    try:
        conn = _open_conn_from_path_or_conn(db_conn)
        # ensure row factory for dict-like access
        try:
            conn.row_factory = sqlite3.Row
        except Exception:
            pass

        folder_name = datetime.utcnow().strftime("%d %m %Y")
        out_dir = BACKUP_DIR / folder_name
        out_dir.mkdir(parents=True, exist_ok=True)

        months = _last_n_months(6)
        for (year, month) in months:
            ym = f"{year}-{month:02d}"
            cur = conn.execute(
                """
                SELECT t.id, t.date, t.amount, c.name as category, t.user_id, t.account_id, t.notes, t.tags
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE strftime('%Y-%m', t.date) = ?
                ORDER BY t.date ASC, t.id ASC
                """,
                (ym,),
            )
            rows = cur.fetchall()
            # create workbook
            wb = Workbook()
            ws = wb.active
            ws.append(HEADERS)
            
            for r in rows:
                vals = [
                    r["id"],
                    r["date"],
                    r["amount"],
                    r["category"],  # now the category name
                    r["user_id"],
                    r["account_id"],
                    r["notes"],
                    r["tags"],
                ]
                ws.append(vals)
            file_name = f"expenses_{year}_{month:02d}.xlsx"
            wb.save(filename=str(out_dir / file_name))

        LOG.info("Created excel backup folder %s", out_dir.name)
        return out_dir
    finally:
        _IN_PROGRESS = False
        if conn is not None and not conn_provided:
            try:
                conn.close()
            except Exception:
                pass


def list_backup_files() -> List[Dict]:
    """
    List items in BACKUP_DIR. For files: file_name, created_at, size.
    For directories: treat the dir as a backup (name, mtime, aggregated size).
    """
    items = []
    for p in sorted(BACKUP_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            if p.is_file():
                stat = p.stat()
                items.append({
                    "file_name": p.name,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "size": stat.st_size,
                })
            elif p.is_dir():
                total = 0
                for f in p.rglob("*"):
                    if f.is_file():
                        try:
                            total += f.stat().st_size
                        except Exception:
                            continue
                stat = p.stat()
                items.append({
                    "file_name": p.name,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "size": total,
                })
        except Exception:
            LOG.exception("Failed to stat backup entry %s", p)
            continue
    return items


def restore_from_file(path: Path) -> Dict:
    """
    Restore backup from a path that can be either:
      - a zip file (will be extracted into EXCEL_ROOT)
      - a directory containing excel files (files will be copied into EXCEL_ROOT)
    Returns counts of files restored.
    """
    restored = {"files": 0}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    if p.is_file() and zipfile.is_zipfile(str(p)):
        with zipfile.ZipFile(str(p), "r") as zf:
            tmp = BACKUP_DIR / f".restore_tmp_{datetime.utcnow().timestamp()}"
            if tmp.exists():
                shutil.rmtree(tmp)
            tmp.mkdir(parents=True, exist_ok=True)
            zf.extractall(tmp)
            for f in tmp.iterdir():
                dst = EXCEL_ROOT / f.name
                if dst.exists():
                    dst.unlink()
                shutil.move(str(f), str(dst))
                restored["files"] += 1
            shutil.rmtree(tmp)
    elif p.is_dir():
        for f in p.iterdir():
            if f.is_file() and f.suffix.lower() in (".xlsx", ".xlsm", ".xltx"):
                dst = EXCEL_ROOT / f.name
                if dst.exists():
                    dst.unlink()
                shutil.copy2(str(f), str(dst))
                restored["files"] += 1
    else:
        raise RuntimeError("Unsupported restore file type")

    LOG.info("Restored %d files from %s", restored["files"], p.name)
    return restored
