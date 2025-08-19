from __future__ import annotations

import os
from pathlib import Path


def _project_root() -> Path:
    # core/config.py -> app/core -> app -> backend -> project root
    return Path(__file__).resolve().parents[3]


PROJECT_ROOT: Path = _project_root()
BACKEND_DIR: Path = PROJECT_ROOT / "backend"

# Allow overriding frontend directory via environment variable
FRONTEND_DIR: Path = Path(os.getenv("FRONTEND_DIR", str(PROJECT_ROOT / "frontend")))
TEMPLATES_DIR: Path = FRONTEND_DIR / "templates"
STATIC_DIR: Path = FRONTEND_DIR / "static"

# Data directory (SQLite DB, backups)
DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(BACKEND_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

