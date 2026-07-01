"""Build the local index from the Corte Costituzionale official open data.

Run:

    it-eli-mcp-caselaw-ingest              # download all eras (1956 -> today) and index
    it-eli-mcp-caselaw-ingest --db PATH    # write to a specific database path
    it-eli-mcp-caselaw-ingest --source FILE.zip [FILE.zip ...]   # index local dumps

The Court publishes decisions as zip-of-zips (an outer archive of per-year archives,
each holding one JSON file with an ``elenco_pronunce`` array). Files are cp1252/latin-1
encoded. We walk the archives recursively, normalize each decision, and build a fresh
SQLite FTS5 database, replacing the target atomically so a failed run never corrupts an
existing index.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx

from . import db
from .records import Decision, normalize_decision

DUMP_URLS: list[str] = [
    "https://dati.cortecostituzionale.it/opendata/distribuzione/pronunce/P_json1956_1980.zip",
    "https://dati.cortecostituzionale.it/opendata/distribuzione/pronunce/P_json1981_2000.zip",
    "https://dati.cortecostituzionale.it/opendata/distribuzione/pronunce/P_json2001_oggi.zip",
]
USER_AGENT = "it-eli-caselaw-mcp/0.1.0 (+https://github.com/matematicsolutions/it-eli-caselaw-mcp)"


def _decode(raw: bytes) -> str:
    """Decode a data file. The Court's JSON is cp1252/latin-1; newer files may be UTF-8."""
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _walk_json(data: bytes) -> Iterator[bytes]:
    """Yield the bytes of every .json file inside a (possibly nested) zip archive."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            inner = zf.read(name)
            lower = name.lower()
            if lower.endswith(".zip"):
                yield from _walk_json(inner)
            elif lower.endswith(".json"):
                yield inner


def _decisions_from_archive(data: bytes) -> Iterator[Decision]:
    for jn in _walk_json(data):
        obj = json.loads(_decode(jn))
        for raw in obj.get("elenco_pronunce", []):
            if not isinstance(raw, dict):
                continue
            try:
                yield normalize_decision(raw)
            except ValueError:
                continue  # skip records with no usable identifier


def _fetch(url: str) -> bytes:
    with httpx.Client(timeout=httpx.Timeout(180.0, connect=15.0),
                      headers={"User-Agent": USER_AGENT}, follow_redirects=True) as c:
        resp = c.get(url)
        resp.raise_for_status()
        return resp.content


def build_index(
    db_path: Path, sources: list[str], *, progress: bool = True
) -> int:
    """Build a fresh index at ``db_path`` from URLs and/or local zip paths."""
    if not db.fts5_available():
        raise RuntimeError("SQLite FTS5 is not available in this Python's sqlite3 build.")

    tmp_path = db_path.with_suffix(db_path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    conn = db.connect(tmp_path, must_exist=False)
    total = 0
    try:
        db.create_schema(conn)
        for src in sources:
            if progress:
                print(f"[ingest] loading {src} ...", file=sys.stderr)
            data = Path(src).read_bytes() if _is_local(src) else _fetch(src)
            batch = list(_decisions_from_archive(data))
            db.insert_decisions(conn, batch)
            total += len(batch)
            if progress:
                print(f"[ingest]   +{len(batch)} decisions (total {total})", file=sys.stderr)
        db.set_meta(conn, "ingested_at", datetime.now(UTC).isoformat(timespec="seconds"))
        db.set_meta(conn, "sources", "; ".join(sources))
        db.set_meta(conn, "count", str(total))
        conn.commit()
    finally:
        conn.close()

    os.replace(tmp_path, db_path)
    if progress:
        print(f"[ingest] done: {total} decisions -> {db_path}", file=sys.stderr)
    return total


def _is_local(src: str) -> bool:
    return not src.lower().startswith(("http://", "https://"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="it-eli-mcp-caselaw-ingest",
        description="Build the Corte Costituzionale case-law index from official open data.",
    )
    parser.add_argument(
        "--db", type=Path, default=None,
        help="database path (default: env IT_ELI_CASELAW_DB / the standard cache path)",
    )
    parser.add_argument(
        "--source", nargs="+", default=None,
        help="local zip file(s) or URL(s) to index instead of the default eras",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress progress output")
    args = parser.parse_args(argv)

    db_path = args.db or db.resolve_db_path()
    sources = args.source or DUMP_URLS
    try:
        n = build_index(db_path, sources, progress=not args.quiet)
    except Exception as exc:  # CLI boundary: report any failure and exit non-zero
        print(f"[ingest] ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"Indexed {n} decisions into {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
