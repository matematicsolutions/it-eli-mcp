"""Citation building for administrative case law (offline)."""

from __future__ import annotations

from it_eli_mcp.giustizia_amministrativa.citations import (
    court_label,
    human_citation,
    split_numero_provvedimento,
)


def test_split_numero_provvedimento() -> None:
    assert split_numero_provvedimento("202605450") == ("2026", "5450")
    assert split_numero_provvedimento("202600007") == ("2026", "7")
    assert split_numero_provvedimento("") == ("", "")
    assert split_numero_provvedimento("123") == ("", "")


def test_court_label() -> None:
    assert court_label("CONSIGLIO DI STATO") == "Cons. St."
    assert court_label("C.G.A.R.S") == "C.G.A.R.S."
    assert court_label("ROMA") == "T.A.R. Roma"
    assert court_label("REGGIO CALABRIA") == "T.A.R. Reggio Calabria"
    assert court_label(None) == ""


def test_human_citation_cds() -> None:
    assert (
        human_citation("SENTENZA", "CONSIGLIO DI STATO", "SEZIONE 4", "202605450")
        == "Cons. St., sez. 4, sent. n. 5450/2026"
    )


def test_human_citation_tar() -> None:
    assert (
        human_citation("ORDINANZA", "MILANO", "SEZIONE 2", "202600123")
        == "T.A.R. Milano, sez. 2, ord. n. 123/2026"
    )


def test_human_citation_missing_coordinates() -> None:
    assert human_citation("SENTENZA", "ROMA", "SEZIONE 1", None) is None
    assert human_citation("SENTENZA", None, "SEZIONE 1", "202600001") is None
