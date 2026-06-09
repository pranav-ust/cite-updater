import responses

from cite_updater.bib_io import BibEntry
from cite_updater.http_client import build_session
from cite_updater.providers.crossref import CROSSREF_API, CrossrefProvider
from cite_updater.providers.openalex import OPENALEX_API, OpenAlexProvider
from cite_updater.providers.semantic_scholar import S2_API, SemanticScholarProvider


def _entry():
    return BibEntry(
        key="x", entry_type="inproceedings",
        title="Attention Is All You Need",
        authors=["Ashish Vaswani", "Noam Shazeer"],
        year=2017, venue=None, doi=None, raw=None,
    )


@responses.activate
def test_openalex_adds_mailto_when_set(monkeypatch):
    monkeypatch.setenv("CITE_UPDATER_MAILTO", "me@example.com")
    responses.get(OPENALEX_API, json={"results": []})
    p = OpenAlexProvider(session=build_session(cache=False))
    p.limiter.min_interval = 0
    p.search(_entry())
    assert "mailto=me%40example.com" in responses.calls[-1].request.url


@responses.activate
def test_openalex_no_mailto_when_unset(monkeypatch):
    monkeypatch.delenv("CITE_UPDATER_MAILTO", raising=False)
    responses.get(OPENALEX_API, json={"results": []})
    p = OpenAlexProvider(session=build_session(cache=False))
    p.limiter.min_interval = 0
    p.search(_entry())
    assert "mailto" not in responses.calls[-1].request.url


@responses.activate
def test_crossref_adds_mailto_when_set(monkeypatch):
    monkeypatch.setenv("CITE_UPDATER_MAILTO", "me@example.com")
    responses.get(CROSSREF_API, json={"message": {"items": []}})
    p = CrossrefProvider(session=build_session(cache=False))
    p.limiter.min_interval = 0
    p.search(_entry())
    assert "mailto=me%40example.com" in responses.calls[-1].request.url


@responses.activate
def test_crossref_no_mailto_when_unset(monkeypatch):
    monkeypatch.delenv("CITE_UPDATER_MAILTO", raising=False)
    responses.get(CROSSREF_API, json={"message": {"items": []}})
    p = CrossrefProvider(session=build_session(cache=False))
    p.limiter.min_interval = 0
    p.search(_entry())
    assert "mailto" not in responses.calls[-1].request.url


@responses.activate
def test_user_agent_includes_mailto_when_set(monkeypatch):
    monkeypatch.setenv("CITE_UPDATER_MAILTO", "me@example.com")
    responses.get(OPENALEX_API, json={"results": []})
    p = OpenAlexProvider(session=build_session(cache=False))
    p.limiter.min_interval = 0
    p.search(_entry())
    assert "mailto:me@example.com" in responses.calls[-1].request.headers["User-Agent"]


@responses.activate
def test_s2_sends_api_key_header_when_set(monkeypatch):
    monkeypatch.setenv("S2_API_KEY", "secret-key")
    responses.get(S2_API, json={"data": []})
    p = SemanticScholarProvider(session=build_session(cache=False))
    p.limiter.min_interval = 0
    p.search(_entry())
    assert responses.calls[-1].request.headers.get("x-api-key") == "secret-key"


@responses.activate
def test_s2_no_api_key_header_when_unset(monkeypatch):
    monkeypatch.delenv("S2_API_KEY", raising=False)
    responses.get(S2_API, json={"data": []})
    p = SemanticScholarProvider(session=build_session(cache=False))
    p.limiter.min_interval = 0
    p.search(_entry())
    assert "x-api-key" not in responses.calls[-1].request.headers
