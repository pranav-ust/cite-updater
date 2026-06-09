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
    strip_accents,
)
from .providers import CanonicalRecord


MismatchKind = str  # e.g. "first_name_mismatch", "title_mismatch", "venue_mismatch", ...


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

    # Accent suggestions: matched authors whose canonical form carries diacritics
    # the citation dropped (e.g. "Bengio" cited, "Bengío" canonical). These still
    # count as a match — we just surface the missing accents as a suggestion.
    for i, j in matches:
        detail = _accent_diff(ref[i], cand[j])
        if detail:
            mismatches.append(Mismatch("accents_missing", detail))

    # Order check: all matched, but in different relative order.
    if len(matches) == len(ref) and len(ref) == len(cand):
        sorted_by_ref = sorted(matches)
        if any(sorted_by_ref[k][1] < sorted_by_ref[k - 1][1] for k in range(1, len(sorted_by_ref))):
            mismatches.append(Mismatch("author_order_wrong", "authors match but order differs"))
        return mismatches  # all matched; accent + order findings only (may be empty)

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


def _accent_diff(ref_author, cand_author) -> str | None:
    """If the citation dropped diacritics the canonical record carries, describe it.

    Only fires when the de-accented forms are identical (so it's genuinely the same
    name) and the canonical side actually has accents the reference lacks. Returns
    None for case-only differences or when the reference already has the accents.
    """
    parts: list[str] = []
    for field in ("first_name", "last_name"):
        r = (ref_author[field] or "").strip()
        c = (cand_author[field] or "").strip()
        if not r or not c or r == c:
            continue
        # Same name modulo accents, canonical carries diacritics, and the
        # reference is its de-accented form (case preserved → not a case diff).
        if strip_accents(c) != c and strip_accents(r) == strip_accents(c):
            parts.append(f"{r} → {c}")
    if not parts:
        return None
    return "missing accents: " + ", ".join(parts)


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


# ---------- title / venue ----------
# Year is intentionally not compared: preprint vs camera-ready vs reprint years
# diverge legitimately and too often to be a useful signal.

def _compare_title(entry: BibEntry, record: CanonicalRecord) -> list[Mismatch]:
    if not entry.title or not record.title:
        return []
    a = " ".join(entry.title.lower().split())
    b = " ".join(record.title.lower().split())
    sim = fuzz.ratio(a, b) / 100.0
    if sim < 0.92:
        return [Mismatch("title_mismatch", f"{entry.title!r} vs {record.title!r} (sim={sim:.2f})")]
    return []


# Irregular acronyms whose full form the token-prefix matcher (`_is_abbreviation`)
# cannot derive — i.e. acronyms that aren't built from the leading letters of the
# full venue name. Keys are lowercase short forms, values the lowercase full name.
# For abbreviations the prefix matcher already handles (e.g. truncated journal
# names like "Appl. Math. Comput."), don't add an entry here.
_VENUE_ABBREVIATIONS = {
    # ML / general AI
    "neurips": "neural information processing systems",
    "nips": "neural information processing systems",
    "icml": "international conference on machine learning",
    "iclr": "international conference on learning representations",
    "aaai": "aaai conference on artificial intelligence",
    "ijcai": "international joint conference on artificial intelligence",
    "uai": "uncertainty in artificial intelligence",
    "aistats": "artificial intelligence and statistics",
    "colt": "conference on learning theory",
    "jmlr": "journal of machine learning research",
    "tmlr": "transactions on machine learning research",
    # NLP / computational linguistics
    "acl": "association for computational linguistics",
    "emnlp": "empirical methods in natural language processing",
    "naacl": "north american chapter of the association for computational linguistics",
    "naacl-hlt": "north american chapter of the association for computational linguistics",
    "eacl": "european chapter of the association for computational linguistics",
    "aacl": "asia-pacific chapter of the association for computational linguistics",
    "coling": "international conference on computational linguistics",
    "tacl": "transactions of the association for computational linguistics",
    "cl": "computational linguistics",
    # Vision
    "cvpr": "computer vision and pattern recognition",
    "iccv": "international conference on computer vision",
    "eccv": "european conference on computer vision",
    "tpami": "transactions on pattern analysis and machine intelligence",
    # Data mining / information retrieval / databases
    "kdd": "knowledge discovery and data mining",
    "sigir": "research and development in information retrieval",
    "www": "the web conference",
    "the web conf": "the web conference",
    "wsdm": "web search and data mining",
    "cikm": "information and knowledge management",
    "icde": "international conference on data engineering",
    "vldb": "very large data bases",
    "sigmod": "management of data",
    # Fairness
    "facct": "fairness accountability and transparency",
    "fat*": "fairness accountability and transparency",
}

_VENUE_NOISE = re.compile(r"\b(proc\.?|proceedings|of the|conf\.?|conference|the)\b", re.IGNORECASE)
_VENUE_PUNCT = re.compile(r"[^\w\s]")

