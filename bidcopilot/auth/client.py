"""HTTP client for CVCopilot authentication service."""
from __future__ import annotations

import httpx

from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)


class AuthClient:
    """Client for CVCopilot auth endpoints.

    Proxies login/verify/profile requests to CVCopilot's Express backend
    so the BidCopilot dashboard doesn't need direct browser-to-CVCopilot calls.
    """

    def __init__(self, base_url: str = "http://localhost:4090"):
        self.base_url = base_url
        self.http = httpx.AsyncClient(timeout=10)

    async def login(self, email: str, password: str, remember_me: bool = False) -> dict | None:
        """Authenticate against CVCopilot. Returns {"token": "..."} or None."""
        try:
            resp = await self.http.post(
                f"{self.base_url}/api/auth/login",
                json={"email": email, "password": password, "rememberMe": remember_me},
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning("auth_login_failed", status=resp.status_code)
            return None
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.error("auth_service_unavailable", error=str(e))
            return None

    async def verify_token(self, token: str) -> dict | None:
        """Verify a JWT token. Returns user dict or None."""
        try:
            resp = await self.http.get(
                f"{self.base_url}/api/auth/verify",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except (httpx.ConnectError, httpx.TimeoutException):
            return None

    async def get_profile(self, token: str) -> dict | None:
        """Fetch full profile from CVCopilot. Returns {user, employmentHistory, education} or None."""
        try:
            resp = await self.http.get(
                f"{self.base_url}/api/profile",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.error("auth_profile_fetch_failed", error=str(e))
            return None

    async def close(self):
        await self.http.aclose()
