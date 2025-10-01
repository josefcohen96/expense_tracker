"""Custom SessionMiddleware that respects https_only=False setting."""
from starlette.middleware.sessions import SessionMiddleware
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
import logging

logger = logging.getLogger(__name__)


class CustomSessionMiddleware(SessionMiddleware):
    """
    Custom SessionMiddleware that properly respects the https_only parameter.
    
    Starlette's default SessionMiddleware sometimes sets Secure=True even when
    https_only=False, especially when running behind proxies. This middleware
    ensures that when https_only=False, cookies are NEVER created with Secure flag.
    """
    
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Store the original https_only setting
        force_insecure = not self.https_only
        
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start" and force_insecure:
                try:
                    # Remove Secure flag from Set-Cookie headers when https_only=False
                    headers = message.get("headers", [])
                    new_headers = []
                    
                    for key, value in headers:
                        if key.lower() == b"set-cookie":
                            # Remove "; Secure" from cookie if present
                            cookie_value = value.decode("latin-1")
                            if "; Secure" in cookie_value:
                                cookie_value = cookie_value.replace("; Secure", "")
                            if "; secure" in cookie_value:
                                cookie_value = cookie_value.replace("; secure", "")
                            new_headers.append((key, cookie_value.encode("latin-1")))
                        else:
                            new_headers.append((key, value))
                    
                    message["headers"] = new_headers
                except Exception as e:
                    logger.error(f"Error processing Set-Cookie header: {e}")
            
            await send(message)

        # Call parent with the wrapper if force_insecure, otherwise normal send
        if force_insecure:
            # We need to call the parent's parent __call__ method with our wrapper
            await SessionMiddleware.__call__(self, scope, receive, send_wrapper)
        else:
            await SessionMiddleware.__call__(self, scope, receive, send)
