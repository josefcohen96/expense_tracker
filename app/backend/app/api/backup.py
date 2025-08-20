from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from pathlib import Path
import zipfile
import logging
import shutil
import os
import sys
import traceback
import inspect
import json

from .. import schemas
from ..services.backup_service import list_backup_files, restore_from_file  # <- שירותים  :contentReference[oaicite:5]{index=5}

router = APIRouter(prefix="/api/backup", tags=["backup"])

ROOT_DIR = Path(__file__).resolve().parents[2]  # .../expense_tracker/app
BACKUP_DIR = ROOT_DIR / "backups"
EXCEL_DIR = BACKUP_DIR / "excel"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
EXCEL_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

# Debug: indicate module import (helps detect circular import chain)
print("DEBUG: imported api.backup module", __name__, "pid:", os.getpid())
logger.debug("DEBUG: imported api.backup module %s pid:%s", __name__, os.getpid())
print("DEBUG: sys.modules keys containing 'backup':", [k for k in sys.modules.keys() if 'backup' in k])
logger.debug("sys.modules keys containing 'backup': %s", [k for k in sys.modules.keys() if 'backup' in k])

def _collect_import_debug_info():
    """
    Collect detailed sys.modules info and current stack for debugging circular imports.
    Returns a dict that can be logged or included in responses.
    """
    try:
        mods = []
        for name, mod in list(sys.modules.items()):
            if not mod:
                continue
            if any(k in name for k in ("backup", "backup_service", "services")):
                try:
                    mods.append({
                        "module": name,
                        "file": getattr(mod, "__file__", None),
                        "package": getattr(mod, "__package__", None),
                        "has_attrs": len(getattr(mod, "__dict__", {})),
                        "sample_attrs": list(getattr(mod, "__dict__", {}).keys())[:20],
                    })
                except Exception as e:
                    mods.append({"module": name, "error": str(e)})
        stack = "".join(traceback.format_stack(limit=100))
        return {"modules": mods, "stack": stack}
    except Exception:
        return {"error": "failed to collect import debug info", "trace": traceback.format_exc()}

# change signature to accept optional db_conn
def create_backup(db_conn=None) -> Path:
    """
    Wrapper used by pages route: create dated folder + monthly excel files.
    Accepts optional db_conn (sqlite3.Connection) for the query.
    """
    print("DEBUG: create_backup called, db_conn:", type(db_conn))
    logger.debug("create_backup called, db_conn=%s", type(db_conn))
    # lazy import to avoid circular import recursion, with diagnostics
    try:
        from ..services.backup_service import create_backup_file
    except RecursionError as rec:
        tb = traceback.format_exc()
        debug = _collect_import_debug_info()
        print("DEBUG: RecursionError importing create_backup_file:\n", tb)
        print("DEBUG: import debug info:", json.dumps(debug, default=str)[:4000])
        logger.exception("RecursionError importing create_backup_file")
        # include debug info in the raised exception so it appears in logs/responses
        raise RuntimeError("RecursionError importing create_backup_file; debug: " + json.dumps(debug, default=str)) from rec
    except Exception as exc:
        tb = traceback.format_exc()
        debug = _collect_import_debug_info()
        print("DEBUG: Exception importing create_backup_file:\n", tb)
        print("DEBUG: import debug info:", json.dumps(debug, default=str)[:4000])
        logger.exception("Exception importing create_backup_file")
        raise RuntimeError("Exception importing create_backup_file; debug: " + json.dumps(debug, default=str)) from exc
    try:
        print("DEBUG: calling create_backup_file()")
        path = create_backup_file(db_conn)
        print("DEBUG: create_backup_file returned:", path)
        logger.debug("create_backup_file returned: %s", path)
        return path
    except Exception:
        tb = traceback.format_exc()
        print("DEBUG: exception in create_backup:\n", tb)
        logger.exception("Exception in create_backup")
        raise

def restore_from_backup(path: Path):
    """
    Wrapper used by pages route to restore a given backup path (dir or zip).
    """
    return restore_from_file(path)

