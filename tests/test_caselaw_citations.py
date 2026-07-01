"""Offline tests for ECLI + citation helpers."""

from __future__ import annotations

from it_eli_mcp.caselaw.citations import (
    build_ecli,
    human_citation,
    parse_ecli,
    source_url,
    tipologia_label,
)


def test_human_citation_sentenza():
    assert human_citation("1", "2024", "S") == "Corte cost., sent. n. 1/2024"


def test_human_citation_ordinanza():
    assert human_citation("45", "2020", "O") == "Corte cost., ord. n. 45/2020"


def test_human_citation_unknown_type():
    assert human_citation("7", "2019", "X") == "Corte cost., n. 7/2019"


def test_human_citation_missing():
    assert human_citation(None, "2024", "S") is None


def test_tipologia_label():
    assert tipologia_label("S") == "Sentenza"
    assert tipologia_label("o") == "Ordinanza"
    assert tipologia_label("Z") == "Z"
    assert tipologia_label(None) is None


def test_source_url():
    assert source_url("2024", "1") == (
        "https://www.cortecostituzionale.it/actionSchedaPronuncia.do?anno=2024&numero=1"
    )


def test_parse_ecli():
    assert parse_ecli("ECLI:IT:COST:1956:1") == ("1956", "1")
    assert parse_ecli("ecli:it:cost:2024:203") == ("2024", "203")
    assert parse_ecli("ECLI:DE:BAG:2024:1") is None
    assert parse_ecli("nonsense") is None


def test_build_ecli():
    assert build_ecli("2024", "1") == "ECLI:IT:COST:2024:1"
