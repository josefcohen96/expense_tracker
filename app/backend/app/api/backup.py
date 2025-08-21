"""
Backup API endpoints for database backup and restore functionality.
"""

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
import json

from .. import schemas
from ..services.backup_service import list_backup_files, restore_from_file

router = APIRouter(prefix="/api/backup", tags=["backup"])

ROOT_DIR = Path(__file__).resolve().parents[2]  # .../expense_tracker/app
BACKUP_DIR = ROOT_DIR / "backups"
EXCEL_DIR = BACKUP_DIR / "excel"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
EXCEL_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

def create_backup(db_conn=None) -> Path:
    """
    Create a new backup file.
    Accepts optional db_conn (sqlite3.Connection) for the query.
    """
    logger.debug("create_backup called, db_conn=%s", type(db_conn))
    
    try:
        from ..services.backup_service import create_backup_file
        path = create_backup_file(db_conn)
        logger.debug("create_backup_file returned: %s", path)
        return path
    except Exception as exc:
        logger.exception("Exception in create_backup")
        raise

def restore_from_backup(path: Path):
    """
    Restore database from a given backup path (dir or zip).
    """
    try:
        restore_from_file(path)
        return {"message": "Backup restored successfully"}
    except Exception as exc:
        logger.exception("Exception in restore_from_backup")
        raise HTTPException(status_code=500, detail=str(exc))

@router.get("", response_model=schemas.BackupList)
async def list_backups() -> schemas.BackupList:
    """List all available backup files."""
    try:
        backup_files = list_backup_files()
        return schemas.BackupList(backups=backup_files)
    except Exception as exc:
        logger.exception("Exception listing backups")
        raise HTTPException(status_code=500, detail=str(exc))

@router.post("/create")
async def create_new_backup() -> JSONResponse:
    """Create a new backup file."""
    try:
        path = create_backup()
        return JSONResponse({
            "message": "Backup created successfully",
            "file": path.name,
            "size": path.stat().st_size if path.exists() else 0
        })
    except Exception as exc:
        logger.exception("Exception creating backup")
        raise HTTPException(status_code=500, detail=str(exc))

@router.post("/restore/{filename}")
async def restore_backup(filename: str) -> JSONResponse:
    """Restore database from a backup file."""
    try:
        backup_path = BACKUP_DIR / filename
        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="Backup file not found")
        
        result = restore_from_backup(backup_path)
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Exception restoring backup")
        raise HTTPException(status_code=500, detail=str(exc))

@router.delete("/{filename}")
async def delete_backup(filename: str) -> JSONResponse:
    """Delete a backup file."""
    try:
        backup_path = BACKUP_DIR / filename
        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="Backup file not found")
        
        backup_path.unlink()
        return JSONResponse({"message": "Backup deleted successfully"})
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Exception deleting backup")
        raise HTTPException(status_code=500, detail=str(exc))

@router.get("/download/{filename}")
async def download_backup(filename: str):
    """Download a backup file."""
    try:
        backup_path = BACKUP_DIR / filename
        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="Backup file not found")
        
        return FileResponse(
            path=backup_path,
            filename=filename,
            media_type='application/zip'
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Exception downloading backup")
        raise HTTPException(status_code=500, detail=str(exc))
