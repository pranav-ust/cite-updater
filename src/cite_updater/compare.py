"""Compare a BibEntry against a CanonicalRecord and report mismatches."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from .bib_io import BibEntry
from .matchers import initial_matches, is_name_match
from .normalize import (
    names_match_with_accents,
    normalize_for_comparison,
    parse_authors,
    split_last_name_prefix,
)
from .providers import CanonicalRecord


MismatchKind = str  # e.g. "first_name_mismatch", "title_mismatch", "year_mismatch", ...


@dataclass
class Mismatch:
    kind: MismatchKind
    detail: str


# ---------- authors ----------

def _compare_authors(entry: BibEntry, record: CanonicalRecord, max_authors: int = 10) -> list[Mismatch]:
    ref = parse_authors(entry.authors)[:max_authors]
    cand = parse_authors(record.authors)[:max_authors]
    if not ref:
        return [Mismatch("empty_list", "entry has no authors")]
    if not cand:
        return []  # nothing to compare against; provider should have skipped

    if any(a["parsing_error"] for a in ref):
        bad = "; ".join(a["original"] for a in ref if a["parsing_error"])
        return [Mismatch("parsing_error", f"unparseable author(s): {bad}")]

    matched_ref: set[int] = set()
    matched_cand: set[int] = set()
    matches: list[tuple[int, int]] = []

    for i, r in enumerate(ref):
        for j, c in enumerate(cand):
            if j in matched_cand:
                continue
            if _authors_equivalent(r, c):
                matched_ref.add(i)
                matched_cand.add(j)
                matches.append((i, j))
                break

    mismatches: list[Mismatch] = []

    # Order check: all matched, but in different relative order.
    if len(matches) == len(ref) and len(ref) == len(cand):
        sorted_by_ref = sorted(matches)
        if any(sorted_by_ref[k][1] < sorted_by_ref[k - 1][1] for k in range(1, len(sorted_by_ref))):
            mismatches.append(Mismatch("author_order_wrong", "authors match but order differs"))
        if not mismatches:
            return []

    unmatched_ref = [ref[i] for i in range(len(ref)) if i not in matched_ref]
    unmatched_cand = [cand[j] for j in range(len(cand)) if j not in matched_cand]

    for r in unmatched_ref:
        best = _classify_single_unmatched(r, unmatched_cand)
        if best is None:
            mismatches.append(Mismatch(
                "author_not_found",
                f"{r['first_name']} {r['last_name']} — not in canonical record",
            ))
        else:
            kind, other = best
            mismatches.append(Mismatch(
                kind,
                f"{r['first_name']} {r['last_name']} vs {other['first_name']} {other['last_name']}",
            ))
            unmatched_cand.remove(other)

    return mismatches


def _authors_equivalent(a, b) -> bool:
    if is_name_match(a, b):
        return True
    if names_match_with_accents(a["first_name"], b["first_name"]) and names_match_with_accents(
        a["last_name"], b["last_name"]
    ):
        return True
    a_base, _ = split_last_name_prefix(a["last_name"])
    b_base, _ = split_last_name_prefix(b["last_name"])
    if (
        names_match_with_accents(a["first_name"], b["first_name"])
        and (
            names_match_with_accents(a_base, b_base)
            or names_match_with_accents(a["last_name"], b_base)
            or names_match_with_accents(a_base, b["last_name"])
        )
    ):
        return True
    return False


def _classify_single_unmatched(ref_author, candidates):
    """Find the best partial match and label why it didn't pass."""
    for c in candidates:
        ref_last_n = normalize_for_comparison(ref_author["last_name"])
        c_last_n = normalize_for_comparison(c["last_name"])
        ref_first_n = normalize_for_comparison(ref_author["first_name"])
        c_first_n = normalize_for_comparison(c["first_name"])

        last_match = ref_last_n == c_last_n or names_match_with_accents(
            ref_author["last_name"], c["last_name"]
        )
        first_match = ref_first_n == c_first_n or names_match_with_accents(
            ref_author["first_name"], c["first_name"]
        )

        if last_match and not first_match:
            if initial_matches(ref_author["first_name"], c["first_name"]):
                continue  # actually equivalent; skip
            return "first_name_mismatch", c
        if first_match and not last_match:
            return "last_name_mismatch", c
    return None


