"""Read and write .bib files, with helpers for annotating suspect entries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import bibtexparser
from bibtexparser.library import Library
from bibtexparser.model import Entry, ExplicitComment


@dataclass
class BibEntry:
    """View of a bibtexparser Entry, with the fields cite-updater cares about."""

    key: str
    entry_type: str
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None
    raw: Entry = field(repr=False)
    is_preprint: bool = False

    @classmethod
    def from_entry(cls, entry: Entry) -> "BibEntry":
        get = lambda name: _strip_braces(entry[name]) if name in entry.fields_dict else ""
        return cls(
            key=entry.key,
            entry_type=entry.entry_type,
            title=get("title"),
            authors=_split_authors(get("author")),
            year=_parse_year(get("year")),
            venue=get("booktitle") or get("journal") or None,
            doi=get("doi") or None,
            raw=entry,
            is_preprint=_looks_like_arxiv(get("archiveprefix"), get("eprint"), get("journal"), get("primaryclass")),
        )


_ARXIV_ID = re.compile(r"\b\d{4}\.\d{4,5}\b")


def _looks_like_arxiv(archiveprefix: str, eprint: str, journal: str, primaryclass: str) -> bool:
    """True if the entry is an arXiv preprint (archivePrefix/eprint/primaryClass/journal signals)."""
    if "arxiv" in (archiveprefix or "").lower() or "arxiv" in (journal or "").lower():
        return True
    if eprint and _ARXIV_ID.search(eprint):
        return True
    return bool(primaryclass and "." in primaryclass)  # e.g. cs.CV, stat.ML


_AUTHOR_SPLIT = re.compile(r"\s+and\s+", re.IGNORECASE)
_BRACE_PAIR = re.compile(r"^\{(.*)\}$", re.DOTALL)


def _strip_braces(value: str | None) -> str:
    if not value:
        return ""
    s = value.strip()
    while True:
        m = _BRACE_PAIR.match(s)
        if not m:
            return s
        s = m.group(1).strip()


def _split_authors(field_value: str) -> list[str]:
    if not field_value:
        return []
    return [a.strip() for a in _AUTHOR_SPLIT.split(field_value) if a.strip()]


def _parse_year(value: str) -> int | None:
    if not value:
        return None
    m = re.search(r"\d{4}", value)
    return int(m.group(0)) if m else None


def read_bib(path: str | Path) -> Library:
    text = Path(path).read_text(encoding="utf-8")
    return bibtexparser.parse_string(text)


def iter_entries(library: Library) -> Iterator[BibEntry]:
    for entry in library.entries:
        yield BibEntry.from_entry(entry)


def annotate(library: Library, entry_key: str, lines: list[str]) -> None:
    """Insert an @comment block immediately before the entry with the given key."""
    if not lines:
        return
    body = "\n".join(f"  {line}" for line in lines)
    comment = ExplicitComment(comment=f"cite-updater suggestion for {entry_key}:\n{body}")
    blocks = list(library.blocks)
    for i, block in enumerate(blocks):
        if isinstance(block, Entry) and block.key == entry_key:
            blocks.insert(i, comment)
            break
    else:
        return
    # Rebuild the library's block list. bibtexparser exposes `_blocks` on Library;
    # public API is to construct a new Library, which we do for cleanliness.
    library._blocks = blocks  # type: ignore[attr-defined]


def write_bib(library: Library, path: str | Path) -> None:
    text = bibtexparser.write_string(library)
    Path(path).write_text(text, encoding="utf-8")
