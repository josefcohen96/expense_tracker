"""The home shell: היום (/), the עוד page and the service worker."""
from __future__ import annotations

import logging
import sqlite3

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from ..db import get_db_conn
from ..services import wedding_plan
from ..services.access import home_path_for, is_module_only_user
from ..services.people import household
from ..services.today import build_today
from ..templating import STATIC_DIR, templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    """היום — the cross-module action queue (mobile home; desktop forwards to /finances)."""
    user_obj = getattr(request.state, "user", None) or request.session.get("user")
    if is_module_only_user(user_obj):
        # Tsahala / Yonatan own one module: send them to it instead of the shared home.
        return RedirectResponse(url=home_path_for(user_obj), status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request, "pages/today.html", {
        "request": request,
        "today": build_today(db_conn, user_obj),
        "people": household(db_conn),
    })


@router.get("/more", response_class=HTMLResponse)
async def more_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    return templates.TemplateResponse(request, "pages/more.html", {
        "request": request,
        "wedding_date": wedding_plan.get_setting(db_conn, "wedding_date") or "",
        "venue_capacity": wedding_plan.get_setting(db_conn, "venue_capacity") or "",
    })


@router.get("/sw.js")
async def service_worker() -> FileResponse:
    sw_path = STATIC_DIR / "js" / "sw.js"
    if not sw_path.exists():
        from starlette.responses import Response
        return Response("", media_type="application/javascript")
    return FileResponse(str(sw_path), media_type="application/javascript")
