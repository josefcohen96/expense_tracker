import os
import shutil
from pathlib import Path
import importlib
import sys
import pytest

# Ensure project root is on sys.path for imports like 'app.backend.app.db'
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def temp_db_path(tmp_path_factory) -> Path:
    project_root = Path(__file__).resolve().parents[1]
    default_db = project_root / "app" / "backend" / "app" / "data" / "budget.db"
    assert default_db.exists(), f"Default DB not found at {default_db}"
    tmp_dir = tmp_path_factory.mktemp("db")
    tmp_db = tmp_dir / "budget_test_copy.sqlite3"
    shutil.copy2(default_db, tmp_db)
    return tmp_db


@pytest.fixture(scope="session")
def app_client(temp_db_path):
    os.environ["BUDGET_DB_PATH"] = str(temp_db_path)
    # Ensure modules read the env var at import time and initialize schema/data
    import app.backend.app.db as db_module
    importlib.reload(db_module)
    # Make sure DB_PATH points to the temp path and initialize tables/default data
    db_module.initialise_database()

    from fastapi.testclient import TestClient
    import app.backend.app.main as main_app

    client = TestClient(main_app.app)
    return client


@pytest.fixture()
def db_conn(app_client, temp_db_path):
    import sqlite3
    conn = sqlite3.connect(str(temp_db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


