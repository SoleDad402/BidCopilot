"""Proxy rotation and health checking."""
from __future__ import annotations
import random
from pydantic import BaseModel
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

class ProxyInfo(BaseModel):
    url: str
    username: str | None = None
    password: str | None = None
    is_healthy: bool = True

class ProxyManager:
    def __init__(self, proxy_list: list[str] | None = None):
        self._proxies: list[ProxyInfo] = []
        for p in (proxy_list or []):
            self._proxies.append(ProxyInfo(url=p))

    def get_proxy(self, site_name: str | None = None) -> ProxyInfo | None:
        healthy = [p for p in self._proxies if p.is_healthy]
        return random.choice(healthy) if healthy else None

    def mark_unhealthy(self, proxy_url: str):
        for p in self._proxies:
            if p.url == proxy_url:
                p.is_healthy = False
                logger.warning("proxy_marked_unhealthy", url=proxy_url)
