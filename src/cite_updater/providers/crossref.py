"""CrossRef provider. https://api.crossref.org/swagger-ui/index.html"""

from __future__ import annotations

import logging

from ..bib_io import BibEntry
from ..http_client import RateLimiter
from . import CanonicalRecord, is_confident_match

log = logging.getLogger(__name__)

CROSSREF_API = "https://api.crossref.org/works"


class CrossrefProvider:
    name = "crossref"

    def __init__(self, session, *, max_results: int = 5):
        self.session = session
        self.max_results = max_results
        self.limiter = RateLimiter(min_interval=0.1, name="crossref", max_interval=5.0, backoff_sleep=5.0)

    def search(self, entry: BibEntry) -> CanonicalRecord | None:
        if not entry.title:
            return None
        items = self.limiter.request(lambda: self._fetch(entry.title))
        for item in items:
            record = _to_record(item)
            if is_confident_match(entry, record):
                return record
        return None

    def _fetch(self, title: str) -> list[dict]:
        params = {
            "query.bibliographic": title,
            "rows": self.max_results,
            "select": "DOI,title,author,issued,container-title,URL",
        }
        resp = self.session.get(CROSSREF_API, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("items", [])


def _to_record(item: dict) -> CanonicalRecord:
    title_list = item.get("title") or [""]
    title = title_list[0] if title_list else ""

    authors = []
    for a in item.get("author", []):
        given = a.get("given", "")
        family = a.get("family", "")
        full = f"{given} {family}".strip()
        if full:
            authors.append(full)

    year = None
    issued = item.get("issued", {})
    date_parts = issued.get("date-parts", [])
    if date_parts and date_parts[0]:
        year = date_parts[0][0]

    venue_list = item.get("container-title") or []
    venue = venue_list[0] if venue_list else None

    return CanonicalRecord(
        title=title,
        authors=authors,
        year=year,
        venue=venue,
        doi=item.get("DOI"),
        url=item.get("URL"),
        source=f"crossref:{item.get('DOI', '')}",
    )
