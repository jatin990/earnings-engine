"""Vercel serverless entry point for Earnings Engine FastAPI app."""

import os
import sys
from pathlib import Path

# Ensure serverless environment flags are active before importing server
os.environ["VERCEL"] = "1"
os.environ["SERVERLESS"] = "1"

# Add project root to sys.path so earnings_engine package can be resolved
_root_dir = Path(__file__).resolve().parent.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

from earnings_engine.api.server import app as _fastapi_app


class VercelPathFixMiddleware:
    """ASGI middleware to restore original request path on Vercel deployments.

    Vercel CLI 59+ internal rewrites route requests to /api/index.py, passing
    the destination path in scope['path']. This middleware extracts the original
    requested URI from Vercel's x-matched-path, x-forwarded-uri, or x-invoke-path
    headers so FastAPI correctly routes to /dashboard, /portal, /api/v1/..., etc.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") in ("http", "websocket"):
            headers = dict(scope.get("headers", []))

            # Extract matched/forwarded path from Vercel headers
            matched_header = (
                headers.get(b"x-matched-path")
                or headers.get(b"x-forwarded-uri")
                or headers.get(b"x-invoke-path")
            )

            current_path = scope.get("path", "")

            if matched_header:
                orig_path = matched_header.decode("utf-8", errors="ignore").split("?")[0]
                if orig_path and (
                    current_path in ("/api/index.py", "/api/index", "/api", "/api/index.py/")
                    or current_path.startswith("/api/index.py")
                ):
                    scope = dict(scope)
                    scope["path"] = orig_path
                    scope["raw_path"] = orig_path.encode("utf-8")

        await self.app(scope, receive, send)


# Export the wrapped ASGI application for Vercel Python runtime
app = VercelPathFixMiddleware(_fastapi_app)

