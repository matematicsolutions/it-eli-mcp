"""Offline tests for GA client argument handling (no network)."""

from __future__ import annotations

import pytest

from it_eli_mcp.giustizia_amministrativa.client import (
    MDP_DOCUMENT_PREFIX,
    GaError,
    _page_size_for,
    get_document,
    resolve_sede,
    resolve_tipo,
    search,
)


def test_resolve_sede_aliases() -> None:
    assert resolve_sede(None) is None
    assert resolve_sede("cds") == "Consiglio di Stato"
    assert resolve_sede("Consiglio di Stato") == "Consiglio di Stato"
    assert resolve_sede("CGARS") == "C.G.A.R.S"
    assert resolve_sede("roma") == "Roma"
    assert resolve_sede("TAR Milano") == "Milano"
    assert resolve_sede("l'aquila") == "L'Aquila"


def test_resolve_sede_rejects_unknown() -> None:
    with pytest.raises(GaError, match="Unknown sede"):
        resolve_sede("Atlantide")


def test_resolve_tipo() -> None:
    assert resolve_tipo(None) is None
    assert resolve_tipo("sentenza") == "Sentenza"
    assert resolve_tipo("Plenaria") == "P"
    assert resolve_tipo("adunanza generale") == "C"
    with pytest.raises(GaError, match="Unknown tipo"):
        resolve_tipo("lodo")


def test_page_size_snaps_to_portal_values() -> None:
    assert _page_size_for(1) == 20
    assert _page_size_for(20) == 20
    assert _page_size_for(21) == 40
    assert _page_size_for(60) == 60


async def test_search_requires_query_or_numero() -> None:
    with pytest.raises(GaError, match="full-text query"):
        await search(None)


async def test_search_validates_numero_and_anno() -> None:
    with pytest.raises(GaError, match="numero"):
        await search(numero="123456")
    with pytest.raises(GaError, match="anno"):
        await search(query="x", anno="26")


async def test_get_document_rejects_foreign_urls() -> None:
    with pytest.raises(GaError, match="document_url"):
        await get_document("https://example.com/evil")
    with pytest.raises(GaError, match="document_url"):
        await get_document("http://mdp.giustizia-amministrativa.it/visualizza/?x=1")
    assert MDP_DOCUMENT_PREFIX.startswith("https://mdp.giustizia-amministrativa.it/")
