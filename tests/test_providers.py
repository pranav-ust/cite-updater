import responses

from cite_updater.bib_io import BibEntry
from cite_updater.http_client import build_session
from cite_updater.providers.crossref import CROSSREF_API, CrossrefProvider
from cite_updater.providers.dblp import DBLP_API, DblpProvider


def _entry():
    return BibEntry(
        key="x", entry_type="inproceedings",
        title="Attention Is All You Need",
        authors=["Ashish Vaswani", "Noam Shazeer"],
        year=2017, venue=None, doi=None, raw=None,
    )


@responses.activate
def test_dblp_returns_record_on_confident_match():
    responses.get(
        DBLP_API,
        json={
            "result": {
                "hits": {
                    "hit": [{
                        "info": {
                            "title": "Attention Is All You Need.",
                            "authors": {"author": [
                                {"text": "Ashish Vaswani"},
                                {"text": "Noam Shazeer"},
                            ]},
                            "year": "2017",
                            "venue": "NeurIPS",
                            "doi": "10.x/y",
                            "ee": "https://arxiv.org/abs/1706.03762",
                            "key": "conf/nips/VaswaniSPUJGKP17",
                        }
                    }]
                }
            }
        },
    )
    p = DblpProvider(session=build_session(cache=False))
    p.limiter.min_interval = 0  # don't sleep in tests
    rec = p.search(_entry())
    assert rec is not None
    assert rec.doi == "10.x/y"
    assert rec.source.startswith("dblp:")


@responses.activate
def test_dblp_returns_none_on_low_similarity():
    responses.get(
        DBLP_API,
        json={"result": {"hits": {"hit": [{"info": {
            "title": "An Unrelated Paper About Bananas",
            "authors": {"author": [{"text": "Some Person"}]},
            "year": "2017",
        }}]}}},
    )
    p = DblpProvider(session=build_session(cache=False))
    p.limiter.min_interval = 0
    assert p.search(_entry()) is None


@responses.activate
def test_crossref_parses_doi():
    responses.get(
        CROSSREF_API,
        json={"message": {"items": [{
            "DOI": "10.x/y",
            "title": ["Attention Is All You Need"],
            "author": [
                {"given": "Ashish", "family": "Vaswani"},
                {"given": "Noam", "family": "Shazeer"},
            ],
            "issued": {"date-parts": [[2017]]},
            "container-title": ["NeurIPS"],
            "URL": "https://doi.org/10.x/y",
        }]}},
    )
    p = CrossrefProvider(session=build_session(cache=False))
    p.limiter.min_interval = 0
    rec = p.search(_entry())
    assert rec is not None
    assert rec.doi == "10.x/y"
    assert rec.year == 2017
