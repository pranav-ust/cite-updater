"""Author-name normalization. Ported from the research repo's validate_citations.py."""

from __future__ import annotations

import re
from typing import TypedDict

from nameparser import HumanName
from unidecode import unidecode


class Author(TypedDict):
    first_name: str
    middle_name: str
    last_name: str
    suffix: str
    title: str
    original: str
    parsing_error: bool


LAST_NAME_PREFIXES = {
    "de", "van", "von", "del", "della", "di", "da",
    "le", "la", "el", "der", "den", "du", "des",
}

_REAL_TITLES = {
    "dr", "mr", "mrs", "ms", "prof", "professor",
    "sir", "madam", "lord", "lady",
}


def strip_accents(text: str) -> str:
    return unidecode(text or "")


def normalize_for_comparison(name: str) -> str:
    if not name:
        return ""
    return unidecode(name.lower().replace(".", "").strip())


def split_last_name_prefix(last_name: str) -> tuple[str, str]:
    """Return (base, original). E.g. 'De Choudhury' -> ('choudhury', 'De Choudhury')."""
    if not last_name:
        return "", ""
    parts = last_name.lower().strip().split()
    if parts and parts[0] in LAST_NAME_PREFIXES:
        base = " ".join(parts[1:]) if len(parts) > 1 else parts[0]
        return base, last_name
    return last_name.lower().strip(), last_name


def names_match_with_accents(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a.lower().strip() == b.lower().strip():
        return True
    return normalize_for_comparison(a) == normalize_for_comparison(b)


def parse_author(name: str) -> Author:
    """Parse a free-form author string into structured components."""
    has_parsing_error = False
    if not name or not name.strip():
        has_parsing_error = True
    elif "*" in name:
        has_parsing_error = True
    elif name.strip().startswith(";"):
        has_parsing_error = True
    elif len(name.strip()) == 1:
        has_parsing_error = True

    cleaned = re.sub(r"\s+\d{4}(?:\s|$)", "", name or "")
    cleaned = re.sub(r"\s+\d{4,}$", "", cleaned)
    cleaned = re.sub(r"\s+\d{4,}\s+", " ", cleaned)
    cleaned = cleaned.replace("*", "").strip()
    if not cleaned:
        has_parsing_error = True

    parsed = HumanName(cleaned)
    first = parsed.first or ""
    middle = parsed.middle or ""
    last = parsed.last or ""
    title = parsed.title or ""
    suffix = parsed.suffix or ""

    if first == "*" or last == "*" or (not first and not last):
        has_parsing_error = True

    # nameparser sometimes shoves the first token into `title` for multi-word
    # given names like "Se Young Chun". Recover the common case.
    if title and first and " " not in title and title.lower() not in _REAL_TITLES:
        first = f"{title} {first}".strip()
        title = ""

    return Author(
        first_name=first,
        middle_name=middle,
        last_name=last,
        suffix=suffix,
        title=title,
        original=name or "",
        parsing_error=has_parsing_error,
    )


def parse_authors(names: list[str]) -> list[Author]:
    return [parse_author(n) for n in names if n is not None]
