from cite_updater.bib_io import BibEntry
from cite_updater.compare import compare
from cite_updater.providers import CanonicalRecord


def _entry(**overrides):
    base = dict(
        key="x", entry_type="inproceedings",
        title="Attention Is All You Need",
        authors=["Ashish Vaswani", "Noam Shazeer"],
        year=2017, venue="NeurIPS", doi=None, raw=None,
    )
    base.update(overrides)
    return BibEntry(**base)


def _record(**overrides):
    base = dict(
        title="Attention Is All You Need",
        authors=["Ashish Vaswani", "Noam Shazeer"],
        year=2017, venue="Neural Information Processing Systems",
        doi="10.x/y", url=None, source="test",
    )
    base.update(overrides)
    return CanonicalRecord(**base)


def test_perfect_match_yields_no_mismatches():
    assert compare(_entry(), _record()) == []


def test_first_name_typo_flagged():
    e = _entry(authors=["Asheesh Vaswani", "Noam Shazeer"])
    kinds = [m.kind for m in compare(e, _record())]
    assert "first_name_mismatch" in kinds


def test_missing_author_flagged():
    e = _entry(authors=["Ashish Vaswani"])
    kinds = [m.kind for m in compare(e, _record())]
    # The extra author from the record becomes unmatched — but we only check ref→cand direction,
    # so a too-short ref list with all matched yields no mismatch. Verify no false positive.
    assert "author_not_found" not in kinds


def test_extra_wrong_author_flagged():
    e = _entry(authors=["Ashish Vaswani", "Noam Shazeer", "Jeff Sun"])
    r = _record(authors=["Ashish Vaswani", "Noam Shazeer", "Jian Sun"])
    kinds = [m.kind for m in compare(e, r)]
    assert "first_name_mismatch" in kinds


def test_missing_accent_surfaced_as_suggestion():
    # Citation dropped the diacritic the canonical record carries → still a match,
    # but flagged as accents_missing.
    e = _entry(authors=["Yoshua Bengio", "Asheesh Vaswani"])
    r = _record(authors=["Yoshua Bengío", "Asheesh Vaswani"])
    kinds = [m.kind for m in compare(e, r)]
    assert "accents_missing" in kinds
    assert "author_not_found" not in kinds  # still counts as the same author
    detail = next(m.detail for m in compare(e, r) if m.kind == "accents_missing")
    assert "Bengio" in detail and "Bengío" in detail


def test_accent_present_in_entry_not_flagged():
    # Reference already has the accents (or richer than canonical) → no suggestion.
    e = _entry(authors=["Yoshua Bengío"])
    r = _record(authors=["Yoshua Bengio"])
    assert all(m.kind != "accents_missing" for m in compare(e, r))


def test_case_only_difference_not_treated_as_accent():
    e = _entry(authors=["yoshua bengio"])
    r = _record(authors=["Yoshua Bengio"])
    assert all(m.kind != "accents_missing" for m in compare(e, r))


def test_year_is_never_compared():
    # Year differences are intentionally ignored (preprint/reprint drift).
    e = _entry(year=2017)
    for ry in (2018, 2020, 1999):
        r = _record(year=ry)
        assert all(m.kind != "year_mismatch" for m in compare(e, r))


def test_title_mismatch_flagged():
    e = _entry(title="Attention Is What You Don't Need")
    assert any(m.kind == "title_mismatch" for m in compare(e, _record()))


def test_venue_abbreviation_matches():
    # NeurIPS in entry, full name in record — should not flag.
    e = _entry(venue="NeurIPS")
    r = _record(venue="Advances in Neural Information Processing Systems")
    assert all(m.kind != "venue_mismatch" for m in compare(e, r))


def test_venue_unrelated_flagged():
    e = _entry(venue="ICML")
    r = _record(venue="Neural Information Processing Systems")
    assert any(m.kind == "venue_mismatch" for m in compare(e, r))


def test_arxiv_venue_synonyms_not_flagged():
    # All of these mean "arXiv" and should collapse together, not flag.
    arxiv_forms = [
        ("ArXiv", "CoRR"),
        ("arXiv preprint arXiv:1506.03365", "arXiv (Cornell University)"),
        ("arXiv: Neural and Evolutionary Computing", "arXiv"),
    ]
    for entry_venue, record_venue in arxiv_forms:
        e = _entry(venue=entry_venue)
        r = _record(venue=record_venue)
        assert all(m.kind != "venue_mismatch" for m in compare(e, r)), (entry_venue, record_venue)


def test_arxiv_vs_real_venue_still_flagged():
    # Entry cites the arXiv preprint when a real venue exists → keep flagging
    # ("cite the actual venue" nudge).
    e = _entry(venue="ArXiv")
    r = _record(venue="International Conference on Learning Representations")
    assert any(m.kind == "venue_mismatch" for m in compare(e, r))


def test_real_venue_vs_nonselective_host_not_flagged():
    # Entry already cites the real venue; provider only offers a preprint server
    # or institutional repository (arXiv, bioRxiv, an institutional "Research
    # Explorer", SSRN, …). That's the provider being unhelpful → suppress.
    host_venues = [
        "arXiv (Cornell University)",
        "Edinburgh Research Explorer (University of Edinburgh)",
        "bioRxiv",
        "SSRN Electronic Journal",
    ]
    for record_venue in host_venues:
        e = _entry(venue="International Conference on Learning Representations")
        r = _record(venue=record_venue)
        assert all(m.kind != "venue_mismatch" for m in compare(e, r)), record_venue


def test_entry_cites_preprint_server_still_flagged():
    # Reverse direction: the citation uses the preprint server but a real venue
    # exists → keep the "cite the actual venue" nudge.
    for entry_venue in ("ArXiv", "bioRxiv"):
        e = _entry(venue=entry_venue)
        r = _record(venue="International Conference on Learning Representations")
        assert any(m.kind == "venue_mismatch" for m in compare(e, r)), entry_venue


def test_journal_abbreviations_not_flagged():
    # DBLP/IEEE-style abbreviations (truncated words + periods) should match.
    pairs = [
        ("Appl. Math. Comput.", "Applied Mathematics and Computation"),
        ("IEEE Trans. Pattern Anal. Mach. Intell.",
         "IEEE Transactions on Pattern Analysis and Machine Intelligence"),
        ("North American Chapter of the Association for Computational Linguistics",
         "NAACL-HLT"),
    ]
    for entry_venue, record_venue in pairs:
        e = _entry(venue=entry_venue)
        r = _record(venue=record_venue)
        assert all(m.kind != "venue_mismatch" for m in compare(e, r)), (entry_venue, record_venue)


def test_distinct_venues_not_treated_as_abbreviation():
    # Genuinely different venues must still flag, not be excused as abbreviations.
    e = _entry(venue="Neural Information Processing Systems")
    r = _record(venue="International Conference on Machine Learning")
    assert any(m.kind == "venue_mismatch" for m in compare(e, r))
