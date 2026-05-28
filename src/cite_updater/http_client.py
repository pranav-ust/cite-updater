"""Shared HTTP session with retry, on-disk cache, and per-provider rate limiting."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import requests
import requests_cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "cite-updater/0.1 (+https://github.com/pranav-ust/cite-updater)"
DEFAULT_CACHE_PATH = Path.home() / ".cache" / "cite-updater" / "http"
DEFAULT_CACHE_TTL = 60 * 60 * 24 * 30  # 30 days


def build_session(
    *,
    cache: bool = True,
    cache_path: Path = DEFAULT_CACHE_PATH,
    cache_ttl: int = DEFAULT_CACHE_TTL,
    user_agent: str = DEFAULT_USER_AGENT,
) -> requests.Session:
    if cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        session = requests_cache.CachedSession(
            cache_name=str(cache_path),
            backend="sqlite",
            expire_after=cache_ttl,
            allowable_codes=(200,),
            stale_if_error=True,
        )
    else:
        session = requests.Session()

    retry = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers["User-Agent"] = user_agent
    return session


class RateLimiter:
    """Simple per-domain rate limiter: ensure at least `min_interval` seconds between calls."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait_for = self._last + self.min_interval - now
            if wait_for > 0:
                time.sleep(wait_for)
            self._last = time.monotonic()
