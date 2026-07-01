"""Smoke tests - require internet (live Normattiva). Not run in offline CI.

Run manually:

    pytest tests/test_smoke.py -v -m smoke

All tests go through the live Normattiva session flow.
"""

from __future__ import annotations

import pytest

from it_eli_mcp.models import ResolveQuery
from it_eli_mcp.server import it_get_act, it_get_text, it_list_codes, it_resolve

pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
async def test_smoke_list_codes() -> None:
    codes = await it_list_codes()
    keys = {c.key for c in codes}
    assert "codice civile" in keys
    assert all(c.urn.startswith("urn:nir:") for c in codes)


@pytest.mark.asyncio
async def test_smoke_resolve_coordinates() -> None:
    res = await it_resolve(ResolveQuery(act_type="legge", year=1990, number=241))
    assert res.urn == "urn:nir:stato:legge:1990;241"
    assert "241" in res.human_readable_citation
    assert res.source_url.startswith("https://www.normattiva.it/")


@pytest.mark.asyncio
async def test_smoke_get_act_by_code() -> None:
    act = await it_get_act("legge 241/1990")
    assert act.urn is not None and "241" in act.urn
    assert act.eli_uri is not None and act.eli_uri.startswith("eli/")
    assert act.article_count > 10
    assert act.source_url.startswith("https://www.normattiva.it/")


@pytest.mark.asyncio
async def test_smoke_get_article_2043_codice_civile() -> None:
    text = await it_get_text("codice civile", article="2043")
    assert text.article_num is not None and "2043" in text.article_num
    assert "danno" in text.content.lower()
    assert text.eli_uri is not None
    assert text.byte_size > 0


@pytest.mark.asyncio
async def test_smoke_point_in_time() -> None:
    # The privacy code as it stood in 2010 (pre-GDPR alignment) must still fetch.
    text = await it_get_text("codice privacy", article="1", at_date="2010-01-01")
    assert text.at_date == "2010-01-01"
    assert text.byte_size > 0
