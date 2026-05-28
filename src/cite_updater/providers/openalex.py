"""OpenAlex provider. https://docs.openalex.org/"""

from __future__ import annotations

import logging

from ..bib_io import BibEntry
from ..http_client import RateLimiter
from . import CanonicalRecord, is_confident_match

log = logging.getLogger(__name__)

OPENALEX_API = "https://api.openalex.org/works"


class OpenAlexProvider:
    name = "openalex"

    def __init__(self, session, *, max_results: int = 5):
        self.session = session
        self.max_results = max_results
        # OpenAlex polite pool is generous; keep a tiny gap.
        self.limiter = RateLimiter(min_interval=0.1)

    def search(self, entry: BibEntry) -> CanonicalRecord | None:
        if not entry.title:
            return None
        self.limiter.wait()
        params = {"search": entry.title, "per-page": self.max_results}
        resp = self.session.get(OPENALEX_API, params=params, timeout=20)
        resp.raise_for_status()
        for work in resp.json().get("results", []):
            record = _to_record(work)
            if is_confident_match(entry, record):
                return record
        return None


def _to_record(work: dict) -> CanonicalRecord:
    authors = [
        (a.get("author") or {}).get("display_name", "")
        for a in work.get("authorships", [])
    ]
    venue = None
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    if isinstance(source, dict):
        venue = source.get("display_name")

    doi = work.get("doi") or ""
    if doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]

    return CanonicalRecord(
        title=work.get("title", "") or work.get("display_name", "") or "",
        authors=[a for a in authors if a],
        year=work.get("publication_year"),
        venue=venue,
        doi=doi or None,
        url=work.get("id"),
        source=f"openalex:{(work.get('id') or '').rsplit('/', 1)[-1]}",
    )
