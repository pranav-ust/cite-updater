"""Bibliographic API providers and the fallback-chain runner."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from rapidfuzz import fuzz

from ..bib_io import BibEntry

log = logging.getLogger(__name__)


@dataclass
class CanonicalRecord:
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None
    url: str | None
    source: str


class Provider(Protocol):
    name: str

    def search(self, entry: BibEntry) -> CanonicalRecord | None: ...


def title_similarity(a: str, b: str) -> float:
    return fuzz.ratio(_norm_title(a), _norm_title(b)) / 100.0


def _norm_title(t: str) -> str:
    return " ".join((t or "").lower().split())


def author_overlap(query: list[str], candidate: list[str]) -> int:
    """Count how many last-name tokens overlap (case-insensitive, accents stripped)."""
    from ..normalize import strip_accents

    def lasts(names: list[str]) -> set[str]:
        out: set[str] = set()
        for n in names:
            tokens = strip_accents(n).lower().replace(",", " ").split()
            if tokens:
                out.add(tokens[-1])
        return out

    return len(lasts(query) & lasts(candidate))


def is_confident_match(
    entry: BibEntry,
    record: CanonicalRecord,
    *,
    min_title_sim: float = 0.85,
    min_author_overlap: int = 1,
) -> bool:
    if not record.title:
        return False
    if title_similarity(entry.title, record.title) < min_title_sim:
        return False
    if entry.authors and author_overlap(entry.authors, record.authors) < min_author_overlap:
        return False
    return True


def run_chain(providers: list[Provider], entry: BibEntry) -> CanonicalRecord | None:
    for p in providers:
        try:
            rec = p.search(entry)
        except Exception as exc:  # noqa: BLE001 — providers may fail; chain continues
            log.warning("provider %s failed for %r: %s", p.name, entry.key, exc)
            continue
        if rec is not None:
            log.debug("provider %s matched %r", p.name, entry.key)
            return rec
    return None


from .arxiv import ArxivProvider  # noqa: E402
from .crossref import CrossrefProvider  # noqa: E402
from .dblp import DblpProvider  # noqa: E402
from .openalex import OpenAlexProvider  # noqa: E402
from .semantic_scholar import SemanticScholarProvider  # noqa: E402

ALL_PROVIDERS: dict[str, type[Provider]] = {
    "arxiv": ArxivProvider,
    "dblp": DblpProvider,
    "openalex": OpenAlexProvider,
    "crossref": CrossrefProvider,
    "semantic_scholar": SemanticScholarProvider,
}

DEFAULT_CHAIN = ["arxiv", "dblp", "openalex", "crossref", "semantic_scholar"]


def build_chain(names: list[str], session) -> list[Provider]:
    chain: list[Provider] = []
    for name in names:
        if name not in ALL_PROVIDERS:
            raise ValueError(f"unknown provider: {name}")
        chain.append(ALL_PROVIDERS[name](session=session))
    return chain
