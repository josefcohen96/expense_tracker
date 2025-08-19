from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from .core import config
from .legacy import db as legacy_db
from .legacy import recurrence as legacy_recurrence
from .legacy import backup as legacy_backup
from .web.pages import router as pages_router, mount_static
from .api.routes import router as api_router


def create_app() -> FastAPI:
    app = FastAPI(title="CoupleBudget Local", version="0.2.0")

    # Ensure DB exists
    legacy_db.initialise_database()

    # Templates and static are mounted from frontend folder inside web/pages module
    mount_static(app)

    # Routers
    app.include_router(pages_router)
    app.include_router(api_router)

    @app.on_event("startup")
    def _startup() -> None:
        try:
            inserted = legacy_recurrence.apply_recurring()
            if inserted:
                print(f"Applied {inserted} recurring transactions on startup.")
        except Exception as exc:
            print(f"Failed to apply recurring transactions: {exc}")
        try:
            if str(os.getenv("AUTO_BACKUP_ON_STARTUP", "1")) in {"1", "true", "True"}:
                bpath = legacy_backup.create_backup(only_if_no_backup_today=True)
                print(f"Startup backup ensured at: {bpath}")
        except Exception as exc:
            print(f"Startup backup failed: {exc}")

    @app.on_event("shutdown")
    def _shutdown() -> None:
        try:
            if str(os.getenv("AUTO_BACKUP_ON_SHUTDOWN", "1")) in {"1", "true", "True"}:
                bpath = legacy_backup.create_backup(only_if_no_backup_today=True)
                print(f"Shutdown backup ensured at: {bpath}")
        except Exception as exc:
            print(f"Shutdown backup failed: {exc}")

    return app


app = create_app()

