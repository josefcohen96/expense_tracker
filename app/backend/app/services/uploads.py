"""Shared rules for files users upload from their phone.

Two modules accept uploads — wedding vendor documents and renovation journal
photos — and both have to reject the same things: unknown extensions, empty or
oversized files, and content whose magic bytes disagree with its extension (a
renamed payload). Keeping the checks here means neither module can drift into
being the lenient one.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

# Magic bytes for file-type sniffing (defense-in-depth alongside the extension
# check — an attacker controls the filename, not the first bytes of the file).
MAGIC_BYTES = {
    "application/pdf": [b"%PDF-"],
    "image/jpeg":      [b"\xff\xd8\xff"],
    "image/png":       [b"\x89PNG\r\n\x1a\n"],
    "image/gif":       [b"GIF87a", b"GIF89a"],
    "image/webp":      [b"RIFF"],  # also has "WEBP" at offset 8
}

# Image formats a phone camera or gallery can realistically produce.
IMAGE_MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


class UploadRejected(ValueError):
    """An upload failed validation. The message is Hebrew and user-facing."""


def sniff_mime(content: bytes) -> Optional[str]:
    """Best-effort MIME type from the file's leading bytes, or None."""
    if not content:
        return None
    for mime, signatures in MAGIC_BYTES.items():
        for sig in signatures:
            if content.startswith(sig):
                # Extra check for WebP: "WEBP" marker at offset 8
                if mime == "image/webp":
                    if len(content) >= 12 and content[8:12] == b"WEBP":
                        return mime
                else:
                    return mime
    return None


def validate_image(content: bytes, filename: Optional[str], max_mb: int) -> tuple[str, str]:
    """Check an uploaded image and return its ``(extension, mime)``.

    Raises :class:`UploadRejected` with a message meant to be shown as-is.
    """
    ext = Path(filename or "image").suffix.lower()
    if ext not in IMAGE_MIME_BY_EXT:
        raise UploadRejected("סוג קובץ לא נתמך. אפשר להעלות JPG, PNG, WEBP או GIF.")
    if not content:
        raise UploadRejected("הקובץ ריק")
    if len(content) > max_mb * 1024 * 1024:
        raise UploadRejected(f"התמונה גדולה מדי (מקסימום {max_mb}MB)")

    declared = IMAGE_MIME_BY_EXT[ext]
    if sniff_mime(content) != declared:
        raise UploadRejected("תוכן הקובץ אינו תואם לסיומת. ודאו שזו תמונה אמיתית.")
    return ext, declared


def random_stored_name(ext: str) -> str:
    """A UUID filename, so the name a user chose never reaches the filesystem."""
    return f"{uuid.uuid4().hex}{ext}"
