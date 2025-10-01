"""Custom SessionMiddleware that respects https_only=False setting."""
from starlette.middleware.sessions import SessionMiddleware
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


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
                # Remove Secure flag from Set-Cookie headers when https_only=False
                headers = MutableHeaders(scope=message)
                set_cookie_headers = []
                
                for idx, (key, value) in enumerate(message.get("headers", [])):
                    if key.lower() == b"set-cookie":
                        # Remove "; Secure" from cookie if present
                        cookie_value = value.decode("latin-1")
                        if "; Secure" in cookie_value:
                            cookie_value = cookie_value.replace("; Secure", "")
                        if "; secure" in cookie_value:
                            cookie_value = cookie_value.replace("; secure", "")
                        set_cookie_headers.append((key, cookie_value.encode("latin-1")))
                    else:
                        set_cookie_headers.append((key, value))
                
                message["headers"] = set_cookie_headers
            
            await send(message)

        await super().__call__(scope, receive, send_wrapper if force_insecure else send)

