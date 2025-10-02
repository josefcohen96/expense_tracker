from __future__ import annotations

import logging
import os
from typing import Any, Iterable, List, Set, Tuple
from urllib.parse import quote_plus
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response


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

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.auth_enabled:
            return await call_next(request)

        path = request.url.path
        method = (request.method or "GET").upper()
        
        # Log all requests for debugging (reduce verbosity in production)
        auth_logger = logging.getLogger("app.auth")
        is_production = os.environ.get("RAILWAY_ENVIRONMENT") is not None or os.environ.get("ENVIRONMENT") == "production"
        if not is_production:
            auth_logger.debug(f"Request: {method} {path}")
            auth_logger.debug(f"Cookies: {dict(request.cookies)}")
            auth_logger.debug(f"Headers: {dict(request.headers)}")
        
        self.logger.info("AuthMiddleware: request received", extra={
            "path": path,
            "method": method,
            "cookies": dict(request.cookies),
            "timestamp": datetime.now().isoformat()
        })

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
        try:
            # Try to access session safely
            if hasattr(request, 'session') and request.session is not None:
                user_obj = request.session.get("user")
                user_in_session = bool(user_obj)
                session_id = getattr(request.session, 'session_id', None)
                session_keys = list(request.session.keys()) if hasattr(request.session, 'keys') else []
                session_data = dict(request.session) if hasattr(request.session, '__dict__') else {}
            else:
                user_obj = None
                user_in_session = False
                session_id = None
                session_keys = []
                session_data = {}
            
            # DEBUG: Log session details for all requests
            if not is_production:
                auth_logger.debug(f"Session check - path: {path}, user_in_session: {user_in_session}")
                auth_logger.debug(f"Session check - user_obj: {user_obj}")
                auth_logger.debug(f"Session check - session_keys: {session_keys}")
            
            self.logger.info("AuthMiddleware: session check", extra={
                "path": path,
                "method": method,
                "user_obj": user_obj,
                "user_in_session": user_in_session,
                "session_id": session_id,
                "session_keys": session_keys,
                "cookies": dict(request.cookies),
                "session_data": session_data,
            })
        except Exception as e:
            user_obj = None
            user_in_session = False
            session_id = None
            session_keys = []
            self.logger.warning("AuthMiddleware: session access failed", extra={
                "path": path,
                "method": method,
                "error": str(e),
                "error_type": type(e).__name__,
                "cookies": dict(request.cookies),
            })

        if user_in_session:
            self.logger.info("AuthMiddleware: authenticated request - allowing", extra={
                "path": path,
                "method": method,
                "username": (user_obj or {}).get("username") if isinstance(user_obj, dict) else None,
                "session_id": session_id,
                "session_keys": session_keys,
                "user_obj": user_obj,
                "timestamp": datetime.now().isoformat()
            })
            return await call_next(request)

        # Not authenticated -> always go to /login (no next param)
        if method == "GET":
            # Special-case: avoid loop for /logout
            if path == "/logout":
                return RedirectResponse(url="/login", status_code=302)
            self.logger.info("AuthMiddleware: redirecting unauthenticated GET", extra={
                "path": path,
                "method": method,
                "session_id": session_id,
                "session_keys": session_keys,
                "user_obj": user_obj,
            })
            return RedirectResponse(url="/login", status_code=302)

        self.logger.info("AuthMiddleware: redirecting unauthenticated non-GET", extra={
            "path": path,
            "method": method,
            "session_id": session_id,
            "session_keys": session_keys,
            "user_obj": user_obj,
        })
        return RedirectResponse(url="/login", status_code=302)


