from __future__ import annotations
import os
import sqlite3
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path as FSPath
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from ..db import get_db_conn
# ===== Templates dir (frontend) =====
ROOT_DIR = FSPath(__file__).resolve().parents[3]  # .../expense_tracker/app
FRONTEND_DIR = ROOT_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["pages"])

# --------- Pages ---------


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    """Dashboard: counters for total txs / total expenses / total income."""
    print(db_conn)
    stats: Dict[str, Any] = {"transactions_count": 0,
                             "total_expenses": 0.0, "total_income": 0.0}
    cur = db_conn.execute(
        "SELECT COUNT(*), "
        "SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), "
        "SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) "
        "FROM transactions"
    )
    row = cur.fetchone()
    if row:
        stats["transactions_count"] = row[0] or 0
        stats["total_expenses"] = abs(row[1] or 0.0)
        stats["total_income"] = row[2] or 0.0
    cur.close()
    return templates.TemplateResponse("pages/index.html", {"request": request, "stats": stats})


@router.get("/transactions", response_class=HTMLResponse)
async def transactions_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    txs = db_conn.execute(
        "SELECT t.id, t.date, t.amount, c.name AS category_name, u.name AS user_name, "
        "a.name AS account_name, t.notes, t.tags, t.category_id, t.user_id, t.account_id "
        "FROM transactions t "
        "JOIN categories c ON t.category_id = c.id "
        "JOIN users u ON t.user_id = u.id "
        "LEFT JOIN accounts a ON t.account_id = a.id "
        "ORDER BY t.date DESC, t.id DESC"
    ).fetchall()
    cats = db_conn.execute(
        "SELECT id, name FROM categories ORDER BY name").fetchall()
    users = db_conn.execute(
        "SELECT id, name FROM users ORDER BY id").fetchall()
    accs = db_conn.execute(
        "SELECT id, name FROM accounts ORDER BY name").fetchall()

    return templates.TemplateResponse(
        "pages/transactions.html",
        {"request": request, "transactions": txs, "categories": cats, "users": users, "accounts": accs, "today": date.today().isoformat(),  # <— כאן שולחים תאריך דיפולטיבי
         },
    )


