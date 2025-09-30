from typing import Any, Callable, List, Tuple, Set
import re
import logging

try:
    # FastAPI/APIRoute is optional at import time for tooling; guarded use
    from fastapi.routing import APIRoute  # type: ignore
except Exception:  # pragma: no cover - safe fallback if not available
    APIRoute = object  # type: ignore


def public(func: Callable) -> Callable:
    setattr(func, "_is_public", True)
    return func


def is_endpoint_public(endpoint: Any) -> bool:
    try:
        return bool(getattr(endpoint, "_is_public", False))
    except Exception:
        return False


def build_public_route_matchers(app: Any) -> List[Tuple["re.Pattern[str]", Set[str]]]:
    """Collect regex + methods for routes decorated with @public.

    Returns list of tuples: (compiled_regex, set_of_methods)
    """
    logger = logging.getLogger(__name__)
    matchers: List[Tuple["re.Pattern[str]", Set[str]]] = []
    try:
        for r in getattr(app, "routes", []) or []:
            try:
                is_public = isinstance(r, APIRoute) and is_endpoint_public(getattr(r, "endpoint", None))
            except Exception:
                is_public = False
            if not is_public:
                continue
            try:
                regex = getattr(r, "path_regex")
            except Exception:
                path_str = getattr(r, "path", getattr(r, "path_format", "")) or ""
                pattern = "^" + re.escape(path_str) + "$"
                regex = re.compile(pattern)
            methods = set(m.upper() for m in (getattr(r, "methods", None) or {"GET"}))
            matchers.append((regex, methods))
    except Exception:
        logger.exception("Failed building public route matchers")
    return matchers

