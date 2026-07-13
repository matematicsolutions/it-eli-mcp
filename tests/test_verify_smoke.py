"""Smoke tests for it_verify_citations - require internet (live Normattiva).

Run manually:

    pytest tests/test_verify_smoke.py -v -m smoke
"""

from __future__ import annotations

import pytest

import it_eli_mcp.server as server

pytestmark = pytest.mark.smoke

_VERIFY = getattr(server.it_verify_citations, "fn", server.it_verify_citations)


@pytest.mark.asyncio
async def test_smoke_verify_real_and_fake_article() -> None:
    res = await _VERIFY(
        "La responsabilita extracontrattuale si fonda sull'art. 2043 c.c. "
        "(risarcimento per fatto illecito); il termine e fissato dall'art. 99999 "
        "della legge 241/1990."
    )
    sc = res.structured_content
    assert sc["status"] == "HALLUCINATION_DETECTED"
    assert res.is_error is True
    by_article = {c["article"]: c for c in sc["citations"]}
    assert by_article["2043"]["status"] == "verified"
    assert by_article["2043"]["content_match"]["matched"] is True
    assert by_article["99999"]["status"] == "not_found"
    assert "does not exist" in by_article["99999"]["range_hint"]


@pytest.mark.asyncio
async def test_smoke_verify_all_good() -> None:
    res = await _VERIFY("Il responsabile del procedimento e disciplinato dall'art. 5 "
                        "della legge 7 agosto 1990, n. 241.")
    sc = res.structured_content
    assert sc["status"] == "VERIFIED"
    assert res.is_error is False
    assert sc["citations"][0]["source_url"].startswith("https://www.normattiva.it/")
