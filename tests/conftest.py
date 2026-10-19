import importlib
import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path for imports like 'app.backend.app.db'
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def temp_db_path(tmp_path_factory) -> Path:
    """A fresh, empty database file for the whole test session.

    The schema and the seeded defaults (categories, users, accounts) are
    created by ``initialise_database()`` in ``app_client``. The suite never
    reads the developer's real ``app/backend/data/budget.db``, so a test's
    result cannot depend on personal data, and CI behaves exactly like a
    local run.
    """
    return tmp_path_factory.mktemp("db") / "budget_test.sqlite3"


@pytest.fixture(scope="session")
def app_client(temp_db_path):
    os.environ["BUDGET_DB_PATH"] = str(temp_db_path)
    os.environ["AUTH_ENABLED"] = "0"
    # TestClient sends "Host: testserver", which the Host-header check rejects
    # unless it is listed. Only a default, so a caller can still override it.
    os.environ.setdefault("ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")
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
