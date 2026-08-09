"""Per-user module access rules.

The app hosts several independent modules (finances, wedding, workouts,
renovation) behind a single login. Not every user may see every module:

- YOSEF   — everything.
- KARINA  — everything except the renovation module.
- TSAHALA — the renovation module only (she never sees the family finances).

Keeping the rules here means both the auth middleware (enforcement) and the
templates (hiding links the user cannot follow) read from one source of truth.
"""
from __future__ import annotations

from typing import Any, Optional

# Canonical usernames, always compared upper-cased.
USER_YOSEF = "YOSEF"
USER_KARINA = "KARINA"
USER_TSAHALA = "TSAHALA"

ALL_USERNAMES = (USER_YOSEF, USER_KARINA, USER_TSAHALA)

# Who may open the renovation module at all.
RENOVATION_USERS = frozenset({USER_YOSEF, USER_TSAHALA})

# Who may change renovation data (the rest get a read-only view).
RENOVATION_EDITORS = frozenset({USER_YOSEF, USER_TSAHALA})

# Users restricted to the renovation module and nothing else.
RENOVATION_ONLY_USERS = frozenset({USER_TSAHALA})

# Path prefixes that belong to the renovation module.
RENOVATION_PREFIXES = ("/renovation", "/api/renovation")

# Paths every logged-in user needs regardless of which modules they own.
_SHARED_PREFIXES = ("/static/", "/login", "/logout")
_SHARED_EXACT = ("/", "/health", "/sw.js", "/offline")


def normalise_username(user: Any) -> str:
    """Extract an upper-cased username from a session dict, string, or None."""
    if isinstance(user, dict):
        user = user.get("username")
    return str(user or "").strip().upper()


def is_renovation_path(path: str) -> bool:
    return path.startswith(RENOVATION_PREFIXES)


def can_access_renovation(user: Any) -> bool:
    return normalise_username(user) in RENOVATION_USERS


def can_edit_renovation(user: Any) -> bool:
    return normalise_username(user) in RENOVATION_EDITORS


def can_access_path(user: Any, path: str) -> bool:
    """Return True if this user is allowed to reach `path`.

    Unknown usernames are treated like a normal full-access user — the login
    step already decided they are legitimate; this layer only carves modules
    out of that access.
    """
    username = normalise_username(user)
    renovation = is_renovation_path(path)

    if username in RENOVATION_ONLY_USERS:
        # Whitelist: anything that is not renovation or shared plumbing is denied.
        return renovation or path in _SHARED_EXACT or path.startswith(_SHARED_PREFIXES)

    if renovation:
        return username in RENOVATION_USERS

    return True


def home_path_for(user: Any) -> str:
    """The landing page a user should be sent to after login / from '/'."""
    if normalise_username(user) in RENOVATION_ONLY_USERS:
        return "/renovation"
    return "/finances"


def password_env_var(username: str) -> Optional[str]:
    """Environment variable holding the password for a known username."""
    key = normalise_username(username)
    if key in ALL_USERNAMES:
        return f"USER_PASSWORD_{key}"
    return None
