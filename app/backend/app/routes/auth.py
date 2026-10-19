"""Login / logout pages and the /login rate limit."""
from __future__ import annotations

import hmac
import logging
import os
import time
from collections import deque
from datetime import datetime
from threading import Lock

from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import URLSafeSerializer

from ..auth import public
from ..services.access import home_path_for, password_env_var
from ..templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pages"])


# --- /login rate limiting (per client IP, in-memory) ---
# In-memory means rate limits reset on process restart, which is fine for this
# single-instance app with two known users. If we ever move to multi-instance,
# this needs a shared store (Redis).
_LOGIN_WINDOW_SECONDS = 300  # 5-minute sliding window
_LOGIN_MAX_ATTEMPTS = 8      # attempts allowed in that window
_login_attempts: dict[str, deque[float]] = {}
_login_attempts_lock = Lock()


def _client_ip(request: Request) -> str:
    """Resolve the client IP behind Railway/proxy via X-Forwarded-For."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    real = request.headers.get("x-real-ip", "").strip()
    if real:
        return real
    return request.client.host if request.client else "unknown"


def _check_login_rate_limit(ip: str) -> bool:
    """Return True if the attempt is allowed; False if the IP is currently blocked."""
    now = time.monotonic()
    cutoff = now - _LOGIN_WINDOW_SECONDS
    with _login_attempts_lock:
        attempts = _login_attempts.get(ip)
        if attempts is None:
            attempts = deque()
            _login_attempts[ip] = attempts
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
            return False
        attempts.append(now)
        return True


def _get_session_secret() -> str:
    """Read SESSION_SECRET_KEY at request time. App startup already validated it."""
    secret = os.environ.get("SESSION_SECRET_KEY")
    if not secret:
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return "pytest-only-not-for-production"
        raise RuntimeError("SESSION_SECRET_KEY environment variable is missing")
    return secret


@router.get("/login", response_class=HTMLResponse)
@public
async def login_page(request: Request) -> HTMLResponse:
    error = request.query_params.get("error")
    try:
        next_q = request.query_params.get("next")
        has_session_user = False
        
        # Check if user is actually authenticated
        if hasattr(request, 'session') and request.session:
            user_obj = request.session.get("user")
            has_session_user = bool(user_obj)
            
        logger.info("Login page served", extra={
            "next": next_q,
            "has_session_user": has_session_user,
        })
        
        # If user is already authenticated, redirect to dashboard
        if has_session_user:
            logger.info("User already authenticated, redirecting to dashboard", extra={
                "username": user_obj.get("username") if isinstance(user_obj, dict) else None,
            })
            return RedirectResponse(url=home_path_for(user_obj), status_code=status.HTTP_302_FOUND)

    except Exception:
        logger.exception("Failed logging login_page context")
        
    return templates.TemplateResponse(
        request,
        "pages/login.html",
        {
            "request": request,
            "error": error,
            "show_sidebar": False,
        },
    )


@router.post("/login", response_class=HTMLResponse, response_model=None)
@public
async def login_post(request: Request):
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = (form.get("password") or "").strip()

    # Rate limit BEFORE doing any credential check or expensive work.
    client_ip = _client_ip(request)
    if not _check_login_rate_limit(client_ip):
        logger.warning("LOGIN rate-limited", extra={"ip": client_ip, "username": username})
        return templates.TemplateResponse(
            request,
            "pages/login.html",
            {
                "request": request,
                "error": "יותר מדי ניסיונות התחברות. נסה שוב בעוד מספר דקות.",
                "show_sidebar": False,
            },
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    logger.info("LOGIN attempt", extra={
        "username": username,
        "ip": client_ip,
        "timestamp": datetime.now().isoformat(),
    })

    # Credentials must come from environment. A missing env var => 500 instead of
    # falling back to a hardcoded password — better to fail loud than to ship the
    # default password publicly via the repo. Only the attempted user's variable
    # is required, so adding a new user never locks out the existing ones.
    # case-insensitive username match
    user_key = username.upper()
    env_var = password_env_var(user_key)
    expected_pw = os.environ.get(env_var) if env_var else None
    if env_var and not expected_pw:
        logger.error("LOGIN misconfigured: password env var is missing", extra={"env_var": env_var})
        return templates.TemplateResponse(
            request,
            "pages/login.html",
            {
                "request": request,
                "error": "שגיאת תצורה בשרת. פנה למנהל המערכת.",
                "show_sidebar": False,
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    # Compare as bytes: compare_digest rejects non-ASCII str, and a password
    # with Hebrew or accented characters would otherwise raise instead of just
    # failing the check.
    if expected_pw and hmac.compare_digest(password.encode("utf-8"), expected_pw.encode("utf-8")):
        logger.info("LOGIN success", extra={"username": user_key, "ip": client_ip})

        try:
            if not hasattr(request, 'session'):
                logger.error("No session object available on request")
                raise Exception("No session object available")
            try:
                request.session.clear()
            except Exception as clear_error:
                logger.warning(f"Failed to clear session: {clear_error}")
            request.session["user"] = {"username": user_key}
        except Exception as e:
            logger.error("Failed to set session", extra={
                "username": user_key,
                "error": str(e),
                "error_type": type(e).__name__,
            })

        response = RedirectResponse(url=home_path_for(user_key), status_code=status.HTTP_303_SEE_OTHER)

        # Also set a signed fallback cookie for auth in case session cookie is blocked by the platform
        try:
            serializer = URLSafeSerializer(_get_session_secret(), salt="auth-user")
            token = serializer.dumps({"u": user_key})
            # Mirror session cookie attributes
            is_production = os.environ.get("RAILWAY_ENVIRONMENT") is not None or os.environ.get("ENVIRONMENT") == "production"
            secure = True if is_production else False
            # Starlette Response.set_cookie uses samesite values: 'lax' | 'strict' | 'none'
            response.set_cookie(
                key="auth_user",
                value=token,
                max_age=86400,
                httponly=True,
                secure=secure,
                samesite="none" if secure else "lax",
                path="/",
            )
        except Exception as cookie_err:
            logger.warning("Failed to set auth cookie", extra={"error": str(cookie_err)})

        return response

    # invalid credentials
    logger.info("LOGIN failed", extra={"username": username, "ip": client_ip})
    return templates.TemplateResponse(
        request,
        "pages/login.html",
        {
            "request": request,
            "error": "שם משתמש או סיסמה שגויים",
            "show_sidebar": False,
        },
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    user_obj = request.session.get('user')
    logger.info(f"LOGOUT user={user_obj}")
    
    try:
        # Clear session data
        if hasattr(request, 'session') and request.session:
            request.session.clear()
            
        logger.info("Session cleared successfully", extra={
            "username": user_obj.get("username") if isinstance(user_obj, dict) else None,
            "timestamp": datetime.now().isoformat()
        })
        # Clear fallback cookie
        try:
            pass
            # Use a temporary response to set delete cookie directive; actual redirect below will be returned
            # We'll attach delete cookie on the final RedirectResponse instead
        except Exception:
            pass
    except Exception as e:
        logger.error("Failed to clear session", extra={
            "error": str(e),
            "error_type": type(e).__name__,
            "timestamp": datetime.now().isoformat()
        })
    
    resp = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    # Ensure fallback cookie is removed
    try:
        resp.delete_cookie("auth_user", path="/")
    except Exception:
        pass
    return resp
