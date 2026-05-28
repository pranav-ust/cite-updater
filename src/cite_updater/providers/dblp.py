"""DBLP HTTP API provider. https://dblp.org/faq/13501473.html"""

from __future__ import annotations

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
        self.limiter = RateLimiter(min_interval=1.1)

    def search(self, entry: BibEntry) -> CanonicalRecord | None:
        if not entry.title:
            return None
        self.limiter.wait()
        params = {"q": entry.title, "format": "json", "h": self.max_results}
        resp = self.session.get(DBLP_API, params=params, timeout=20)
        resp.raise_for_status()
        hits = resp.json().get("result", {}).get("hits", {}).get("hit", [])
        for hit in hits:
            info = hit.get("info", {})
            record = _to_record(info)
            if is_confident_match(entry, record):
                return record
        return None


def _to_record(info: dict) -> CanonicalRecord:
    authors_field = info.get("authors", {}).get("author", [])
    if isinstance(authors_field, dict):
        authors_field = [authors_field]
    authors = [a.get("text", "") if isinstance(a, dict) else str(a) for a in authors_field]

    year_raw = info.get("year")
    try:
        year = int(year_raw) if year_raw else None
    except (TypeError, ValueError):
        year = None

    return CanonicalRecord(
        title=info.get("title", "").rstrip("."),
        authors=authors,
        year=year,
        venue=info.get("venue") or None,
        doi=info.get("doi") or None,
        url=info.get("ee") or info.get("url") or None,
        source=f"dblp:{info.get('key', '')}",
    )
