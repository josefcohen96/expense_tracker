from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ...db import get_db_conn
from ...services.uploads import sniff_mime as _sniff_mime

router = APIRouter(prefix="/api/wedding", tags=["wedding"])


# ─── Vendor File Attachments ─────────────────────────────────────────────────

# Directory for uploaded vendor files: app/uploads/vendor_files/
_UPLOADS_DIR = Path(__file__).resolve().parents[4] / "uploads" / "vendor_files"
_ALLOWED_MIME = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp"}
_ALLOWED_EXT  = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp"}
_MAX_SIZE_MB  = 15

@router.get("/vendors/{vendor_id}/files")
async def list_vendor_files(vendor_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rows = db_conn.execute(
        "SELECT * FROM vendor_files WHERE vendor_id=? ORDER BY uploaded_at DESC",
        (vendor_id,)
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/vendors/{vendor_id}/files", status_code=201)
async def upload_vendor_file(
    vendor_id: int,
    file: UploadFile = File(...),
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    if not db_conn.execute("SELECT 1 FROM wedding_vendors WHERE id=?", (vendor_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Validate extension
    orig_name = file.filename or "file"
    ext = Path(orig_name).suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="סוג קובץ לא נתמך. מותר: PDF, JPG, PNG, GIF, WEBP")

    # Read content and check size
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="הקובץ ריק")
    size_mb = len(content) / (1024 * 1024)
    if size_mb > _MAX_SIZE_MB:
        raise HTTPException(status_code=400, detail=f"הקובץ גדול מדי (מקסימום {_MAX_SIZE_MB}MB)")

    # Determine mime type from extension
    mime_map = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    declared_mime = mime_map.get(ext, "application/octet-stream")

    # Verify magic bytes match the declared extension — defense against renamed payloads
    detected_mime = _sniff_mime(content)
    if detected_mime is None or detected_mime != declared_mime:
        raise HTTPException(
            status_code=400,
            detail="תוכן הקובץ אינו תואם לסיומת. ודא שהקובץ הוא PDF/תמונה אמיתי.",
        )

    # Store file under a UUID name so original_name can't influence the path
    stored_name = f"{uuid.uuid4().hex}{ext}"
    vendor_dir = _UPLOADS_DIR / str(vendor_id)
    vendor_dir.mkdir(parents=True, exist_ok=True)
    (vendor_dir / stored_name).write_bytes(content)

    # Save metadata (truncate display name to avoid pathological lengths)
    safe_orig = orig_name[:255]
    cur = db_conn.execute(
        "INSERT INTO vendor_files (vendor_id, original_name, stored_name, file_size, mime_type) VALUES (?,?,?,?,?)",
        (vendor_id, safe_orig, stored_name, len(content), declared_mime),
    )
    db_conn.commit()
    row = db_conn.execute("SELECT * FROM vendor_files WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.get("/files/{file_id}")
async def get_vendor_file(file_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    row = db_conn.execute("SELECT * FROM vendor_files WHERE id=?", (file_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    file_path = (_UPLOADS_DIR / str(row["vendor_id"]) / row["stored_name"]).resolve()
    # Guard against path-traversal: stored_name should be UUID-only, but verify.
    try:
        file_path.relative_to(_UPLOADS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    # Use inline disposition so the browser (including iOS Safari) renders the file
    # instead of prompting a download. All allowed types (PDF, images) display natively.
    mime = row["mime_type"]
    encoded_name = quote(row["original_name"], safe="")
    disposition = f"inline; filename=\"{row['original_name']}\"; filename*=UTF-8''{encoded_name}"
    return FileResponse(
        path=str(file_path),
        media_type=mime,
        headers={"Content-Disposition": disposition},
    )


@router.delete("/files/{file_id}", status_code=204)
async def delete_vendor_file(file_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    row = db_conn.execute("SELECT * FROM vendor_files WHERE id=?", (file_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    file_path = _UPLOADS_DIR / str(row["vendor_id"]) / row["stored_name"]
    if file_path.exists():
        file_path.unlink()
    db_conn.execute("DELETE FROM vendor_files WHERE id=?", (file_id,))
    db_conn.commit()
