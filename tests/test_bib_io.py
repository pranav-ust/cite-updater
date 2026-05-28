from pathlib import Path

from cite_updater.bib_io import annotate, iter_entries, read_bib, write_bib

FIXTURE = Path(__file__).parent / "fixtures" / "sample.bib"


def test_read_entries_basic():
    lib = read_bib(FIXTURE)
    entries = list(iter_entries(lib))
    assert len(entries) == 2

    vaswani = next(e for e in entries if e.key == "vaswani2017attention")
    assert vaswani.title == "Attention Is All You Need"
    assert vaswani.year == 2017
    assert vaswani.venue == "Advances in Neural Information Processing Systems"
    assert "Ashish Vaswani" in vaswani.authors
    assert len(vaswani.authors) == 8


def test_annotate_and_write_roundtrip(tmp_path):
    lib = read_bib(FIXTURE)
    annotate(lib, "he2016deep", ["first_name_mismatch: Jeff Sun vs Jian Sun", "suggested: doi=10.1109/CVPR.2016.90"])

    out = tmp_path / "out.bib"
    write_bib(lib, out)
    text = out.read_text()
    assert "cite-updater suggestion for he2016deep" in text
    assert "Jeff Sun vs Jian Sun" in text
    # Original entries still present.
    assert "@inproceedings{he2016deep" in text
    assert "@inproceedings{vaswani2017attention" in text
