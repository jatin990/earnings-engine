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
    requested URI from query parameters (__vercel_path__) or Vercel's proxy headers
    (x-now-route-matches, x-matched-path, x-forwarded-uri, x-invoke-path, etc.)
    so FastAPI correctly routes to /dashboard, /portal, /api/v1/auth/verify-code, etc.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            current_path = scope.get("path", "")
            raw_query = scope.get("query_string", b"").decode("utf-8", errors="ignore")

            target_path = None

            # 1. Extract from __vercel_path__ query param (injected via vercel.json rewrite)
            if raw_query and "__vercel_path__" in raw_query:
                try:
                    parsed_query = urllib.parse.parse_qs(raw_query, keep_blank_values=True)
                    if "__vercel_path__" in parsed_query:
                        extracted_list = parsed_query.pop("__vercel_path__")
                        raw_extracted = extracted_list[0] if extracted_list else ""
                        if raw_extracted:
                            target_path = "/" + raw_extracted.lstrip("/")
                        else:
                            target_path = "/"

                        # Rebuild clean query string without __vercel_path__
                        clean_qs = urllib.parse.urlencode(parsed_query, doseq=True) if parsed_query else ""
                        scope = dict(scope)
                        scope["query_string"] = clean_qs.encode("utf-8")
                except Exception:
                    pass

            # 2. Try extracting path from x-now-route-matches or x-vercel-route-matches
            if not target_path or target_path in ("/api/index.py", "/api/index", "/api", "/api/index.py/"):
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

            # 3. Fall back to other Vercel proxy headers
            if not target_path or target_path in ("/api/index.py", "/api/index", "/api", "/api/index.py/"):
                for header_key in (
                    b"x-forwarded-uri",
                    b"x-original-uri",
                    b"x-rewrite-url",
                    b"x-matched-path",
                    b"x-invoke-path",
                    b"x-vercel-forwarded-path",
                    b"x-vercel-invoke-path",
                ):
                    raw_val = headers.get(header_key)
                    if raw_val:
                        decoded = raw_val.decode("utf-8", errors="ignore").split("?")[0]
                        if decoded and decoded not in ("/api/index.py", "/api/index", "/api", "/api/index.py/"):
                            target_path = decoded
                            break

            # 4. Clean target_path
            if target_path and "?" in target_path:
                target_path = target_path.split("?")[0]

            # 5. Apply target_path to scope
            if target_path and target_path not in ("/api/index.py", "/api/index", "/api", "/api/index.py/"):
                scope = dict(scope)
                scope["path"] = target_path
                scope["raw_path"] = target_path.encode("utf-8")
            elif current_path in ("/api/index.py", "/api/index", "/api", "/api/index.py/") or current_path.startswith("/api/index.py"):
                scope = dict(scope)
                scope["path"] = "/"
                scope["raw_path"] = b"/"

        await self.app(scope, receive, send)


# Export the wrapped ASGI application for Vercel Python runtime
app = VercelPathFixMiddleware(_fastapi_app)


