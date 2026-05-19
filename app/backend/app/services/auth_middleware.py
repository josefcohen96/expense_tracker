from __future__ import annotations

import logging
import os
from typing import Any, Iterable, List, Set, Tuple
from urllib.parse import quote_plus
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from itsdangerous import BadSignature, URLSafeSerializer


class AuthMiddleware(BaseHTTPMiddleware):
    """Auth guard middleware.

    - Allows static assets and service worker.
    - Allows routes marked @public (provided via regex+methods tuples).
    - Requires a logged-in session user for all other routes.
    - For GET: redirects to /login?next=...; for non-GET: redirects to /login.
    """

    def __init__(
        self,
        app: Any,
        public_route_matchers: Iterable[Tuple[Any, Set[str]]],
        auth_enabled: bool = True,
    ) -> None:
        super().__init__(app)
        self.public_route_matchers: List[Tuple[Any, Set[str]]] = list(public_route_matchers)
        self.auth_enabled = auth_enabled
        self.logger = logging.getLogger(__name__)
        # Fallback cookie-based auth (signed).
        # SESSION_SECRET_KEY is validated at app startup in main.py — we just read it here.
        # No hardcoded fallback: a leaked default key would let anyone forge auth cookies.
        secret_key = os.environ.get("SESSION_SECRET_KEY")
        if not secret_key:
            if os.environ.get("PYTEST_CURRENT_TEST"):
                secret_key = "pytest-only-not-for-production"
            else:
                raise RuntimeError("SESSION_SECRET_KEY must be set before AuthMiddleware is initialized")
        self.secret_key = secret_key
        self.serializer = URLSafeSerializer(self.secret_key, salt="auth-user")
        self.cookie_name = "auth_user"

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.auth_enabled:
            return await call_next(request)

        path = request.url.path
        method = (request.method or "GET").upper()

        # Lightweight per-request log. We deliberately do NOT log cookies, headers,
        # or the full session dict — those contain auth tokens that would leak if
        # log files are ever exposed.
        auth_logger = logging.getLogger("app.auth")
        is_production = os.environ.get("RAILWAY_ENVIRONMENT") is not None or os.environ.get("ENVIRONMENT") == "production"
        if not is_production:
            auth_logger.debug(f"Request: {method} {path}")

        # Allow unauthenticated access to static and service worker
        if path.startswith("/static/") or path == "/sw.js":
            return await call_next(request)
        # Always allow health endpoint
        if path == "/health":
            return await call_next(request)

        # Allow @public endpoints
        try:
            for regex, methods in self.public_route_matchers:
                try:
                    if regex.match(path) and (not methods or method in methods):
                        self.logger.debug("AuthMiddleware: public route allowed", extra={
                            "path": path,
                            "method": method,
                        })
                        return await call_next(request)
                except Exception:
                    # Best-effort; ignore a broken matcher
                    continue
        except Exception:
            self.logger.exception("AuthMiddleware: error checking public matchers")

        # Require a session user for everything else
        user_obj = None
        user_in_session = False

        try:
            if hasattr(request, 'session'):
                try:
                    user_obj = request.session.get("user")
                    user_in_session = bool(user_obj)
                except Exception as session_error:
                    self.logger.warning("AuthMiddleware: session access failed", extra={
                        "path": path,
                        "method": method,
                        "session_error_type": type(session_error).__name__,
                    })
        except Exception as e:
            self.logger.warning("AuthMiddleware: session access failed", extra={
                "path": path,
                "method": method,
                "error_type": type(e).__name__,
            })

        # Fallback: if no session user, try signed cookie auth
        if not user_in_session:
            try:
                token = request.cookies.get(self.cookie_name)
                if token:
                    data = self.serializer.loads(token)
                    username = (data or {}).get("u")
                    if username:
                        user_obj = {"username": username}
                        user_in_session = True
            except BadSignature:
                self.logger.warning("AuthMiddleware: invalid auth cookie signature", extra={
                    "path": path,
                    "method": method,
                })
            except Exception as e:
                self.logger.warning("AuthMiddleware: cookie auth error", extra={
                    "path": path,
                    "method": method,
                    "error_type": type(e).__name__,
                })

        if user_in_session:
            return await call_next(request)

        # Not authenticated -> always go to /login (no next param)
        if method == "GET":
            # Special-case: avoid loop for /logout
            if path == "/logout":
                return RedirectResponse(url="/login", status_code=302)
            self.logger.info("AuthMiddleware: redirecting unauthenticated GET", extra={
                "path": path,
            })
            return RedirectResponse(url="/login", status_code=302)

        self.logger.info("AuthMiddleware: redirecting unauthenticated non-GET", extra={
            "path": path,
            "method": method,
        })
        return RedirectResponse(url="/login", status_code=302)


