"""Live smoke test - queries the real SentenzeWeb Solr endpoint.

Run manually:

    pytest -m smoke

Hits italgiure.giustizia.it/sncass (the Court's free public search engine).
"""

from __future__ import annotations

import pytest

from it_eli_mcp.cassazione import client

pytestmark = pytest.mark.smoke


async def test_smoke_search_returns_hits():
    total, decisions, _hl = await client.search("responsabilita medica", limit=3)
    assert total > 0
    assert len(decisions) > 0
    for d in decisions:
        assert d.sic_id
        assert d.testo


async def test_smoke_search_civil_only():
    total, decisions, _hl = await client.search("contratto", chamber="civile", limit=3)
    assert total > 0
    for d in decisions:
        assert d.kind == "snciv"


async def test_smoke_search_labour_chamber():
    total, decisions, _hl = await client.search("licenziamento", sub_chamber="lavoro", limit=3)
    assert total > 0
    for d in decisions:
        assert d.szdec == "L"


async def test_smoke_get_by_id_roundtrip():
    _total, decisions, _hl = await client.search("contratto", limit=1)
    assert decisions
    sic_id = decisions[0].sic_id
    fetched = await client.get_by_id(sic_id)
    assert fetched is not None
    assert fetched.sic_id == sic_id
    assert fetched.testo
