"""arXiv provider. Uses the arXiv export API (Atom feed) via feedparser."""

from __future__ import annotations

import logging
import time

import feedparser
import requests

from ..bib_io import BibEntry
from ..http_client import RateLimiter
from . import CanonicalRecord, is_confident_match

log = logging.getLogger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query"

# arXiv asks for <=1 request every 3s, but throttles by IP and returns bursts of
# 429s once tripped — and the per-instance limiter resets each run, so repeated
# runs hammer the same IP limit. Widen the gap on failure (cap 30s), retry once.
_BASE_INTERVAL = 3.0
_MAX_INTERVAL = 30.0
_BACKOFF_SLEEP = 15.0


class ArxivProvider:
    name = "arxiv"

    def __init__(self, session, *, max_results: int = 5):
        self.session = session
        self.max_results = max_results
        self.limiter = RateLimiter(min_interval=_BASE_INTERVAL)

    def search(self, entry: BibEntry) -> CanonicalRecord | None:
        if not entry.title:
            return None
        try:
            feed = self._fetch(entry.title)
        except requests.RequestException as exc:
            self._on_failure()
            log.info("arxiv throttled, backing off (interval=%.1fs): %s", self.limiter.min_interval, exc)
            time.sleep(_BACKOFF_SLEEP)
            try:
                feed = self._fetch(entry.title)
            except requests.RequestException as exc2:
                self._on_failure()
                raise exc2
        self._on_success()
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
        self.limiter.wait()
        params = {"search_query": f'ti:"{title}"', "max_results": self.max_results}
        resp = self.session.get(ARXIV_API, params=params, timeout=20)
        resp.raise_for_status()
        return feedparser.parse(resp.text)

    def _on_failure(self) -> None:
        self.limiter.min_interval = min(self.limiter.min_interval * 2, _MAX_INTERVAL)

    def _on_success(self) -> None:
        if self.limiter.min_interval > _BASE_INTERVAL:
            self.limiter.min_interval = max(self.limiter.min_interval * 0.8, _BASE_INTERVAL)


def _year(published: str) -> int | None:
    if not published or len(published) < 4:
        return None
    try:
        return int(published[:4])
    except ValueError:
        return None
