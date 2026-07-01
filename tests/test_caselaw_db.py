"""Offline tests for the FTS5 index: build in-memory, search, get, recent, stats."""

from __future__ import annotations

import pytest

from it_eli_mcp.caselaw import db
from it_eli_mcp.caselaw.records import normalize_decision

pytestmark = pytest.mark.skipif(not db.fts5_available(), reason="SQLite FTS5 not available")

DECISIONS = [
    {
        "ecli": "ECLI:IT:COST:1956:1", "numero_pronuncia": "1", "anno_pronuncia": "1956",
        "tipologia_pronuncia": "S", "data_decisione": "05/06/1956", "data_deposito": "14/06/1956",
        "presidente": "DE NICOLA", "relatore_pronuncia": "AZZARITI", "collegio": "",
        "epigrafe": "giudizio di legittimit&agrave; costituzionale",
        "testo": "La Corte dichiara l'illegittimit&agrave; della norma sulla pubblica sicurezza.",
        "dispositivo": "dichiara l'illegittimit&agrave; costituzionale",
    },
    {
        "ecli": "ECLI:IT:COST:2024:203", "numero_pronuncia": "203", "anno_pronuncia": "2024",
        "tipologia_pronuncia": "O", "data_decisione": "10/11/2024", "data_deposito": "20/11/2024",
        "presidente": "BARBERA", "relatore_pronuncia": "ROSSI", "collegio": "",
        "epigrafe": "questione in materia di protezione dei dati personali",
        "testo": "La societ&agrave; ricorrente lamenta la violazione della privacy.",
        "dispositivo": "dichiara manifestamente inammissibile la questione",
    },
]


@pytest.fixture
def conn():
    c = db.connect(":memory:", must_exist=False)
    db.create_schema(c)
    db.insert_decisions(c, [normalize_decision(r) for r in DECISIONS])
    c.commit()
    yield c
    c.close()


def test_search_basic(conn):
    hits = db.search(conn, "pubblica sicurezza")
    assert len(hits) == 1
    assert hits[0]["ecli"] == "ECLI:IT:COST:1956:1"
    assert "<<" in hits[0]["snippet"]  # snippet markers present


def test_search_diacritic_insensitive(conn):
    # query without the accent must still match "società"
    hits = db.search(conn, "societa")
    assert any(h["ecli"] == "ECLI:IT:COST:2024:203" for h in hits)


def test_search_filter_by_year_and_type(conn):
    assert len(db.search(conn, "illegittimita", anno="1956")) == 1
    assert db.search(conn, "illegittimita", anno="2024") == []
    assert len(db.search(conn, "questione", tipologia="O")) == 1
    assert db.search(conn, "questione", tipologia="S") == []


def test_get_by_ecli(conn):
    row = db.get_by_ecli(conn, "ECLI:IT:COST:2024:203")
    assert row is not None
    assert row["citation"] == "Corte cost., ord. n. 203/2024"
    assert "privacy" in row["testo"]
    assert db.get_by_ecli(conn, "ECLI:IT:COST:1900:1") is None


def test_recent_orders_newest_first(conn):
    r = db.recent(conn, limit=10)
    assert r[0]["ecli"] == "ECLI:IT:COST:2024:203"
    assert r[1]["ecli"] == "ECLI:IT:COST:1956:1"


def test_stats(conn):
    s = db.stats(conn)
    assert s["total"] == 2
    assert s["year_min"] == 1956
    assert s["year_max"] == 2024
    assert s["by_tipologia"] == {"Sentenza": 1, "Ordinanza": 1}


def test_empty_query_raises(conn):
    with pytest.raises(ValueError):
        db.search(conn, "!!!")


def test_missing_db_raises(tmp_path):
    with pytest.raises(db.DatabaseMissingError):
        db.connect(tmp_path / "nope.sqlite", must_exist=True)
