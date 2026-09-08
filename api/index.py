"""Vercel serverless entry point for Earnings Engine FastAPI app."""

import os
import sys
import urllib.parse
from pathlib import Path

# Ensure serverless environment flags are active before importing server (when not running tests)
if "PYTEST_CURRENT_TEST" not in os.environ and "TESTING" not in os.environ:
    os.environ["VERCEL"] = "1"
    os.environ["SERVERLESS"] = "1"

# Add project root to sys.path so earnings_engine package can be resolved
_root_dir = Path(__file__).resolve().parent.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

from earnings_engine.api.server import app as _fastapi_app


class VercelPathFixMiddleware:
    """ASGI middleware to restore original request path on Vercel deployments.

    Vercel internal rewrites route requests to /api/index.py, passing
    the destination path in scope['path']. This middleware extracts the original
    requested URI from Vercel's headers (x-now-route-matches, x-matched-path,
    x-forwarded-uri, x-invoke-path, etc.) so FastAPI correctly routes to
    /dashboard, /portal, /api/v1/..., etc.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            current_path = scope.get("path", "")

            # 1. Try extracting path from x-now-route-matches (Vercel regex capture group 1)
            target_path = None
            route_matches = headers.get(b"x-now-route-matches") or headers.get(b"x-vercel-route-matches")
            if route_matches:
                try:
                    match_str = route_matches.decode("utf-8", errors="ignore")
                    params = urllib.parse.parse_qs(match_str)
                    if "1" in params and params["1"]:
                        val = params["1"][0]
                        if val:
                            target_path = "/" + val.lstrip("/")
                        else:
                            target_path = "/"
                except Exception:
                    pass

            # 2. Fall back to other Vercel proxy headers
            if not target_path or target_path in ("/api/index.py", "/api/index", "/api", "/api/index.py/"):
                for header_key in (
                    b"x-forwarded-uri",
                    b"x-original-uri",
                    b"x-rewrite-url",
                    b"x-matched-path",
                    b"x-invoke-path",
                ):
                    raw_val = headers.get(header_key)
                    if raw_val:
                        decoded = raw_val.decode("utf-8", errors="ignore").split("?")[0]
                        if decoded and decoded not in ("/api/index.py", "/api/index", "/api", "/api/index.py/"):
                            target_path = decoded
                            break

            # 3. If current path is the serverless entrypoint, route to target_path or fallback to root "/"
            if current_path in ("/api/index.py", "/api/index", "/api", "/api/index.py/") or current_path.startswith("/api/index.py"):
                final_path = target_path if (target_path and target_path not in ("/api/index.py", "/api/index", "/api", "/api/index.py/")) else "/"
                scope = dict(scope)
                scope["path"] = final_path
                scope["raw_path"] = final_path.encode("utf-8")

        await self.app(scope, receive, send)


# Export the wrapped ASGI application for Vercel Python runtime
app = VercelPathFixMiddleware(_fastapi_app)


