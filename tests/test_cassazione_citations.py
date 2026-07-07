"""Offline tests for Cassazione citation helpers."""

from __future__ import annotations

from it_eli_mcp.cassazione.citations import human_citation, section_label, source_url, tipo_abbr


def test_human_citation_civil_ordinary_section():
    assert human_citation("snciv", "Ordinanza", "21018", "2021", szdec="0", ssz="5") == (
        "Cass. civ., Sez. V, ord. n. 21018/2021"
    )


def test_human_citation_labour_chamber():
    assert human_citation("snciv", "Sentenza", "4567", "2019", szdec="L") == (
        "Cass. civ., Sez. lav., sent. n. 4567/2019"
    )


def test_human_citation_tax_chamber():
    assert human_citation("snciv", "Sentenza", "8901", "2022", szdec="5") == (
        "Cass. civ., Sez. trib., sent. n. 8901/2022"
    )


def test_human_citation_criminal():
    assert human_citation("snpen", "Sentenza", "12345", "2020") == "Cass. pen., sent. n. 12345/2020"


def test_human_citation_missing_coordinates():
    assert human_citation("snciv", "Sentenza", None, "2020") is None
    assert human_citation("snciv", "Sentenza", "1", None) is None


def test_tipo_abbr():
    assert tipo_abbr("Sentenza") == "sent."
    assert tipo_abbr("Ordinanza") == "ord."
    assert tipo_abbr(None) == "n."
    assert tipo_abbr("Boh") == "n."


def test_section_label_szdec_wins_over_ssz():
    assert section_label("snciv", "L", "3") == "Sez. lav."
    assert section_label("snciv", "5", "3") == "Sez. trib."


def test_section_label_from_ssz_roman():
    assert section_label("snciv", "0", "3") == "Sez. III"
    assert section_label("snciv", None, "1") == "Sez. I"


def test_section_label_none_when_ordinary():
    assert section_label("snciv", "0", "0") is None
    assert section_label("snciv", None, None) is None


def test_source_url_with_id():
    assert source_url("snciv2021521018O") == (
        "https://www.italgiure.giustizia.it/sncass/#id=snciv2021521018O"
    )


def test_source_url_without_id():
    assert source_url(None) == "https://www.italgiure.giustizia.it/sncass/"
