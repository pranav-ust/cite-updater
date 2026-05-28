"""DBLP HTTP API provider. https://dblp.org/faq/13501473.html"""

from __future__ import annotations

import html
import logging
import time

import requests

from ..bib_io import BibEntry
from ..http_client import RateLimiter
from . import CanonicalRecord, is_confident_match

log = logging.getLogger(__name__)

DBLP_API = "https://dblp.org/search/publ/api"

_BASE_INTERVAL = 1.1
_MAX_INTERVAL = 8.0
_BACKOFF_SLEEP = 10.0  # extra sleep before single in-provider retry


class DblpProvider:
    name = "dblp"

    def __init__(self, session, *, max_results: int = 10):
        self.session = session
        self.max_results = max_results
        self.limiter = RateLimiter(min_interval=_BASE_INTERVAL)

    def search(self, entry: BibEntry) -> CanonicalRecord | None:
        if not entry.title:
            return None
        try:
            hits = self._fetch(entry.title)
        except requests.RequestException as exc:
            self._on_failure()
            log.info("dblp connection error, backing off (interval=%.1fs): %s", self.limiter.min_interval, exc)
            time.sleep(_BACKOFF_SLEEP)
            try:
                hits = self._fetch(entry.title)
            except requests.RequestException as exc2:
                self._on_failure()
                raise exc2
        self._on_success()
        for hit in hits:
            info = hit.get("info", {})
            record = _to_record(info)
            if is_confident_match(entry, record):
                return record
        return None

    def _fetch(self, title: str) -> list[dict]:
        self.limiter.wait()
        params = {"q": title, "format": "json", "h": self.max_results}
        resp = self.session.get(DBLP_API, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json().get("result", {}).get("hits", {}).get("hit", [])

    def _on_failure(self) -> None:
        new_interval = min(self.limiter.min_interval * 2, _MAX_INTERVAL)
        if new_interval != self.limiter.min_interval:
            self.limiter.min_interval = new_interval

    def _on_success(self) -> None:
        if self.limiter.min_interval > _BASE_INTERVAL:
            self.limiter.min_interval = max(self.limiter.min_interval * 0.8, _BASE_INTERVAL)


def _to_record(info: dict) -> CanonicalRecord:
    authors_field = info.get("authors", {}).get("author", [])
    if isinstance(authors_field, dict):
        authors_field = [authors_field]
    # DBLP's JSON HTML-escapes characters in names/titles (e.g. D'Orazio → D&apos;Orazio).
    authors = [
        html.unescape(a.get("text", "") if isinstance(a, dict) else str(a))
        for a in authors_field
    ]

    year_raw = info.get("year")
    try:
        year = int(year_raw) if year_raw else None
    except (TypeError, ValueError):
        year = None

    return CanonicalRecord(
        title=html.unescape(info.get("title", "")).rstrip("."),
        authors=authors,
        year=year,
        venue=html.unescape(info.get("venue")) if info.get("venue") else None,
        doi=info.get("doi") or None,
        url=info.get("ee") or info.get("url") or None,
        source=f"dblp:{info.get('key', '')}",
    )
