"""Fetch arXiv source tarballs for the papers in test_files/{acl,neurips}/ and
extract any *.bib files into data/arxiv_source_bibs/<id>/.

One-off experiment script (not productized). Respects arXiv rate limit (>=3s).
Caches raw downloads under ~/.cache/cite-updater/arxiv-src/.
"""

from __future__ import annotations

import gzip
import io
import json
import shutil
import sys
import tarfile
import time
from collections import Counter
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
TEST_DIRS = [REPO / "test_files" / "acl", REPO / "test_files" / "neurips"]
OUT_ROOT = REPO / "data" / "arxiv_source_bibs"
CACHE_ROOT = Path.home() / ".cache" / "cite-updater" / "arxiv-src"

USER_AGENT = "cite-updater-experiment/0.1 (cs.pranav.a@gmail.com)"
RATE_LIMIT_S = 3.2  # be slightly above 3s


def collect_ids() -> list[tuple[str, str]]:
    ids: list[tuple[str, str]] = []
    for d in TEST_DIRS:
        for f in sorted(d.glob("*.bib")):
            ids.append((d.name, f.stem))
    return ids


def cache_path(arxiv_id: str) -> Path:
    return CACHE_ROOT / arxiv_id


def fetch(arxiv_id: str, session: requests.Session) -> tuple[bytes | None, str]:
    """Return (bytes, status). status in {cached, fetched, http_<code>, error_<msg>}.

    Cached payloads live at CACHE_ROOT/<id>/raw + .meta (content-type).
    """
    cdir = cache_path(arxiv_id)
    raw = cdir / "raw"
    meta = cdir / "meta.json"
    if raw.exists() and meta.exists():
        return raw.read_bytes(), "cached"

    url = f"https://arxiv.org/e-print/{arxiv_id}"
    try:
        r = session.get(url, timeout=60, allow_redirects=True)
    except requests.RequestException as e:
        return None, f"error_{type(e).__name__}"

    if r.status_code != 200:
        return None, f"http_{r.status_code}"
    cdir.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(r.content)
    meta.write_text(json.dumps({
        "content_type": r.headers.get("Content-Type", ""),
        "content_disposition": r.headers.get("Content-Disposition", ""),
        "content_length": len(r.content),
    }))
    return r.content, "fetched"


def sniff_kind(blob: bytes) -> str:
    if len(blob) < 4:
        return "unknown"
    # gzip magic
    if blob[:2] == b"\x1f\x8b":
        # could be .tar.gz or single .gz of a .tex
        try:
            inner = gzip.decompress(blob)
        except OSError:
            return "gzip_corrupt"
        if inner[:8] == b"ustar\x00\x00\x00" or len(inner) > 512 and inner[257:262] == b"ustar":
            return "tar.gz"
        # heuristic: tar files often start with a filename; try opening as tar
        try:
            tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")
            return "tar.gz"
        except tarfile.TarError:
            pass
        return "gz_single"
    if blob[:4] == b"PK\x03\x04":
        return "zip"
    if blob[257:262] == b"ustar":
        return "tar"
    # PDF: many "withdrawn" or no-source arxiv responses return the PDF
    if blob[:4] == b"%PDF":
        return "pdf"
    # Plain text? Look for TeX-ish content
    head = blob[:2048].lower()
    if b"\\documentclass" in head or b"\\begin{document}" in head:
        return "tex_bare"
    return "unknown"


def extract_bibs(blob: bytes, kind: str, out_dir: Path) -> list[Path]:
    """Extract any *.bib files from the source bundle into out_dir.
    Returns list of written paths.
    """
    written: list[Path] = []

    def _write(name: str, data: bytes) -> None:
        # flatten to basename; if collision, prefix with parent
        safe = name.replace("..", "_").replace("/", "__")
        if not safe.lower().endswith(".bib"):
            return
        dest = out_dir / safe
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        written.append(dest)

    if kind == "tar.gz":
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                if m.name.lower().endswith(".bib"):
                    f = tf.extractfile(m)
                    if f is not None:
                        _write(m.name, f.read())
    elif kind == "tar":
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:") as tf:
            for m in tf.getmembers():
                if m.isfile() and m.name.lower().endswith(".bib"):
                    f = tf.extractfile(m)
                    if f is not None:
                        _write(m.name, f.read())
    elif kind == "gz_single":
        # single-file .gz: arXiv only puts a single .tex in this format. No bib.
        return []
    elif kind == "tex_bare":
        return []
    elif kind == "zip":
        import zipfile
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            for n in zf.namelist():
                if n.lower().endswith(".bib"):
                    _write(n, zf.read(n))
    # pdf / unknown / gzip_corrupt → nothing
    return written


