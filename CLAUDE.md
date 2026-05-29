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
test_files/
  neurips.bib        Combined 57-entry BibTeX file (NeurIPS 2023 papers from arXiv)
  acl.bib            Combined 65-entry BibTeX file (ACL 2024 papers from arXiv)
  neurips/*.bib      Same entries, one .bib per paper, named by arXiv id
  acl/*.bib
```

`test_files/` is real-world input for the CLI — DBLP-titled NeurIPS/ACL papers
matched to arXiv via fuzzy title search (≥85% Levenshtein), then serialized
as `@misc{}` entries with `archivePrefix = {arXiv}`. Useful for end-to-end
smoke runs:

```bash
cite-updater test_files/neurips.bib -o /tmp/neurips_annotated.bib -v
```

## Pipeline

```
bib → parse → for each entry:
                 chain: dblp → openalex → crossref → arxiv → semantic_scholar
                 first confident match wins (title fuzz ≥ 0.85 AND ≥1 author overlap)
                 if no match → leave entry alone
                 if match → compare(entry, record) → list[Mismatch]
                            if mismatches → annotate with @comment + DOI/URL
              → write out
```

No LLM. No GPU. No DBLP XML dump. Just HTTP + string comparison.

## Conventions to preserve

- **Provider chain order matters.** DBLP first as the strongest published-venue
  check for ML/CS bibs; OpenAlex and CrossRef next for broader coverage and DOIs.
  arXiv is fourth — it's frequently rate-limited (429s / read timeouts) and for
  arXiv-sourced `.bib` entries it tends to echo the cited metadata back rather
  than provide an independent canonical record. Semantic Scholar is the fallback.
  Don't reorder casually.
- **`is_confident_match` requires both title sim AND author overlap.** Title-only
  matches give false positives on conference-proceedings entries that share a
  template title. Don't relax to title-only.
- **Year is not compared** — preprint/camera-ready/reprint years diverge too
  often to signal anything. `year_mismatch` was removed from `compare()`.
- **Venue comparison strips abbreviations** (NeurIPS ↔ Neural Information
  Processing Systems) and collapses arXiv synonyms (`arXiv`/`CoRR`/`arXiv
  (Cornell University)`/`arXiv preprint arXiv:NNNN.NNNN` → `arxiv`). Add new
  abbreviations in `compare.py:_VENUE_ABBREVIATIONS`.
- **`initial_matches` only fires when one side is a single-letter initial.**
  "Jeff" vs "Jeffrey" intentionally does NOT match — those are different names.
- **The original `.bib` is never modified.** Output goes to a separate file.
- **Per-provider rate limiters with adaptive backoff** (`http_client.py:RateLimiter`).
  Each provider sets a base gap (arXiv 3s, DBLP 1.1s, S2 1s, OpenAlex/CrossRef
  0.1s) plus `max_interval` + `backoff_sleep`. `limiter.request(fetch)` wraps the
  HTTP call: on a `RequestException` it doubles the gap (capped at `max_interval`),
  sleeps `backoff_sleep`, retries once, then decays back toward base on success.
  All five providers route through this. Don't run providers in parallel without
  rethinking the shared limiter state.

## Dev workflow

```bash
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest                                 # 22 tests
.venv/bin/cite-updater tests/fixtures/sample.bib -o /tmp/out.bib -v
```

The HTTP cache lives at `~/.cache/cite-updater/http.sqlite` (30-day TTL).
`--no-cache` bypasses it. Tests use `responses` to mock HTTP — don't hit the
real network in tests.

## Wild-bib experiment (2026-05-28)

To stress-test against real handwritten `.bib` files (the existing
`test_files/{acl,neurips}/*.bib` are canonical-metadata round-trips from DBLP →
arXiv, so cite-updater can't catch typos/accents/initials in them), 122 arXiv
source tarballs were fetched via `scripts/fetch_arxiv_sources.py`. 110/122
(90%) yielded a `.bib`, but the count is inflated by canonical dumps —
`anthology.bib` (full ACL Anthology, ~46MB ×25 copies), `neurips_2023.bib`,
`neurips_2022.bib`. After filtering those plus any `.bib >1MB` (safe ceiling
for hand-written references), 101 papers / 105 files / **14,401 entries**
remained. Per-paper output is in `data/arxiv_source_bibs/<arxiv-id>/` (gitignored).

Two random-100 samples with `--no-cache` gave:

| sample | OK | suspect | unmatched | dblp fails | s2 fails | arxiv fails |
|--------|----|---------|-----------|------------|----------|-------------|
| 1 (pre-backoff)  | 21 | 15 | 66 | 17 | 46 | 4  |
| 2 (post-backoff) | 19 | 13 | 68 |  6 | 38 | 23 |

Adaptive backoff now lives in **both** `providers/dblp.py` and
`providers/arxiv.py`: on `RequestException` each doubles its `min_interval`
(DBLP cap 8s, arXiv cap 30s), sleeps (10s / 15s), retries once, then decays back
toward baseline on success. DBLP backoff cut DBLP failures ~3× (17→6). arXiv
throttles by IP across runs, so repeated full-chain runs in one day still trip
its 429 limit — the backoff degrades gracefully instead of burning 4 fast
retries, but doesn't undo the server-side throttle.

### Findings — fixed

- **arXiv venue synonyms collapsed (`compare.py:_normalize_venue`).** `ArXiv`,
  `CoRR`, `arXiv (Cornell University)`, `arXiv preprint arXiv:NNNN.NNNN`, and
  `arXiv: <subject>` now normalize to one `arxiv` token, killing the single
  biggest `venue_mismatch` false-positive source. arXiv-vs-real-venue (e.g.
  ArXiv vs ICLR) still flags — that's a real catch.
- **OpenAlex over-acceptance fixed (`is_confident_match`).** A single shared
  surname is no longer enough to confirm a multi-author paper: once both sides
  list ≥3 authors, ≥ ceil(min/2) surnames must overlap. The `ouyang2022training`
  (InstructGPT) → unrelated OpenAlex `W7133211372` false match now correctly
  falls through to unmatched. et-al tokens (`others`, `et al`) are excluded from
  the overlap count.
- **Venue/journal abbreviations handled (`compare.py:_is_abbreviation`).** Punctuation
  is stripped during normalization and a token-prefix subsequence matcher accepts
  DBLP/IEEE-style abbreviations: `Appl. Math. Comput.` ↔ `Applied Mathematics and
  Computation`, `IEEE Trans. Pattern Anal. Mach. Intell.` ↔ the full name. NAACL
  was added to `_VENUE_ABBREVIATIONS` (irregular acronym, not prefix-derivable).
- **Adaptive backoff on all five providers** (was DBLP + arXiv only). Folded into
  the shared `http_client.py:RateLimiter.request`; each provider just sets base /
  max / sleep.

### Findings — still open / informational

- **Provider-returned junk venues still slip through.** OpenAlex sometimes returns
  an institutional repository as the venue (e.g. `Edinburgh Research Explorer
  (University of Edinburgh)` for an ICLR paper), which flags as `venue_mismatch`.
  Not an abbreviation, so `_is_abbreviation` can't fix it; would need to distrust
  OpenAlex's venue field for repository-like names. Low frequency, left as-is.

- **Most "unmatched" entries are legit, not a bug.** Spot-checking sample 2:
  workshop papers, pre-2010 NLP references, niche math books (Bakry-Gentil-Ledoux
  2014), and theses don't appear in DBLP/OpenAlex/CrossRef.
- **Real catches that justify the tool:** `Katie Millican` → `Katherine Millican`,
  `Ves Stoyanov` → `Veselin Stoyanov`, `Alex Nichol` → `Alexander Nichol`,
  multiple entries citing the arXiv preprint when the paper actually appeared at
  NeurIPS/ICLR/IJCAI. The arXiv-vs-real-venue flags are kept on purpose.
- **Year is not compared at all.** Preprint vs camera-ready vs reprint years
  diverge legitimately and too often to be useful; `year_mismatch` was removed
  from `compare()`. Don't reintroduce a year check.

## Open work

Tracked in GitHub Issues. Highlights:

- arXiv source-bundle ingest (parse the author's original `references.bib`/`.bbl`
  from the arXiv source tarball — stronger than any API). Prototype lives in
  `scripts/fetch_arxiv_sources.py`; see above.
- `--apply` mode that rewrites suspect entries with canonical values.

**Explicitly out of scope:** LLM-based categorisation. This package stays
rule-based / LLM-free. The research repo (`cite--updater`, double dash) is
where any LLM work lives.
