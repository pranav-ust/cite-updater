"""Pure name-matching logic. Ported from the research repo's analyze_matches.py."""

from __future__ import annotations

from unidecode import unidecode

from .normalize import Author


def _initials(name: str) -> str:
    normalized = name.replace(".", " ").replace("-", " ").strip()
    out: list[str] = []
    for word in normalized.split():
        if word:
            out.append(unidecode(word[0].lower()))
    return "".join(out)


def is_initial(name: str) -> bool:
    return len(name.replace(".", "").strip()) == 1


def is_compound_initial(name: str) -> bool:
    """Detect patterns like 'K.-T' or 'C.-J' — initials joined by hyphens/periods."""
    cleaned = name.replace(".", "").replace("-", "").strip()
    if 0 < len(cleaned) <= 3 and cleaned.isalpha():
        if "-" in name or ("." in name and len(cleaned) <= 3):
            return True
    return False


def initial_matches(name1: str, name2: str) -> bool:
    """True only when one side is an actual initial (single letter) matching the other.

    Will NOT match 'Jeff' vs 'Jeffrey' — both are full names, not initials.
    """
    n1_is_initial = is_initial(name1) or is_compound_initial(name1)
    n2_is_initial = is_initial(name2) or is_compound_initial(name2)
    if not n1_is_initial and not n2_is_initial:
        return False

    init1, init2 = _initials(name1), _initials(name2)
    if not init1 or not init2:
        return False

    if len(init1) == 1 and len(init2) > 1:
        return init1[0] == init2[0]
    if len(init2) == 1 and len(init1) > 1:
        return init2[0] == init1[0]

    if n1_is_initial and n2_is_initial:
        return (
            init1 == init2
            or (len(init1) == 1 and init1[0] == init2[0])
            or (len(init2) == 1 and init2[0] == init1[0])
        )

    if n1_is_initial:
        return init1[0] == init2[0]
    if n2_is_initial:
        return init2[0] == init1[0]
    return False


def _normalize_component(text: str) -> str:
    return unidecode(text.lower().replace(".", "").replace("-", "").strip())


def _all_parts(author: Author) -> list[str]:
    parts: list[str] = []
    for key in ("first_name", "middle_name", "last_name"):
        if author.get(key):
            parts.extend(unidecode(author[key].lower()).split())
    return parts


def is_name_match(a: Author, b: Author) -> bool:
    """Match two parsed authors allowing for initials, accents, reordering, compound names."""
    a_first = _normalize_component(a["first_name"])
    a_middle = _normalize_component(a["middle_name"])
    a_last = _normalize_component(a["last_name"])
    b_first = _normalize_component(b["first_name"])
    b_middle = _normalize_component(b["middle_name"])
    b_last = _normalize_component(b["last_name"])

    a_parts = [p for p in [a_first, a_middle, a_last] if p]
    b_parts = [p for p in [b_first, b_middle, b_last] if p]

    if set(_all_parts(a)) and set(_all_parts(a)) == set(_all_parts(b)):
        return True

    if a_last and a_last == b_last:
        if a_first and a_first == b_first:
            return True
        if initial_matches(a["first_name"], b["first_name"]):
            return True
        if a_middle and b_first == a_middle:
            return True
        if b_middle and a_first == b_middle:
            return True
        if "".join(a_parts) == "".join(b_parts):
            return True

    if a_first and a_last and a_first == b_last and a_last == b_first:
        return True

    if " ".join(a_parts) == " ".join(b_parts) and a_parts:
        return True

    a_compound = "".join(c for c in f"{a_first}{a_middle}{a_last}" if c.isalnum())
    b_compound = "".join(c for c in f"{b_first}{b_middle}{b_last}" if c.isalnum())
    if a_compound and a_compound == b_compound:
        return True

    return False
