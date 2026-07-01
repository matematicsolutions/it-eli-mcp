"""Offline tests: normalizing a raw open-data decision into a clean record."""

from __future__ import annotations

import pytest

from it_eli_mcp.caselaw.records import normalize_decision

RAW = {
    "collegio": "composta dai signori: Avv. ENRICO DE NICOLA, Presidente",
    "numero_pronuncia": "1",
    "anno_pronuncia": "1956",
    "data_decisione": "05/06/1956",
    "data_deposito": "14/06/1956",
    "tipologia_pronuncia": "S",
    "presidente": "DE NICOLA",
    "relatore_pronuncia": "AZZARITI",
    "redattore_pronuncia": "",
    "epigrafe": "nei giudizi di legittimit&agrave; costituzionale dell'art. 113&#13;T.U.",
    "testo": "Ritenuto in fatto:&#13;La questione di legittimit&agrave; &egrave; unica.",
    "dispositivo": "per questi motivi LA CORTE COSTITUZIONALE dichiara ...",
    "ecli": "ECLI:IT:COST:1956:1",
}


def test_normalize_basic_fields():
    d = normalize_decision(RAW)
    assert d.ecli == "ECLI:IT:COST:1956:1"
    assert d.numero == "1"
    assert d.anno == "1956"
    assert d.tipologia == "S"
    assert d.tipologia_label == "Sentenza"
    assert d.citation == "Corte cost., sent. n. 1/1956"
    assert d.source_url == (
        "https://www.cortecostituzionale.it/actionSchedaPronuncia.do?anno=1956&numero=1"
    )


def test_html_entities_unescaped():
    d = normalize_decision(RAW)
    # &agrave; -> à, &egrave; -> è, &#13; -> newline (collapsed away from inline runs)
    assert "legittimità" in d.epigrafe
    assert "è unica" in d.testo
    assert "&agrave;" not in d.testo
    assert "&#13;" not in d.epigrafe


def test_ecli_fallback_from_coordinates():
    raw = dict(RAW)
    del raw["ecli"]
    d = normalize_decision(raw)
    assert d.ecli == "ECLI:IT:COST:1956:1"


def test_missing_identifier_raises():
    with pytest.raises(ValueError):
        normalize_decision({"testo": "x"})


def test_ordinanza_citation():
    raw = dict(RAW, tipologia_pronuncia="O", numero_pronuncia="45", anno_pronuncia="2020",
               ecli="ECLI:IT:COST:2020:45")
    d = normalize_decision(raw)
    assert d.tipologia_label == "Ordinanza"
    assert d.citation == "Corte cost., ord. n. 45/2020"
