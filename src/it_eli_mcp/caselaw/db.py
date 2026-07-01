"""SQLite FTS5 store for Corte Costituzionale decisions.

A single FTS5 table holds the searchable text (epigrafe/testo/dispositivo) plus the
metadata as UNINDEXED columns, tokenized with ``unicode61 remove_diacritics 2`` so an
Italian query matches regardless of accents. The database is built once by ``ingest``
and read by the MCP tools; nothing here reaches the network.
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from .records import Decision

# Column order MUST match the CREATE VIRTUAL TABLE below (snippet() uses the index).
_COLUMNS = [
    "ecli", "numero", "anno", "tipologia", "tipologia_label",
    "data_decisione", "data_deposito", "presidente", "relatore", "redattore",
    "collegio", "epigrafe", "testo", "dispositivo", "citation", "source_url",
]
_TESTO_COL_INDEX = _COLUMNS.index("testo")  # for snippet()

_UNINDEXED = {
    "ecli", "numero", "anno", "tipologia", "tipologia_label", "data_decisione",
    "data_deposito", "presidente", "relatore", "redattore", "collegio",
    "citation", "source_url",
}

# Strip FTS5 operator characters from user queries; keep letters, digits, spaces.
_FTS_SANITIZE_RE = re.compile(r"[^0-9A-Za-zÀ-ÿ ]+")


class DatabaseMissingError(Exception):
    """The index database does not exist yet. Run ``it-eli-caselaw-mcp-ingest``."""


def resolve_db_path() -> Path:
    env = os.environ.get("IT_ELI_CASELAW_DB")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".matematic" / "data" / "it-eli-caselaw" / "cost.sqlite"


def _column_ddl() -> str:
    cols = []
    for c in _COLUMNS:
        cols.append(f"{c} UNINDEXED" if c in _UNINDEXED else c)
    return ", ".join(cols)


def connect(path: Path | str | None = None, *, must_exist: bool = True) -> sqlite3.Connection:
    p = Path(path) if path is not None else resolve_db_path()
    is_memory = str(p) == ":memory:"
    if must_exist and not is_memory and not p.exists():
        raise DatabaseMissingError(
            f"Index not found at {p}. Build it with `it-eli-caselaw-mcp-ingest` "
            f"(downloads the Corte Costituzionale open data and indexes it)."
        )
    if not is_memory:
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS decisions USING fts5("
        f"{_column_ddl()}, tokenize='unicode61 remove_diacritics 2')"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()


def fts5_available() -> bool:
    try:
        c = sqlite3.connect(":memory:")
        c.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        c.close()
        return True
    except sqlite3.OperationalError:
        return False


def insert_decisions(conn: sqlite3.Connection, decisions: Iterable[Decision]) -> int:
    rows = ([getattr(d, c) for c in _COLUMNS] for d in decisions)
    placeholders = ", ".join("?" for _ in _COLUMNS)
    cur = conn.executemany(
        f"INSERT INTO decisions ({', '.join(_COLUMNS)}) VALUES ({placeholders})", rows
    )
    return cur.rowcount if cur.rowcount is not None else 0


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _sanitize_query(q: str) -> str:
    cleaned = _FTS_SANITIZE_RE.sub(" ", q).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def search(
    conn: sqlite3.Connection,
    query: str,
    *,
    anno: str | None = None,
    tipologia: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Full-text search over epigrafe/testo/dispositivo. Returns ranked hit dicts."""
    fts = _sanitize_query(query)
    if not fts:
        raise ValueError("Empty search query after sanitization.")
    sql = (
        "SELECT ecli, citation, anno, numero, tipologia_label, data_deposito, source_url, "
        f"snippet(decisions, {_TESTO_COL_INDEX}, '<<', '>>', ' ... ', 18) AS snippet "
        "FROM decisions WHERE decisions MATCH ?"
    )
    params: list[Any] = [fts]
    if anno:
        sql += " AND anno = ?"
        params.append(anno)
    if tipologia:
        sql += " AND tipologia = ?"
        params.append(tipologia.upper())
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_by_ecli(conn: sqlite3.Connection, ecli: str) -> dict[str, Any] | None:
    row = conn.execute(
        f"SELECT {', '.join(_COLUMNS)} FROM decisions WHERE ecli = ? LIMIT 1", (ecli.strip(),)
    ).fetchone()
    return dict(row) if row else None


def recent(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT ecli, citation, anno, numero, tipologia_label, data_deposito, source_url "
        "FROM decisions ORDER BY CAST(anno AS INTEGER) DESC, CAST(numero AS INTEGER) DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def stats(conn: sqlite3.Connection) -> dict[str, Any]:
    total = conn.execute("SELECT count(*) AS n FROM decisions").fetchone()["n"]
    years = conn.execute(
        "SELECT min(CAST(anno AS INTEGER)) AS lo, max(CAST(anno AS INTEGER)) AS hi FROM decisions"
    ).fetchone()
    by_type = conn.execute(
        "SELECT tipologia_label AS label, count(*) AS n FROM decisions GROUP BY tipologia_label"
    ).fetchall()
    return {
        "total": total,
        "year_min": years["lo"],
        "year_max": years["hi"],
        "by_tipologia": {r["label"]: r["n"] for r in by_type},
    }


def iter_search_columns() -> Iterator[str]:
    yield from _COLUMNS
