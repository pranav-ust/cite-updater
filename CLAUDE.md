# CLAUDE.md

Guidance for Claude Code working in this repo.

## What this is

`cite-updater` is a small CLI that validates a `.bib` file against bibliographic
APIs and annotates suspect entries with the canonical record. The original
`.bib` is never modified — the tool writes a new file with `@comment` blocks
prepended to suspect entries.

This is the **public** sister repo of
`https://github.com/pranav-ust/cite--updater` (double dash), which holds a much
larger research pipeline (PDF download → GROBID → DBLP-XML validation → LLM
classification). The matching/normalization logic here was ported from that
repo's `src/analyze_matches.py` and `src/validate_citations.py`; everything
else (BibTeX I/O, HTTP providers, CLI) is new.

## Layout

```
src/cite_updater/
  normalize.py       Author-string → structured fields (HumanName + unidecode)
  matchers.py        Pure name-matching: is_name_match, initial_matches, ...
  bib_io.py          bibtexparser v2 read/write + annotate()
  http_client.py     Shared requests.Session with retry + requests-cache
  compare.py         Entry vs CanonicalRecord → list[Mismatch]
  cli.py             argparse + orchestration; entry point `cite-updater`
  providers/
    __init__.py      Provider protocol + chain runner
    arxiv.py         http://export.arxiv.org/api/query (Atom via feedparser)
    dblp.py          https://dblp.org/search/publ/api
    openalex.py      https://api.openalex.org/works
    crossref.py      https://api.crossref.org/works
    semantic_scholar.py
tests/
  fixtures/sample.bib
  test_matchers.py   test_bib_io.py   test_compare.py   test_providers.py
```

## Pipeline

```
bib → parse → for each entry:
                 chain: arxiv → dblp → openalex → crossref → semantic_scholar
                 first confident match wins (title fuzz ≥ 0.85 AND ≥1 author overlap)
                 if no match → leave entry alone
                 if match → compare(entry, record) → list[Mismatch]
                            if mismatches → annotate with @comment + DOI/URL
              → write out
```

No LLM. No GPU. No DBLP XML dump. Just HTTP + string comparison.

## Conventions to preserve

- **Provider chain order matters.** arXiv first because most ML/CS bibs are
  arXiv-heavy and the arXiv API returns clean author lists. DBLP second as the
  strongest published-venue check. Don't reorder casually.
- **`is_confident_match` requires both title sim AND author overlap.** Title-only
  matches give false positives on conference-proceedings entries that share a
  template title. Don't relax to title-only.
- **Year off-by-one is tolerated** — preprint year vs publication year.
- **Venue comparison strips abbreviations** (NeurIPS ↔ Neural Information
  Processing Systems). Add new abbreviations in `compare.py:_VENUE_ABBREVIATIONS`.
- **`initial_matches` only fires when one side is a single-letter initial.**
  "Jeff" vs "Jeffrey" intentionally does NOT match — those are different names.
- **The original `.bib` is never modified.** Output goes to a separate file.
- **Per-provider rate limiters live in each provider class.** arXiv = 3s gap,
  DBLP = 1.1s, others looser. Don't run providers in parallel without rethinking
  these.

## Dev workflow

```bash
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest                                 # 22 tests
.venv/bin/cite-updater tests/fixtures/sample.bib -o /tmp/out.bib -v
```

The HTTP cache lives at `~/.cache/cite-updater/http.sqlite` (30-day TTL).
`--no-cache` bypasses it. Tests use `responses` to mock HTTP — don't hit the
real network in tests.

## Open work

Tracked in GitHub Issues. Highlights:

- arXiv source-bundle ingest (parse the author's original `references.bib`/`.bbl`
  from the arXiv source tarball — stronger than any API).
- `--apply` mode that rewrites suspect entries with canonical values.

**Explicitly out of scope:** LLM-based categorisation. This package stays
rule-based / LLM-free. The research repo (`cite--updater`, double dash) is
where any LLM work lives.
