"""Regression test for the auth/session middleware ordering bug.

AuthMiddleware reads request.session to find the logged-in user. If
SessionMiddleware is registered (via app.add_middleware) AFTER AuthMiddleware,
Starlette puts Auth on the outside of the stack, so Auth's dispatch runs
before Session has decoded the cookie into request.session — every
request.session access then fails.

That failure mode causes a real redirect loop: once the signed `auth_user`
fallback cookie (24h, never renewed) expires while the `session` cookie is
still valid, AuthMiddleware can't read the session (broken) and the
`auth_user` cookie is gone, so it sends the browser to /login. But /login
reads a still-valid `session` cookie directly (no fallback-cookie check) and
redirects straight back to the protected page. Repeat forever.

This test runs with auth genuinely enabled (unlike the rest of the suite,
which sets AUTH_ENABLED=0) so it exercises the real AuthMiddleware/session
interaction, and simulates the `auth_user` cookie expiring while the session
cookie survives.
"""
import importlib
import os
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def authed_client(tmp_path_factory):
    """A TestClient with real auth enabled and its own DB, independent of the
    session-scoped `app_client` fixture (which runs with AUTH_ENABLED=0)."""
    saved_env = {
        k: os.environ.get(k)
        for k in (
            "BUDGET_DB_PATH",
            "AUTH_ENABLED",
            "USER_PASSWORD_YOSEF",
            "USER_PASSWORD_KARINA",
            "SESSION_SECRET_KEY",
            "ALLOWED_HOSTS",
        )
    }

    tmp_db = tmp_path_factory.mktemp("auth_db") / "budget_auth_test.sqlite3"
    os.environ["BUDGET_DB_PATH"] = str(tmp_db)
    os.environ["AUTH_ENABLED"] = "1"
    os.environ["USER_PASSWORD_YOSEF"] = "test-password-yosef"
    os.environ["USER_PASSWORD_KARINA"] = "test-password-karina"
    os.environ.setdefault("SESSION_SECRET_KEY", "pytest-only-not-for-production")
    os.environ.setdefault("ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")

    # Force a fresh import of the app so it picks up AUTH_ENABLED=1 and rebuilds
    # its middleware stack (main.py reads these env vars at import time).
    for mod_name in list(sys.modules):
        if mod_name.startswith("app.backend.app"):
            del sys.modules[mod_name]

    import app.backend.app.db as db_module
    importlib.reload(db_module)
    db_module.initialise_database()

    import app.backend.app.main as main_module

    from fastapi.testclient import TestClient
    client = TestClient(main_module.app)
    try:
        yield client
    finally:
        client.close()
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for mod_name in list(sys.modules):
            if mod_name.startswith("app.backend.app"):
                del sys.modules[mod_name]


def test_login_sets_session_and_auth_cookie(authed_client):
    resp = authed_client.post(
        "/login",
        data={"username": "yosef", "password": "test-password-yosef"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "session" in authed_client.cookies
    assert "auth_user" in authed_client.cookies


def test_protected_page_works_after_login(authed_client):
    authed_client.post(
        "/login",
        data={"username": "yosef", "password": "test-password-yosef"},
        follow_redirects=False,
    )
    resp = authed_client.get("/finances", follow_redirects=False)
    assert resp.status_code == 200


def test_no_redirect_loop_when_auth_user_cookie_expires(authed_client):
    """Reproduces the bug: log in, then drop only the auth_user fallback
    cookie (simulating its 24h expiry) while the session cookie survives.
    AuthMiddleware must still authenticate via request.session — it must not
    redirect to /login (which would then bounce back, causing the loop the
    user hit in production)."""
    authed_client.post(
        "/login",
        data={"username": "yosef", "password": "test-password-yosef"},
        follow_redirects=False,
    )
    assert "session" in authed_client.cookies

    authed_client.cookies.delete("auth_user")

    resp = authed_client.get("/finances", follow_redirects=False)
    assert resp.status_code == 200, (
        "AuthMiddleware failed to authenticate via request.session once the "
        "auth_user cookie was gone — this is the redirect-loop bug "
        "(SessionMiddleware must run before AuthMiddleware)."
    )
