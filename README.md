# cite-updater

Check a BibTeX file against bibliographic APIs and flag entries whose authors,
title, or venue disagree with the canonical record. The original `.bib` is never
modified — `cite-updater` writes a new file with `@comment` suggestions above
each suspect entry. No LLM, no GPU; rule-based comparison only.

Lookup chain: **DBLP → OpenAlex → CrossRef → arXiv → Semantic Scholar**. The
first provider returning a confident match (title fuzz ≥ 0.85 and ≥ 1 author
overlap) wins.

## Install

```bash
git clone https://github.com/pranav-ust/cite-updater
cd cite-updater
pip install -e .
```

## Usage

```bash
cite-updater refs.bib -o refs.corrected.bib
```

Flags: `--providers dblp,arxiv` (restrict/reorder the chain), `--no-cache`,
`--no-progress`, `-v`/`-vv`.

## What gets flagged

| Kind | When |
|------|------|
| `first_name_mismatch` / `last_name_mismatch` | Same author, name differs (typo, dropped initial). |
| `accents_missing` | Citation dropped diacritics the record carries (`Bengio` → `Bengío`). |
| `author_not_found` | A cited author has no counterpart in the record. |
| `author_order_wrong` | All authors match, different order. |
| `parsing_error` | Author field has unparseable junk. |
| `title_mismatch` | Title fuzz < 0.92. |
| `venue_mismatch` | Venue disagrees after expanding abbreviations and collapsing arXiv synonyms. |
| `preprint_published` | Venue-less arXiv entry the record shows was published — suggests the real venue. |

Year is not compared (preprint/camera-ready/reprint years diverge too often).

## Development

```bash
pip install -e .[dev]
pytest
```

## License

MIT.
