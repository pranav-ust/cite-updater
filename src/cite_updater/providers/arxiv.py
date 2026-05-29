"""arXiv provider. Uses the arXiv export API (Atom feed) via feedparser."""

from __future__ import annotations

import logging

import feedparser

from ..bib_io import BibEntry
from ..http_client import RateLimiter
from . import CanonicalRecord, is_confident_match

log = logging.getLogger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query"


class ArxivProvider:
    name = "arxiv"

    def __init__(self, session, *, max_results: int = 5):
        self.session = session
        self.max_results = max_results
        # arXiv asks for <=1 request every 3s and throttles by IP (429 bursts);
        # the per-instance limiter resets each run, so repeated runs hammer the
        # same IP limit. Widen aggressively on failure.
        self.limiter = RateLimiter(min_interval=3.0, name="arxiv", max_interval=30.0, backoff_sleep=15.0)

    def search(self, entry: BibEntry) -> CanonicalRecord | None:
        if not entry.title:
            return None
        feed = self.limiter.request(lambda: self._fetch(entry.title))
        for item in feed.entries:
            arxiv_id = (getattr(item, "id", "") or "").rsplit("/", 1)[-1]
            record = CanonicalRecord(
                title=(getattr(item, "title", "") or "").strip(),
                authors=[a.name for a in getattr(item, "authors", [])],
                year=_year(getattr(item, "published", "")),
                venue=None,
                doi=getattr(item, "arxiv_doi", None) or None,
                url=f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else None,
                source=f"arxiv:{arxiv_id}" if arxiv_id else "arxiv",
            )
            if is_confident_match(entry, record):
                return record
        return None

    def _fetch(self, title: str):
        params = {"search_query": f'ti:"{title}"', "max_results": self.max_results}
        resp = self.session.get(ARXIV_API, params=params, timeout=20)
        resp.raise_for_status()
        return feedparser.parse(resp.text)


def _year(published: str) -> int | None:
    if not published or len(published) < 4:
        return None
    try:
        return int(published[:4])
    except ValueError:
        return None