@router.post("/excel")
async def api_backup_create() -> JSONResponse:
    # lazy import to avoid circular import
    try:
        from ..services.backup_service import create_backup_file
    except RecursionError:
        tb = traceback.format_exc()
        debug = _collect_import_debug_info()
        print("DEBUG: RecursionError importing create_backup_file in api_backup_create:\n", tb)
        logger.exception("RecursionError importing create_backup_file in api_backup_create")
        return JSONResponse(status_code=500, content={"error": "RecursionError importing create_backup_file", "debug": debug})
    except Exception as exc:
        tb = traceback.format_exc()
        debug = _collect_import_debug_info()
        print("DEBUG: Exception importing create_backup_file in api_backup_create:\n", tb)
        logger.exception("Exception importing create_backup_file in api_backup_create")
        return JSONResponse(status_code=500, content={"error": str(exc), "trace": tb, "debug": debug})

    print("DEBUG: api_backup_create called")
    logger.debug("api_backup_create called")
    try:
        path = create_backup_file()
        print("DEBUG: api_backup_create success, path:", path)
        logger.debug("api_backup_create success: %s", path)
        return JSONResponse(content={"file": path.name})
    except Exception as exc:
        tb = traceback.format_exc()
        print("DEBUG: api_backup_create exception:\n", tb)
        logger.exception("api_backup_create failed")
        # include traceback for debugging (remove in production)
        raise HTTPException(status_code=500, detail={"error": str(exc), "trace": tb})

@router.get("/list", response_model=schemas.BackupList)
async def api_backup_list() -> schemas.BackupList:
    backups = list_backup_files()
    items = [schemas.BackupItem(**b) for b in backups]
    return schemas.BackupList(backups=items)

@router.post("/restore")
async def api_backup_restore(request: Request) -> JSONResponse:
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="No data provided")
    tmp_path = BACKUP_DIR / f"api_restore_{datetime.now().timestamp()}.xlsx"
    with open(tmp_path, "wb") as f:
        f.write(data)
    try:
        counts = restore_from_file(tmp_path)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc))
    tmp_path.unlink(missing_ok=True)
    return JSONResponse(content={"restored": True, "counts": counts})

@router.post("/backup/create")
async def backup_create():
    try:
        # lazy import to avoid circular import
        try:
            from ..services.backup_service import create_backup_file
        except RecursionError:
            tb = traceback.format_exc()
            debug = _collect_import_debug_info()
            print("DEBUG: RecursionError importing create_backup_file in backup_create:\n", tb)
            print("DEBUG: import debug info:", json.dumps(debug, default=str)[:4000])
            logger.exception("RecursionError importing create_backup_file in backup_create")
            return JSONResponse(status_code=500, content={"detail": "RecursionError importing create_backup_file", "debug": debug})
        except Exception as exc:
            tb = traceback.format_exc()
            debug = _collect_import_debug_info()
            print("DEBUG: Exception importing create_backup_file in backup_create:\n", tb)
            print("DEBUG: import debug info:", json.dumps(debug, default=str)[:4000])
            logger.exception("Exception importing create_backup_file in backup_create")
            return JSONResponse(status_code=500, content={"detail": "Failed importing create_backup_file", "error": str(exc), "trace": tb, "debug": debug})

        print("DEBUG: backup_create entry")
        logger.debug("backup_create entry")
        path = create_backup_file()
        print("DEBUG: backup_create created:", path)
        logger.info("Created backup: %s", path)
        # redirect back to the UI that lists backups
        return RedirectResponse(url="/backup", status_code=303)
    except Exception as exc:
        tb = traceback.format_exc()
        debug = _collect_import_debug_info()
        print("DEBUG: backup_create exception:\n", tb)
        print("DEBUG: import debug info:", json.dumps(debug, default=str)[:4000])
        logger.exception("Unhandled error in /backup/create")
        return JSONResponse(status_code=500, content={"detail": "Failed to create backup", "error": str(exc), "trace": tb, "debug": debug})

@router.get("/backup/download/{file_name}")
async def backup_download(file_name: str):
    safe_name = Path(file_name).name
    path = BACKUP_DIR / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(str(path), filename=safe_name)


@router.get("/backup/restore/{file_name}")
async def backup_restore(file_name: str):
    safe_name = Path(file_name).name
    path = BACKUP_DIR / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Backup not found")
    try:
        # extract into EXCEL_DIR (overwrite existing files)
        with zipfile.ZipFile(path, "r") as zf:
            # extract to a temporary dir then move files to avoid partial overwrite
            tmp_dir = BACKUP_DIR / f".restore_tmp_{datetime.utcnow().timestamp()}"
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)
            tmp_dir.mkdir(parents=True, exist_ok=True)
            zf.extractall(tmp_dir)
            for src in tmp_dir.iterdir():
                dst = EXCEL_DIR / src.name
                # move/replace
                if dst.exists():
                    dst.unlink()
                shutil.move(str(src), str(dst))
            shutil.rmtree(tmp_dir)
        logger.info("Restored backup %s into %s", safe_name, EXCEL_DIR)
        return RedirectResponse(url="/backup", status_code=303)
    except Exception:
        tb = traceback.format_exc()
        print("DEBUG: backup_restore exception:\n", tb)
        logger.exception("Failed to restore backup %s", safe_name)
        raise HTTPException(status_code=500, detail="Failed to restore backup")
