"""Semantic Scholar Graph API provider. https://api.semanticscholar.org/api-docs/graph"""

from __future__ import annotations

import logging
import os

from ..bib_io import BibEntry
from ..http_client import RateLimiter
from . import CanonicalRecord, is_confident_match

log = logging.getLogger(__name__)

S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_FIELDS = "title,authors,year,venue,externalIds,url"


class SemanticScholarProvider:
    name = "semantic_scholar"

    def __init__(self, session, *, max_results: int = 5):
        self.session = session
        self.max_results = max_results
        # Unauthenticated tier is heavily rate-limited and 429s often; be
        # conservative and back off hard.
        self.limiter = RateLimiter(min_interval=1.0, name="semantic_scholar", max_interval=10.0, backoff_sleep=10.0)

    def search(self, entry: BibEntry) -> CanonicalRecord | None:
        if not entry.title:
            return None
        papers = self.limiter.request(lambda: self._fetch(entry.title))
        for paper in papers:
            record = _to_record(paper)
            if is_confident_match(entry, record):
                return record
        return None

    def _fetch(self, title: str) -> list[dict]:
        params = {"query": title, "limit": self.max_results, "fields": S2_FIELDS}
        # Optional free API key for a substantially higher rate limit; anonymous
        # otherwise.
        headers = {}
        api_key = os.environ.get("S2_API_KEY")
        if api_key:
            headers["x-api-key"] = api_key
        resp = self.session.get(S2_API, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        return resp.json().get("data", [])


def _to_record(paper: dict) -> CanonicalRecord:
    authors = [a.get("name", "") for a in paper.get("authors", [])]
    external = paper.get("externalIds") or {}
    return CanonicalRecord(
        title=paper.get("title", "") or "",
        authors=[a for a in authors if a],
        year=paper.get("year"),
        venue=paper.get("venue") or None,
        doi=external.get("DOI"),
        url=paper.get("url"),
        source=f"s2:{paper.get('paperId', '')}",
    )
