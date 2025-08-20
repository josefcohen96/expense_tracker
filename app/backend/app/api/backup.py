from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from .. import schemas
from ..services.backup_service import create_backup_file, list_backup_files, restore_from_file  # <- שירותים  :contentReference[oaicite:5]{index=5}


router = APIRouter(prefix="/api/backup", tags=["backup"])

@router.post("/excel")
async def api_backup_create() -> JSONResponse:
    path = create_backup_file()
    return JSONResponse(content={"file": path.name})

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
