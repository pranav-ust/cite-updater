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
pip install cite-updater          # not yet published — for now, see "From source"
```

From source:

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
| `first_name_mismatch` / `last_name_mismatch` | Same author, name differs (incl. typos, missing accents). |
| `author_not_found` | A cited author has no counterpart in the canonical record. |
| `author_order_wrong` | All authors match but in a different order. |
| `parsing_error` | The bib author field has unparseable junk (`*`, fragments, etc.). |
| `title_mismatch` | Cited title vs canonical title fuzzy ratio < 0.92. |
| `venue_mismatch` | Cited venue doesn't match canonical, after expanding common abbreviations (NeurIPS ↔ Neural Information Processing Systems, etc.) and collapsing arXiv synonyms. |

Year is deliberately not compared — preprint, camera-ready, and reprint years
diverge legitimately and too often to be a useful signal.

No LLM, no GPU. The categories come from rule-based comparison only.

## Development

```bash
pip install -e .[dev]
pytest
```

## Roadmap

Planned work is tracked in [GitHub Issues](https://github.com/pranav-ust/cite-updater/issues).
Headline items: arXiv source-bundle ingest (parse the author's original
`references.bib` straight out of the `.tar.gz`) and an `--apply` mode that
rewrites entries with canonical values.

## License

MIT.
