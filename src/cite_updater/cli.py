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
    parser.add_argument(
        "--no-progress", action="store_true",
        help="Disable the progress indicator (also off automatically when stdin is closed)",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0)
    return parser


class _Progress:
    """Dependency-free progress indicator written to stderr.

    On a TTY it draws an in-place bar; when stderr is redirected (e.g. to a log
    file) it emits one greppable ``PROGRESS i/n …`` line per entry instead, so
    background runs stay observable without a carriage-return mess in the file.
    """

    def __init__(self, total: int, *, stream=sys.stderr, enabled: bool = True):
        self.total = total
        self.stream = stream
        self.is_tty = bool(getattr(stream, "isatty", lambda: False)())
        self.enabled = enabled and total > 0
        self.ok = self.suspect = self.unmatched = 0

    def update(self, *, ok: int, suspect: int, unmatched: int) -> None:
        self.ok, self.suspect, self.unmatched = ok, suspect, unmatched
        if not self.enabled:
            return
        done = ok + suspect + unmatched
        if self.is_tty:
            width = 24
            filled = round(width * done / self.total)
            bar = "█" * filled + "·" * (width - filled)
            self.stream.write(
                f"\r[{bar}] {done}/{self.total} ({done / self.total:.0%})  "
                f"ok={ok} suspect={suspect} unmatched={unmatched}  "
            )
            if done == self.total:
                self.stream.write("\n")
        else:
            self.stream.write(
                f"PROGRESS {done}/{self.total} ok={ok} suspect={suspect} unmatched={unmatched}\n"
            )
        self.stream.flush()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING - 10 * min(args.verbose, 2),
        format="%(levelname)s %(name)s: %(message)s",
    )

    library = read_bib(args.input)
    session = build_session(cache=not args.no_cache)
    chain = build_chain([p.strip() for p in args.providers.split(",") if p.strip()], session)

    entries = list(iter_entries(library))
    progress = _Progress(len(entries), enabled=not args.no_progress)

    n_suspect = n_unmatched = n_ok = 0
    for bib in entries:
        record = run_chain(chain, bib)
        if record is None:
            n_unmatched += 1
            log.info("no provider matched: %s", bib.key)
        else:
            mismatches = compare(bib, record)
            if not mismatches:
                n_ok += 1
            else:
                n_suspect += 1
                annotate(library, bib.key, format_suggestion(record, mismatches))
                log.info("flagged %s (%d issues)", bib.key, len(mismatches))
        progress.update(ok=n_ok, suspect=n_suspect, unmatched=n_unmatched)

    n_total = len(entries)
    write_bib(library, args.output)
    print(
        f"{n_total} entries: {n_ok} OK, {n_suspect} suspect, {n_unmatched} unmatched "
        f"→ {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