@router.post("/transactions")
async def create_transaction(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> RedirectResponse:
    """HTML form submission (no python-multipart)."""
    from urllib.parse import parse_qs
    body = await request.body()
    form = {k: v[0] if isinstance(v, list) else v for k, v in parse_qs(
        body.decode("utf-8")).items()}
    date = form.get("date")
    amount = form.get("amount")
    category_id = form.get("category_id")
    user_id = form.get("user_id")
    account_id = form.get("account_id") or None
    notes = form.get("notes") or None
    tags = form.get("tags") or None

    try:
        amount_val = float(amount) if amount is not None else 0.0
        category_int = int(category_id) if category_id is not None else None
        user_int = int(user_id) if user_id is not None else None
        account_int = int(account_id) if account_id not in (None, "") else None
        db_conn.execute(
            "INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (date, amount_val, category_int, user_int, account_int, notes, tags),
        )
        db_conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return RedirectResponse(url="/transactions", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/recurrences", response_class=HTMLResponse)
async def recurrences_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    recs = db_conn.execute(
        "SELECT r.id, r.name, r.amount, c.name AS category_name, u.name AS user_name, "
        "r.frequency, r.start_date, r.end_date, r.day_of_month, r.weekday, r.active "
        "FROM recurrences r "
        "JOIN categories c ON r.category_id = c.id "
        "JOIN users u ON r.user_id = u.id "
        "ORDER BY r.name"
    ).fetchall()
    cats = db_conn.execute(
        "SELECT id, name FROM categories ORDER BY name").fetchall()
    users = db_conn.execute(
        "SELECT id, name FROM users ORDER BY id").fetchall()
    return templates.TemplateResponse(
        "pages/recurrences.html",
        {"request": request, "recurrences": recs,
            "categories": cats, "users": users},
    )


@router.get("/backup", response_class=HTMLResponse)
async def backup_page(request: Request) -> HTMLResponse:
    from ..api import backup as backup_mod
    import logging
    logger = logging.getLogger(__name__)

    try:
        backups_model = await backup_mod.api_backup_list()
        raw_backups = backups_model.backups if backups_model is not None else []
    except Exception:
        logger.exception("Failed to fetch backup list for page")
        raw_backups = []

    backups = []
    for b in raw_backups:
        try:
            # support pydantic model attributes or plain dicts with various key names
            file_name = (
                getattr(b, "file_name", None)
                or getattr(b, "file", None)
                or getattr(b, "name", None)
                or (b.get("file_name") if isinstance(b, dict) else None)
                or (b.get("file") if isinstance(b, dict) else None)
                or (b.get("name") if isinstance(b, dict) else None)
            )
            created_at = (
                getattr(b, "created_at", None)
                or getattr(b, "created", None)
                or (b.get("created_at") if isinstance(b, dict) else None)
                or (b.get("created") if isinstance(b, dict) else None)
            )
            size = (
                getattr(b, "size", None)
                or (b.get("size") if isinstance(b, dict) else None)
            )

            # if metadata missing, try to stat the file in BACKUP_DIR
            if (created_at in (None, "")) and file_name:
                try:
                    p = backup_mod.BACKUP_DIR / file_name
                    if p.exists():
                        created_at = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
                        size = p.stat().st_size if size in (None, 0) else size
                except Exception:
                    logger.debug("Cannot stat backup file %s", file_name, exc_info=True)

            backups.append({
                "file_name": file_name or "",
                "created_at": created_at or "",
                "size": int(size or 0),
            })
        except Exception:
            logger.exception("Failed to normalize backup item")
            continue

    return templates.TemplateResponse("pages/backup.html", {"request": request, "backups": backups})


@router.post("/backup/create")
async def backup_create(db_conn: sqlite3.Connection = Depends(get_db_conn)) -> RedirectResponse:
    from ..api import backup as backup_mod
    # pass DB connection to the create function so the service can query transactions
    try:
        path = backup_mod.create_backup(db_conn)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return RedirectResponse(url="/backup", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/backup/restore/{file_name}")
async def backup_restore_file(file_name: str) -> RedirectResponse:
    from ..api import backup as backup_mod
    file_path = backup_mod.BACKUP_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    try:
        backup_mod.restore_from_backup(file_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url="/backup", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/backup/download/{file_name}")
async def backup_download(file_name: str) -> FileResponse:
    from ..api import backup as backup_mod
    file_path = backup_mod.BACKUP_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(str(file_path), filename=file_name)


@router.get("/statistics", response_class=HTMLResponse)
async def statistics_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    # מאתחל נתונים לעמוד סטטיסטיקות
    monthly = db_conn.execute("""
        SELECT strftime('%Y-%m', date) AS ym,
               SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) AS expenses
        FROM transactions
        WHERE date >= date('now','-5 months','start of month')
        GROUP BY ym
        ORDER BY ym
    """).fetchall()
    # monthly_expenses = [{"month": r["ym"], "expenses": float(
    #     r["expenses"] or 0.0)} for r in monthly]

    # cats = db_conn.execute(
    #     "SELECT id, name FROM categories ORDER BY name").fetchall()
    users = db_conn.execute(
        "SELECT id, name FROM users ORDER BY id").fetchall()

    # cat_rows = db_conn.execute("""
    #     SELECT c.name AS category,
    #            SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS expenses
    #     FROM transactions t
    #     JOIN categories c ON t.category_id = c.id
    #     WHERE t.date >= date('now','-6 months')
    #     GROUP BY c.name
    #     ORDER BY expenses DESC
    # """).fetchall()

    # cat_breakdown = [{"label": r["category"], "value": float(
    #     r["expenses"] or 0.0)} for r in cat_rows]

    # Get monthly category breakdown for donut chart
    category_monthly_rows = db_conn.execute("""
        SELECT strftime('%Y-%m', t.date) AS month,
               c.name AS category,
               SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS amount
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now','start of month','-5 months')
        GROUP BY month, c.name
        ORDER BY month ASC, c.name ASC
    """).fetchall()
    
    # Also get total category breakdown for other charts
    category_total_rows = db_conn.execute("""
        SELECT c.name AS category,
               SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS total
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now','start of month','-5 months')
        GROUP BY c.name
        ORDER BY c.name
    """).fetchall()
    # user_rows = db_conn.execute("""
    #      SELECT u.name AS user,
    #             SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS expenses
    #      FROM transactions t
    #      JOIN users u ON t.user_id = u.id
    #      WHERE t.date >= date('now','-6 months')
    #      GROUP BY u.name
    #      ORDER BY expenses DESC
    #  """).fetchall()

    # user_breakdown = [{"label": r["user"], "value": float(
    #     r["expenses"] or 0.0)} for r in user_rows]

    return templates.TemplateResponse(
        "pages/statistics.html",
        {
            "request": request,
            "monthly_expenses": [dict(r) for r in (monthly or [])],
            "user_expenses": [dict(r) for r in (users or [])],
            "category_expenses": [dict(r) for r in (category_monthly_rows or [])],
            "category_totals": [dict(r) for r in (category_total_rows or [])],
        }
    )


def _find_db_file() -> Optional[Path]:
	# mirror logic used by backup_service
	candidates = [
		os.getenv("COUPLEBUDGET_DB"),
		"data.db", "couplebudget.db", "db.sqlite3", "app.db", "database.db"
	]
	root_dir = Path(__file__).resolve().parents[3]  # .../expense_tracker/app
	for c in candidates:
		if not c:
			continue
		p = Path(c) if Path(c).is_absolute() else root_dir / c
		if p.exists():
			return p
	return None

def _open_conn() -> sqlite3.Connection:
	db_path = _find_db_file()
	if not db_path:
		raise RuntimeError("DB file not found")
	conn = sqlite3.connect(str(db_path))
	conn.row_factory = sqlite3.Row
	return conn

@router.get("/statistics/category")
async def statistics_category(months: Optional[str] = Query(default=None)) -> List[Dict]:
	"""
	Return aggregated expenses by category with per-month breakdown.
	Params:
	- months: optional CSV of YYYY-MM values to filter on.
	Response items: { month: 'YYYY-MM', category: 'Name', amount: number }
	"""
	try:
		conn = _open_conn()
		params: list = []
		where = ""
		if months:
			parts = [m.strip() for m in months.split(",") if m.strip()]
			if parts:
				where = f" AND strftime('%Y-%m', t.date) IN ({','.join(['?']*len(parts))})"
				params.extend(parts)
		sql = f"""
			SELECT strftime('%Y-%m', t.date) AS month,
			       COALESCE(c.name, 'אחר') AS category,
			       SUM(t.amount) AS amount
			FROM transactions t
			LEFT JOIN categories c ON t.category_id = c.id
			WHERE 1=1 {where}
			GROUP BY month, category
			ORDER BY month ASC, category ASC
		"""
		rows = conn.execute(sql, params).fetchall()
		return [{"month": r["month"], "category": r["category"], "amount": float(r["amount"] or 0)} for r in rows]
	except Exception as exc:
		raise HTTPException(status_code=500, detail=str(exc))
	finally:
		try:
			conn.close()
		except Exception:
			pass
