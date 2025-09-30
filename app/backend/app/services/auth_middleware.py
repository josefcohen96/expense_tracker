from __future__ import annotations

import logging
from typing import Any, Iterable, List, Set, Tuple
from urllib.parse import quote_plus

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

        # Allow unauthenticated access to static and service worker
        if path.startswith("/static/") or path == "/sw.js":
            return await call_next(request)

        # Allow @public endpoints
        try:
            for regex, methods in self.public_route_matchers:
                try:
                    if regex.match(path) and (not methods or method in methods):
                        return await call_next(request)
                except Exception:
                    # Best-effort; ignore a broken matcher
                    continue
        except Exception:
            self.logger.exception("AuthMiddleware: error checking public matchers")

        # Require a session user for everything else
        try:
            user_in_session = bool(request.session.get("user"))
        except Exception:
            user_in_session = False

        if user_in_session:
            return await call_next(request)

        # Not authenticated -> redirect appropriately
        if method == "GET":
            # Special-case: avoid next=/logout to prevent loops
            if path == "/logout":
                return RedirectResponse(url="/login", status_code=302)
            query = ("?" + str(request.url.query)) if request.url.query else ""
            nxt = quote_plus(path + query)
            return RedirectResponse(url=f"/login?next={nxt}", status_code=302)

        return RedirectResponse(url="/login", status_code=302)


