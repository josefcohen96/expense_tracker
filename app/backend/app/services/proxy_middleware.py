"""Middleware to handle Railway proxy headers for correct scheme detection."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.datastructures import Headers, MutableHeaders
import logging

logger = logging.getLogger(__name__)


class ProxyHeaderMiddleware(BaseHTTPMiddleware):
    """
    Middleware that ensures Railway's proxy headers are properly handled.
    Railway terminates HTTPS at the proxy level and forwards HTTP to the container.
    This middleware forces the request to appear as HTTPS when X-Forwarded-Proto is https.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Get the forwarded protocol
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        
        # Log for debugging
        logger.debug(f"ProxyHeaderMiddleware: proto={forwarded_proto}, url={request.url}")
        
        # If the proxy says it's HTTPS, we need to make sure the request reflects that
        if forwarded_proto == "https":
            # Modify the scope to reflect HTTPS
            request.scope["scheme"] = "https"
            
        response = await call_next(request)
        return response