# arXiv has many surface forms across providers/authors, all meaning the same
# preprint server: "arXiv", "CoRR" (DBLP's label), "arXiv preprint arXiv:1234.5678"
# (BibTeX convention), "arXiv (Cornell University)" (OpenAlex), "arXiv: Neural and
# Evolutionary Computing" (Semantic Scholar subject label). Collapse them all so we
# don't flag arXiv-vs-arXiv as a venue mismatch. arXiv-vs-real-venue still differs.
_ARXIV_VENUE = re.compile(r"\barxiv\b|\bcorr\b", re.IGNORECASE)

# "Non-selective" hosts: preprint servers, aggregators, and institutional
# repositories that providers (mostly OpenAlex/Semantic Scholar) sometimes return
# as a paper's venue. They don't identify *where a paper was published* — they're
# just where a copy lives. When a provider returns one of these but the citation
# names a real venue, the citation is following good practice (cite the published
# venue); the provider is being unhelpful. We suppress venue_mismatch in that
# direction. "arxiv" (the normalized form above) is the canonical member.
_NONSELECTIVE_VENUE = re.compile(
    r"\barxiv\b|\bbiorxiv\b|\bmedrxiv\b|\bchemrxiv\b|\btechrxiv\b|\bssrn\b"
    r"|research square|preprints?\.org|\bosf\b|\bzenodo\b"
    r"|research explorer|institutional repositor|\bresearchgate\b"
    r"|archives-ouvertes",
    re.IGNORECASE,
)


def _is_nonselective_venue(normalized: str) -> bool:
    return bool(_NONSELECTIVE_VENUE.search(normalized))


def _normalize_venue(v: str) -> str:
    v = (v or "").lower().strip()
    if not v:
        return ""
    if _ARXIV_VENUE.search(v):
        return "arxiv"
    v = _VENUE_PUNCT.sub(" ", v)  # "Appl. Math. Comput." → "appl math comput"
    v = " ".join(v.split())
    for short, long in _VENUE_ABBREVIATIONS.items():
        short = _VENUE_PUNCT.sub(" ", short).strip()
        if v == short or v.startswith(short + " ") or v == long:
            v = long
            break
    v = _VENUE_NOISE.sub(" ", v)
    return " ".join(v.split())


def _is_abbreviation(a: str, b: str) -> bool:
    """True if the shorter venue is a token-wise abbreviation of the longer one.

    Each token of the shorter string must be a prefix of a token in the longer
    string, matched left-to-right (skipping the longer string's extra/stopword
    tokens). Handles DBLP/IEEE-style abbreviations like "IEEE Trans. Pattern
    Anal. Mach. Intell." vs "IEEE Transactions on Pattern Analysis and Machine
    Intelligence", or "Appl. Math. Comput." vs "Applied Mathematics and Computation".
    """
    ta, tb = a.split(), b.split()
    short, long = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(short) < 2 or short == long:
        return False  # single-token abbreviations are too weak to trust
    i = 0
    for token in long:
        if i < len(short) and token.startswith(short[i]):
            i += 1
    return i == len(short)


def _compare_venue(entry: BibEntry, record: CanonicalRecord) -> list[Mismatch]:
    if not record.venue:
        return []  # nothing canonical to compare or suggest
    b = _normalize_venue(record.venue)
    if not b:
        return []
    if not entry.venue:
        # Entry has no venue. If it's an arXiv preprint and the matched record
        # (typically DBLP) names a real published venue, nudge the author to cite
        # that — no extra lookup, it's already on the record we matched.
        if entry.is_preprint and not _is_nonselective_venue(b):
            return [Mismatch("preprint_published", f"published at {record.venue!r}; entry cites the preprint")]
        return []
    a = _normalize_venue(entry.venue)
    if not a:
        return []
    # Asymmetric non-selective-host handling: if the citation names a real venue
    # but the provider only returns a preprint server / institutional repository
    # (e.g. OpenAlex returning "arXiv (Cornell University)" or "Edinburgh Research
    # Explorer" for a NIPS/ICLR paper), that's the provider being unhelpful, not a
    # bad citation — citing the published venue is good practice. Suppress. The
    # reverse (entry cites the preprint, a real venue exists) is still flagged:
    # it's the "cite the actual venue, not the preprint" nudge.
    if _is_nonselective_venue(b) and not _is_nonselective_venue(a):
        return []
    sim = fuzz.partial_ratio(a, b) / 100.0
    if sim >= 0.7 or _is_abbreviation(a, b):
        return []
    return [Mismatch("venue_mismatch", f"{entry.venue!r} vs {record.venue!r}")]


def compare(entry: BibEntry, record: CanonicalRecord) -> list[Mismatch]:
    return (
        _compare_authors(entry, record)
        + _compare_title(entry, record)
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
