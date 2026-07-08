"""Live smoke tests against giustizia-amministrativa.it (marked smoke)."""

from __future__ import annotations

import pytest

from it_eli_mcp.giustizia_amministrativa import client as ga_client

pytestmark = pytest.mark.smoke


async def test_live_fulltext_search_cds_narrows() -> None:
    total_all, hits_all = await ga_client.search("responsabilita", limit=5)
    total_cds, hits_cds = await ga_client.search(
        "responsabilita", sede="Consiglio di Stato", limit=5
    )
    assert total_all > total_cds > 0  # sede filter must actually narrow
    assert hits_all and hits_cds
    hit = hits_cds[0]
    assert hit.document_url.startswith("https://mdp.giustizia-amministrativa.it/visualizza/?")
    assert hit.ecli.startswith("ECLI:IT:")
    assert hit.citation


async def test_live_numero_lookup_and_anno_client_filter() -> None:
    total, hits = await ga_client.search(
        numero="5450", anno="2026", sede="Consiglio di Stato", tipo="sentenza", limit=20
    )
    assert total >= 1
    assert hits, "expected the 2026 decision among the newest-first first page"
    assert all(h.anno == "2026" for h in hits)
    assert any(h.numero == "5450" for h in hits)


async def test_live_get_decision_full_text() -> None:
    _, hits = await ga_client.search("appalto", sede="Consiglio di Stato", limit=20)
    xml_hits = [h for h in hits if h.document_format == "xml"]
    assert xml_hits, "expected at least one machine-readable (GA XML) hit on page 1"
    doc = await ga_client.get_document(xml_hits[0].document_url)
    assert len(doc.testo) > 2000
    assert doc.anno and doc.numero
    assert doc.tipologia
