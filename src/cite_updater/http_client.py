"""Shared HTTP session with retry, on-disk cache, and per-provider rate limiting."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, TypeVar

import requests
import requests_cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

T = TypeVar("T")

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

    # Optional contact email for provider polite pools / authenticated tiers.
    # Anonymous remains the default when CITE_UPDATER_MAILTO is unset.
    mailto = os.environ.get("CITE_UPDATER_MAILTO") or None
    if mailto:
        user_agent = f"{user_agent} (mailto:{mailto})"
    session.headers["User-Agent"] = user_agent
    # Stash so providers can also add mailto as a query param.
    session.cite_updater_mailto = mailto
    return session


class RateLimiter:
    """Per-domain rate limiter with adaptive backoff.

    Ensures at least `min_interval` seconds between calls. On a request failure,
    `request()` widens the interval (doubling, capped at `max_interval`), sleeps
    `backoff_sleep`, and retries once; a success decays the interval back toward
    `min_interval`. With the defaults (`max_interval == min_interval`,
    `backoff_sleep == 0`) it behaves like a plain spacing limiter.
    """

    def __init__(
        self,
        min_interval: float,
        *,
        name: str = "",
        max_interval: float | None = None,
        backoff_sleep: float = 0.0,
    ):
        self.base_interval = min_interval
        self.min_interval = min_interval
        self.max_interval = max_interval if max_interval is not None else min_interval
        self.backoff_sleep = backoff_sleep
        self.name = name
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

    def request(self, fetch: Callable[[], T]) -> T:
        """Run `fetch` under the rate limit, retrying once with backoff on failure."""
        self.wait()
        try:
            result = fetch()
        except requests.RequestException as exc:
            self._widen()
            log.info(
                "%s request failed, backing off (interval=%.1fs): %s",
                self.name or "provider", self.min_interval, exc,
            )
            if self.backoff_sleep > 0:
                time.sleep(self.backoff_sleep)
            self.wait()
            try:
                result = fetch()
            except requests.RequestException:
                self._widen()
                raise
        self._narrow()
        return result

    def _widen(self) -> None:
        self.min_interval = min(max(self.min_interval, self.base_interval) * 2, self.max_interval)

    def _narrow(self) -> None:
        if self.min_interval > self.base_interval:
            self.min_interval = max(self.min_interval * 0.8, self.base_interval)
