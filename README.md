# cite-updater

Check a BibTeX file against bibliographic APIs (DBLP → CrossRef → OpenAlex →
arXiv → Semantic Scholar) and flag entries whose authors, title, or venue
disagree with the canonical record. Your `.bib` is never modified —
suggestions are written to a new file as `@comment` blocks. No LLM, no GPU.

This tool accompanies our FAccT paper on citation accuracy in ML scholarship.

## Install

```bash
git clone https://github.com/pranav-ust/cite-updater
cd cite-updater
pip install -e .
```

## Check your bib

```bash
cite-updater refs.bib -o refs.checked.bib
```

Try it on a sample from [`examples/`](examples/):

```bash
cite-updater examples/acl_paper.bib -o /tmp/out.bib -v
```

## Your output

Each suspect entry gets a `@comment` suggestion prepended; the original entry is
left untouched, so you review and fix by hand:

```bibtex
@comment{cite-updater suggestion for he2016deep:
  first_name_mismatch: Jeff Sun vs Jian Sun
  suggested: source=dblp:conf/cvpr/HeZRS16, doi=10.1109/CVPR.2016.90}

@inproceedings{he2016deep,
  author = {Kaiming He and Xiangyu Zhang and Shaoqing Ren and Jeff Sun},
  ...
}
```

It flags author-name typos, missing diacritics, wrong/missing authors, author
order, title and venue mismatches, and arXiv preprints that were later
published. Year is not compared. Run `cite-updater --help` for flags.

## Development

```bash
pip install -e .[dev]
pytest
```

## License

MIT.
