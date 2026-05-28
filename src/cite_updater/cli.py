"""Command-line entry point: cite-updater input.bib -o corrected.bib."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .bib_io import annotate, iter_entries, read_bib, write_bib
from .compare import compare, format_suggestion
from .http_client import build_session
from .providers import DEFAULT_CHAIN, build_chain, run_chain

log = logging.getLogger("cite_updater")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cite-updater",
        description="Check BibTeX entries against bibliographic APIs and annotate suspect ones.",
    )
    parser.add_argument("input", type=Path, help="Input .bib file")
    parser.add_argument(
        "-o", "--output", type=Path, required=True,
        help="Output .bib file (original is never modified)",
    )
    parser.add_argument(
        "--providers", default=",".join(DEFAULT_CHAIN),
        help=f"Comma-separated provider chain (default: {','.join(DEFAULT_CHAIN)})",
    )
    parser.add_argument("--no-cache", action="store_true", help="Disable on-disk HTTP cache")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING - 10 * min(args.verbose, 2),
        format="%(levelname)s %(name)s: %(message)s",
    )

    library = read_bib(args.input)
    session = build_session(cache=not args.no_cache)
    chain = build_chain([p.strip() for p in args.providers.split(",") if p.strip()], session)

    n_total = n_suspect = n_unmatched = n_ok = 0
    for bib in iter_entries(library):
        n_total += 1
        record = run_chain(chain, bib)
        if record is None:
            n_unmatched += 1
            log.info("no provider matched: %s", bib.key)
            continue
        mismatches = compare(bib, record)
        if not mismatches:
            n_ok += 1
            continue
        n_suspect += 1
        annotate(library, bib.key, format_suggestion(record, mismatches))
        log.info("flagged %s (%d issues)", bib.key, len(mismatches))

    write_bib(library, args.output)
    print(
        f"{n_total} entries: {n_ok} OK, {n_suspect} suspect, {n_unmatched} unmatched "
        f"→ {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
