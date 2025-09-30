from typing import Any, Callable


def public(func: Callable) -> Callable:
    setattr(func, "_is_public", True)
    return func


def is_endpoint_public(endpoint: Any) -> bool:
    try:
        return bool(getattr(endpoint, "_is_public", False))
    except Exception:
        return False