# ---------- title / year / venue ----------

def _compare_title(entry: BibEntry, record: CanonicalRecord) -> list[Mismatch]:
    if not entry.title or not record.title:
        return []
    a = " ".join(entry.title.lower().split())
    b = " ".join(record.title.lower().split())
    sim = fuzz.ratio(a, b) / 100.0
    if sim < 0.92:
        return [Mismatch("title_mismatch", f"{entry.title!r} vs {record.title!r} (sim={sim:.2f})")]
    return []


def _compare_year(entry: BibEntry, record: CanonicalRecord) -> list[Mismatch]:
    if entry.year is None or record.year is None:
        return []
    if abs(entry.year - record.year) <= 1:
        return []  # preprint-vs-publication year drift
    return [Mismatch("year_mismatch", f"{entry.year} vs {record.year}")]


_VENUE_ABBREVIATIONS = {
    "neurips": "neural information processing systems",
    "nips": "neural information processing systems",
    "icml": "international conference on machine learning",
    "iclr": "international conference on learning representations",
    "aaai": "aaai conference on artificial intelligence",
    "acl": "association for computational linguistics",
    "emnlp": "empirical methods in natural language processing",
    "cvpr": "computer vision and pattern recognition",
    "facct": "fairness accountability and transparency",
    "fat*": "fairness accountability and transparency",
}

_VENUE_NOISE = re.compile(r"\b(proc\.?|proceedings|of the|conf\.?|conference|the)\b", re.IGNORECASE)

# arXiv has many surface forms across providers/authors, all meaning the same
# preprint server: "arXiv", "CoRR" (DBLP's label), "arXiv preprint arXiv:1234.5678"
# (BibTeX convention), "arXiv (Cornell University)" (OpenAlex), "arXiv: Neural and
# Evolutionary Computing" (Semantic Scholar subject label). Collapse them all so we
# don't flag arXiv-vs-arXiv as a venue mismatch. arXiv-vs-real-venue still differs.
_ARXIV_VENUE = re.compile(r"\barxiv\b|\bcorr\b", re.IGNORECASE)


def _normalize_venue(v: str) -> str:
    v = (v or "").lower().strip()
    if not v:
        return ""
    if _ARXIV_VENUE.search(v):
        return "arxiv"
    for short, long in _VENUE_ABBREVIATIONS.items():
        if v == short or v.startswith(short + " ") or v == long:
            v = long
            break
    v = _VENUE_NOISE.sub(" ", v)
    return " ".join(v.split())


def _compare_venue(entry: BibEntry, record: CanonicalRecord) -> list[Mismatch]:
    if not entry.venue or not record.venue:
        return []  # arXiv records, missing fields → skip
    a = _normalize_venue(entry.venue)
    b = _normalize_venue(record.venue)
    if not a or not b:
        return []
    sim = fuzz.partial_ratio(a, b) / 100.0
    if sim < 0.7:
        return [Mismatch("venue_mismatch", f"{entry.venue!r} vs {record.venue!r}")]
    return []


def compare(entry: BibEntry, record: CanonicalRecord) -> list[Mismatch]:
    return (
        _compare_authors(entry, record)
        + _compare_title(entry, record)
        + _compare_year(entry, record)
        + _compare_venue(entry, record)
    )


def format_suggestion(record: CanonicalRecord, mismatches: list[Mismatch]) -> list[str]:
    """One line per mismatch + a trailing line pointing to the canonical record."""
    lines = [f"{m.kind}: {m.detail}" for m in mismatches]
    pointer_bits = [f"source={record.source}"]
    if record.doi:
        pointer_bits.append(f"doi={record.doi}")
    if record.url:
        pointer_bits.append(f"url={record.url}")
    lines.append("suggested: " + ", ".join(pointer_bits))
    return lines
