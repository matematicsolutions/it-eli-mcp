"""Offline parse tests for the GA search HTML and document XML fixtures.

Both fixtures are trimmed, verbatim copies of live responses captured
2026-07-08 during the ConsiglioDiStato re-verification (see DISCOVERY.md).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from it_eli_mcp.giustizia_amministrativa.records import (
    GaParseError,
    parse_document,
    parse_search_html,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def search_html() -> str:
    return (FIXTURES / "ga_search_sample.html").read_text(encoding="utf-8")


@pytest.fixture()
def document_xml() -> bytes:
    return (FIXTURES / "ga_document_sample.xml").read_bytes()


def test_parse_search_total_and_hits(search_html: str) -> None:
    total, hits = parse_search_html(search_html)
    assert total == 1128
    assert len(hits) == 2
    h = hits[0]
    assert h.tipo == "SENTENZA"
    assert h.sede == "ROMA"
    assert h.sezione == "SEZIONE 1B"
    assert h.numero_provvedimento == "202611970"
    assert h.anno == "2026"
    assert h.numero == "11970"
    assert h.numero_ricorso == "202515527"
    assert h.ecli == "ECLI:IT:TARLAZ:2026:11970SENT"
    assert h.document_url.startswith("https://mdp.giustizia-amministrativa.it/visualizza/?")
    assert "nomeFile=202611970_01.html" in h.document_url
    assert h.document_format == "xml"
    assert "&amp;" not in h.document_url
    assert "Responsabilita" in h.snippet


def test_parse_search_citation(search_html: str) -> None:
    _, hits = parse_search_html(search_html)
    assert hits[0].citation == "T.A.R. Roma, sez. 1B, sent. n. 11970/2026"


def test_parse_search_rejects_unknown_layout() -> None:
    with pytest.raises(GaParseError, match="Trovati"):
        parse_search_html("<html><body>Qualcosa di diverso</body></html>")


def test_parse_document_coordinates(document_xml: bytes) -> None:
    doc = parse_document(document_xml)
    assert doc.tipologia == "Sentenza"
    assert doc.anno == "2026"
    assert doc.numero == "11970"
    assert doc.nrg_anno == "2025"
    assert doc.nrg_numero == "15527"
    assert doc.data_pubblicazione == "2026-07-01"
    assert doc.urn.startswith("urn:nir:tar.lazio")


def test_parse_document_body_order_and_content(document_xml: bytes) -> None:
    doc = parse_document(document_xml)
    assert "Il Tribunale Amministrativo Regionale" in doc.testo
    assert "Ordina che la presente sentenza sia eseguita" in doc.testo
    # epigrafe comes before the dispositivo
    assert doc.testo.index("ha pronunciato la presente") < doc.testo.index(
        "definitivamente pronunciando sul ricorso"
    )
    # internal file paths / word file names from <meta> must NOT leak into the text
    assert ".docm" not in doc.testo
    assert "DocumentiGA" not in doc.testo


def test_parse_document_rejects_html_404() -> None:
    # a well-formed HTML page parses as XML but lacks <Provvedimento>;
    # truly malformed content fails at the XML stage - both must raise
    with pytest.raises(GaParseError, match="GA XML"):
        parse_document(b"<!DOCTYPE html><html><body>404</body></html>")
    with pytest.raises(GaParseError, match="GA XML"):
        parse_document(b"<html><body>404 <br> unclosed</body></html>")
