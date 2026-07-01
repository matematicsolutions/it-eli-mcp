"""Live smoke test - downloads the smallest era dump, builds an index, queries it.

Run manually:

    pytest -m smoke

Hits the Corte Costituzionale open data (dati.cortecostituzionale.it).
"""

from __future__ import annotations

import pytest

from it_eli_mcp.caselaw import db
from it_eli_mcp.caselaw.ingest import build_index

pytestmark = pytest.mark.smoke

SMALLEST_ERA = (
    "https://dati.cortecostituzionale.it/opendata/distribuzione/pronunce/P_json1956_1980.zip"
)


@pytest.fixture(scope="module")
def indexed_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("it-cost") / "cost.sqlite"
    n = build_index(path, [SMALLEST_ERA], progress=False)
    assert n > 100, f"expected many decisions from 1956-1980, got {n}"
    return path


def test_smoke_stats(indexed_db):
    conn = db.connect(indexed_db)
    try:
        s = db.stats(conn)
    finally:
        conn.close()
    assert s["total"] > 100
    assert s["year_min"] == 1956
    # the "1956_1980" era file spills a few stragglers past 1980 (deposited later)
    assert 1980 <= s["year_max"] <= 1990


def test_smoke_get_first_decision(indexed_db):
    conn = db.connect(indexed_db)
    try:
        row = db.get_by_ecli(conn, "ECLI:IT:COST:1956:1")
    finally:
        conn.close()
    assert row is not None
    assert row["anno"] == "1956"
    assert row["testo"] and len(row["testo"]) > 200
    assert "à" in row["testo"] or "è" in row["testo"]  # accents decoded correctly


def test_smoke_search(indexed_db):
    conn = db.connect(indexed_db)
    try:
        hits = db.search(conn, "costituzionale", limit=5)
    finally:
        conn.close()
    assert len(hits) > 0
    for h in hits:
        assert h["ecli"].startswith("ECLI:IT:COST:")
        assert h["citation"]
