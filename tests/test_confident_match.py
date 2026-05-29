from cite_updater.bib_io import BibEntry
from cite_updater.providers import CanonicalRecord, author_overlap, is_confident_match


def _entry(authors, title="Training language models to follow instructions"):
    return BibEntry(
        key="x", entry_type="article", title=title,
        authors=authors, year=2022, venue=None, doi=None, raw=None,
    )


def _record(authors, title="Training language models to follow instructions"):
    return CanonicalRecord(
        title=title, authors=authors, year=2022, venue=None,
        doi=None, url=None, source="test",
    )


def test_etal_token_not_counted_as_author():
    assert author_overlap(["Long Ouyang", "and others"], ["Long Ouyang"]) == 1


def test_single_shared_surname_among_many_rejected():
    # InstructGPT-style: title matches, but only 1 of many surnames overlaps.
    entry = _entry(
        ["Long Ouyang", "Jeffrey Wu", "Xu Jiang", "Diogo Almeida",
         "Carroll Wainwright", "Pamela Mishkin", "Chong Zhang"],
    )
    # Unrelated record that happens to share one common surname ("Zhang").
    record = _record(["Wei Zhang", "Hao Li", "Ming Chen", "Yan Wang", "Bo Liu"])
    assert not is_confident_match(entry, record)


def test_strong_overlap_confirmed():
    entry = _entry(["Long Ouyang", "Jeffrey Wu", "Xu Jiang", "Diogo Almeida"])
    record = _record(["Long Ouyang", "Jeff Wu", "Xu Jiang", "Diogo Almeida"])
    assert is_confident_match(entry, record)


def test_single_author_still_needs_one_overlap():
    entry = _entry(["Geoffrey Hinton"])
    record = _record(["Geoffrey Hinton"])
    assert is_confident_match(entry, record)
    record_wrong = _record(["Yann LeCun"])
    assert not is_confident_match(entry, record_wrong)


def test_one_typo_among_several_still_matches():
    # A genuine match with one misspelled surname must survive (the comparator
    # is what flags the typo; the gate should still let it through).
    entry = _entry(["Ashish Vaswanni", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit"])
    record = _record(["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit"])
    assert is_confident_match(entry, record)
