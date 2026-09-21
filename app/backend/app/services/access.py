"""Per-user module access rules.

The app hosts several independent modules (finances, wedding, workouts,
renovation) behind a single login. Not every user may see every module:

- YOSEF   — everything.
- KARINA  — everything except the renovation module.
- TSAHALA — the renovation module only (she never sees the family finances).
- YONATAN — the workouts module only (his own arena, nothing of the household).

Keeping the rules here means both the auth middleware (enforcement) and the
templates (hiding links the user cannot follow) read from one source of truth.
"""
from __future__ import annotations

from typing import Any, Optional

# Canonical usernames, always compared upper-cased.
USER_YOSEF = "YOSEF"
USER_KARINA = "KARINA"
USER_TSAHALA = "TSAHALA"
USER_YONATAN = "YONATAN"

ALL_USERNAMES = (USER_YOSEF, USER_KARINA, USER_TSAHALA, USER_YONATAN)

# Hebrew display names, keyed by canonical username.
USER_DISPLAY_NAMES = {
    USER_YOSEF: "יוסף",
    USER_TSAHALA: "צהלה",
    USER_KARINA: "קארינה",
    USER_YONATAN: "יונתן",
}

# Who may open the renovation module at all.
RENOVATION_USERS = frozenset({USER_YOSEF, USER_TSAHALA})

# Who may change renovation data (the rest get a read-only view).
RENOVATION_EDITORS = frozenset({USER_YOSEF, USER_TSAHALA})

# Path prefixes that belong to each carved-out module.
RENOVATION_PREFIXES = ("/renovation", "/api/renovation")
WORKOUTS_PREFIXES = ("/workouts", "/api/workouts")

# Users restricted to a single module: username -> (its path prefixes, its home page).
# Such a user is whitelisted to that module plus the shared plumbing below.
MODULE_ONLY_USERS = {
    USER_TSAHALA: (RENOVATION_PREFIXES, "/renovation"),
    USER_YONATAN: (WORKOUTS_PREFIXES, "/workouts"),
}

# Users restricted to the renovation module and nothing else.
RENOVATION_ONLY_USERS = frozenset(
    user for user, (prefixes, _home) in MODULE_ONLY_USERS.items() if prefixes == RENOVATION_PREFIXES
)

# Users restricted to the workouts module and nothing else.
WORKOUTS_ONLY_USERS = frozenset(
    user for user, (prefixes, _home) in MODULE_ONLY_USERS.items() if prefixes == WORKOUTS_PREFIXES
)

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


def is_workouts_path(path: str) -> bool:
    return path.startswith(WORKOUTS_PREFIXES)


def is_module_only_user(user: Any) -> bool:
    """True for a login that owns a single module (Tsahala, Yonatan)."""
    return normalise_username(user) in MODULE_ONLY_USERS


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

    restriction = MODULE_ONLY_USERS.get(username)
    if restriction:
        # Whitelist: anything that is not the user's module or shared plumbing is denied.
        prefixes, _home = restriction
        return path.startswith(prefixes) or path in _SHARED_EXACT or path.startswith(_SHARED_PREFIXES)

    if is_renovation_path(path):
        return username in RENOVATION_USERS

    return True


def home_path_for(user: Any) -> str:
    """The landing page a user should be sent to after login / from '/'."""
    restriction = MODULE_ONLY_USERS.get(normalise_username(user))
    if restriction:
        return restriction[1]
    # The היום screen; on desktop it forwards to /finances.
    return "/"


def display_name(user: Any) -> str:
    """Hebrew display name for a session user, username or users.name value."""
    key = normalise_username(user)
    return USER_DISPLAY_NAMES.get(key, key.title())


def password_env_var(username: str) -> Optional[str]:
    """Environment variable holding the password for a known username."""
    key = normalise_username(username)
    if key in ALL_USERNAMES:
        return f"USER_PASSWORD_{key}"
    return None
