"""DBLP HTTP API provider. https://dblp.org/faq/13501473.html"""

from __future__ import annotations

import html
import logging

from ..bib_io import BibEntry
from ..http_client import RateLimiter
from . import CanonicalRecord, is_confident_match

log = logging.getLogger(__name__)

DBLP_API = "https://dblp.org/search/publ/api"


class DblpProvider:
    name = "dblp"

    def __init__(self, session, *, max_results: int = 10):
        self.session = session
        self.max_results = max_results
        self.limiter = RateLimiter(min_interval=1.1, name="dblp", max_interval=8.0, backoff_sleep=10.0)

    def search(self, entry: BibEntry) -> CanonicalRecord | None:
        if not entry.title:
            return None
        hits = self.limiter.request(lambda: self._fetch(entry.title))
        for hit in hits:
            info = hit.get("info", {})
            record = _to_record(info)
            if is_confident_match(entry, record):
                return record
        return None

    def _fetch(self, title: str) -> list[dict]:
        params = {"q": title, "format": "json", "h": self.max_results}
        resp = self.session.get(DBLP_API, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json().get("result", {}).get("hits", {}).get("hit", [])


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
