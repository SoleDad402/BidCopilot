"""Retry decorators using tenacity."""
from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

browser_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    retry=retry_if_exception_type((TimeoutError, ConnectionError)),
)

llm_retry = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((TimeoutError, ConnectionError)),
)
