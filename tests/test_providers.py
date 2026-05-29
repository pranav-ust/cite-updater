import feedparser
import requests
import responses

from cite_updater.bib_io import BibEntry
from cite_updater.http_client import build_session
from cite_updater.providers import arxiv as arxiv_mod
from cite_updater.providers.arxiv import ArxivProvider
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


def test_arxiv_backoff_widens_and_decays():
    p = ArxivProvider(session=build_session(cache=False))
    base = p.limiter.min_interval
    p._on_failure()
    assert p.limiter.min_interval == base * 2
    for _ in range(10):
        p._on_failure()
    assert p.limiter.min_interval == arxiv_mod._MAX_INTERVAL  # capped
    p._on_success()
    assert p.limiter.min_interval < arxiv_mod._MAX_INTERVAL    # decays
    assert p.limiter.min_interval >= base


def test_arxiv_retries_once_on_throttle(monkeypatch):
    monkeypatch.setattr(arxiv_mod.time, "sleep", lambda *_: None)  # no real backoff sleep
    p = ArxivProvider(session=build_session(cache=False))
    # _fetch is patched below, so limiter.wait() never fires — leave min_interval
    # at the base so the backoff math is observable.
    calls = {"n": 0}

    def flaky_fetch(_title):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.ConnectionError("too many 429 error responses")
        return feedparser.parse("")  # empty feed → no match, but no exception

    p._fetch = flaky_fetch
    assert p.search(_entry()) is None      # retried past the throttle, didn't propagate
    assert calls["n"] == 2                  # one failure + one retry
    assert p.limiter.min_interval >= arxiv_mod._BASE_INTERVAL * 2 * 0.8  # bumped then decayed