def main() -> int:
    ids = collect_ids()
    print(f"Found {len(ids)} arXiv ids across {len(TEST_DIRS)} test_files dirs", flush=True)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    status_counter: Counter[str] = Counter()
    kind_counter: Counter[str] = Counter()
    yield_counter: Counter[str] = Counter()  # has_bib / bbl_only / no_source / pdf_only / unknown / error
    per_paper: list[dict] = []

    last_network = 0.0
    for i, (venue, arxiv_id) in enumerate(ids, 1):
        cached = (cache_path(arxiv_id) / "raw").exists()
        if not cached:
            gap = time.monotonic() - last_network
            if gap < RATE_LIMIT_S:
                time.sleep(RATE_LIMIT_S - gap)
        blob, status = fetch(arxiv_id, session)
        if not cached:
            last_network = time.monotonic()
        status_counter[status] += 1

        record = {"venue": venue, "id": arxiv_id, "fetch": status}

        if blob is None:
            yield_counter["fetch_failed"] += 1
            record["kind"] = None
            record["yield"] = "fetch_failed"
            per_paper.append(record)
            print(f"[{i:3d}/{len(ids)}] {arxiv_id} fetch={status}", flush=True)
            continue

        kind = sniff_kind(blob)
        kind_counter[kind] += 1
        record["kind"] = kind

        out_dir = OUT_ROOT / arxiv_id
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            bibs = extract_bibs(blob, kind, out_dir)
        except Exception as e:
            bibs = []
            record["extract_error"] = f"{type(e).__name__}: {e}"

        # Also note .bbl presence for yield classification
        has_bbl = False
        if kind in {"tar.gz", "tar"}:
            try:
                opener = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz" if kind == "tar.gz" else "r:")
                with opener as tf:
                    for m in tf.getmembers():
                        if m.isfile() and m.name.lower().endswith(".bbl"):
                            has_bbl = True
                            break
            except tarfile.TarError:
                pass

        record["n_bib_files"] = len(bibs)
        record["has_bbl"] = has_bbl

        if bibs:
            yclass = "has_bib"
        elif has_bbl:
            yclass = "bbl_only"
        elif kind == "pdf":
            yclass = "pdf_only"
        elif kind in {"tex_bare", "gz_single"}:
            yclass = "tex_only"
        elif kind == "unknown":
            yclass = "unknown_format"
        else:
            yclass = "no_bib"
        yield_counter[yclass] += 1
        record["yield"] = yclass

        per_paper.append(record)

        # Clean empty out_dir
        if not bibs:
            try:
                out_dir.rmdir()
            except OSError:
                pass

        print(
            f"[{i:3d}/{len(ids)}] {arxiv_id} {status} kind={kind} bibs={len(bibs)} bbl={has_bbl} → {yclass}",
            flush=True,
        )

    # Manifest
    manifest_path = OUT_ROOT / "_manifest.json"
    manifest_path.write_text(json.dumps({
        "n_papers": len(ids),
        "fetch_status": dict(status_counter),
        "bundle_kind": dict(kind_counter),
        "yield": dict(yield_counter),
        "papers": per_paper,
    }, indent=2))

    print("\n=== Summary ===", flush=True)
    print(f"papers attempted     : {len(ids)}", flush=True)
    print(f"fetch status         : {dict(status_counter)}", flush=True)
    print(f"bundle kind          : {dict(kind_counter)}", flush=True)
    print(f"yield                : {dict(yield_counter)}", flush=True)
    print(f"manifest             : {manifest_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
