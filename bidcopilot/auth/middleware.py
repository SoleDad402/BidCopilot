"""FastAPI auth middleware — verifies JWT tokens via CVCopilot."""
from __future__ import annotations

import time

from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from bidcopilot.auth.client import AuthClient

# In-memory token verification cache: token -> (user_dict, expiry_timestamp)
_verify_cache: dict[str, tuple[dict, float]] = {}
CACHE_TTL = 300  # 5 minutes

PUBLIC_PREFIXES = ("/login", "/api/auth/", "/static/")


def _is_public(path: str) -> bool:
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


async def _cached_verify(auth_client: AuthClient, token: str) -> dict | None:
    """Verify token with TTL cache to avoid hammering CVCopilot."""
    now = time.time()
    cached = _verify_cache.get(token)
    if cached and cached[1] > now:
        return cached[0]

    result = await auth_client.verify_token(token)
    if result:
        user = result.get("user", result)
        _verify_cache[token] = (user, now + CACHE_TTL)
        return user

    # Remove stale entry
    _verify_cache.pop(token, None)
    return None


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware that protects all routes except login and static assets."""

    def __init__(self, app, auth_client: AuthClient):
        super().__init__(app)
        self.auth_client = auth_client

    async def dispatch(self, request: Request, call_next):
        if _is_public(request.url.path):
            return await call_next(request)

        # Extract token from cookie or Authorization header
        token = request.cookies.get("bc_token")
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]

        if not token:
            return self._unauthorized(request)

        user = await _cached_verify(self.auth_client, token)
        if not user:
            return self._unauthorized(request)

        # Attach user and token to request state
        request.state.user = user
        request.state.token = token
        return await call_next(request)

    @staticmethod
    def _unauthorized(request: Request):
        accepts = request.headers.get("accept", "")
        if "text/html" in accepts:
            return RedirectResponse("/login", status_code=302)
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
