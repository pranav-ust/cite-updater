# cite-updater

Check a BibTeX file against bibliographic APIs and flag entries whose authors,
title, or venue disagree with what the API says. The original `.bib` is
never modified — `cite-updater` writes a new file with `@comment` blocks
attached to each suspect entry, pointing to the canonical DOI/URL so you can
review and fix by hand.

The lookup chain is **DBLP → OpenAlex → CrossRef → arXiv → Semantic Scholar**.
The first provider to return a confident match (title fuzzy ratio ≥ 0.85 and at
least one author overlap) wins.

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

Useful flags:

- `--providers arxiv,dblp` — restrict / reorder the chain.
- `--no-cache` — bypass the on-disk HTTP cache (defaults to
  `~/.cache/cite-updater/http.sqlite`, 30 day TTL).
- `--no-progress` — disable the progress indicator (an in-place bar on a TTY,
  or one greppable `PROGRESS i/n …` line per entry when stderr is redirected).
- `-v` / `-vv` — increase verbosity.

Example annotated output:

```bibtex
@comment{cite-updater suggestion for he2016deep:
  first_name_mismatch: Jeff Sun vs Jian Sun
  suggested: source=dblp:conf/cvpr/HeZRS16, doi=10.1109/CVPR.2016.90
}
@inproceedings{he2016deep,
  author    = {Kaiming He and Xiangyu Zhang and Shaoqing Ren and Jeff Sun},
  ...
}
```

## What gets flagged

| Kind | When |
|------|------|
| `first_name_mismatch` / `last_name_mismatch` | Same author, name differs (e.g. a typo or a dropped initial). |
| `accents_missing` | Same author, but the citation dropped diacritics the canonical record carries (e.g. `Bengio` → `Bengío`). Still counts as a match. |
| `author_not_found` | A cited author has no counterpart in the canonical record. |
| `author_order_wrong` | All authors match but in a different order. |
| `parsing_error` | The bib author field has unparseable junk (`*`, fragments, etc.). |
| `title_mismatch` | Cited title vs canonical title fuzzy ratio < 0.92. |
| `venue_mismatch` | Cited venue doesn't match canonical, after expanding common abbreviations (NeurIPS ↔ Neural Information Processing Systems, etc.) and collapsing arXiv synonyms. |
| `preprint_published` | Entry is an arXiv preprint with no venue, but the matched record (e.g. DBLP) shows it was published somewhere — suggests citing the published venue. No extra lookup; uses the record already matched. |

Year is deliberately not compared — preprint, camera-ready, and reprint years
diverge legitimately and too often to be a useful signal.

No LLM, no GPU. The categories come from rule-based comparison only.

## Development

```bash
pip install -e .[dev]
pytest
```

## License

MIT.
