"""Offline tests for the it_verify_citations tool - fixture acts, no network.

The Normattiva fetch seam (``server._fetch_act_doc``) is monkeypatched with a
schema-compatible fixture ``AknDoc`` (the mcp-de-legal pattern for corpora too
large to download in CI). The Constitutional Court index is an in-memory FTS5
database built from the same fixtures as test_caselaw_db.
"""

from __future__ import annotations

import pytest

import it_eli_mcp.server as server
from it_eli_mcp.akn import AknDoc, Article
from it_eli_mcp.caselaw import db
from it_eli_mcp.caselaw.records import normalize_decision

pytestmark = pytest.mark.skipif(not db.fts5_available(), reason="SQLite FTS5 not available")

# fastmcp returns a FunctionTool (call via .fn) or the bare function, by version.
_VERIFY = getattr(server.it_verify_citations, "fn", server.it_verify_citations)

CC_DOC = AknDoc(
    urn="urn:nir:stato:regio.decreto:1942-03-16;262",
    eli="eli/id/1942/04/04/042U0262/CONSOLIDATED",
    title="Codice civile",
    doc_date="1942-03-16",
    articles=[
        Article(eid=f"art_{n}", num=f"Art. {n}.", heading=None,
                text=f"1. Testo art. {n}. 2. Secondo comma.")
        for n in (1, 2, 100, 2042)
    ] + [
        Article(
            eid="art_2043",
            num="Art. 2043.",
            heading="Risarcimento per fatto illecito",
            text=("1. Qualunque fatto doloso o colposo, che cagiona ad altri un danno "
                  "ingiusto, obbliga colui che ha commesso il fatto a risarcire il danno."),
        ),
    ],
)

L241_DOC = AknDoc(
    urn="urn:nir:stato:legge:1990-08-07;241",
    eli="eli/id/1990/08/18/090G0294/CONSOLIDATED",
    title="Norme sul procedimento amministrativo",
    doc_date="1990-08-07",
    articles=[
        Article(eid=f"art_{n}", num=f"Art. {n}.", heading=None,
                text="1. Primo comma. 2. Secondo comma. 3. Terzo comma.")
        for n in range(1, 32)
    ],
)

DECISION = {
    "ecli": "ECLI:IT:COST:2024:1", "numero_pronuncia": "1", "anno_pronuncia": "2024",
    "tipologia_pronuncia": "S", "data_decisione": "09/01/2024", "data_deposito": "11/01/2024",
    "presidente": "BARBERA", "relatore_pronuncia": "ROSSI", "collegio": "",
    "epigrafe": "giudizio di legittimita costituzionale",
    "testo": "La Corte dichiara non fondata la questione.",
    "dispositivo": "dichiara non fondata la questione",
}


@pytest.fixture(autouse=True)
def _patched(monkeypatch):
    async def fake_fetch(client, reference):
        ref = reference.lower()
        if "codice civile" in ref or "1942" in ref:
            return CC_DOC
        if "241" in ref:
            return L241_DOC
        raise server.NotAvailableError(f"No Akoma Ntoso export link for {reference!r}.")

    conn = db.connect(":memory:", must_exist=False)
    db.create_schema(conn)
    db.insert_decisions(conn, [normalize_decision(DECISION)])
    conn.commit()

    async def fake_open_caselaw():
        # A fresh connection per call would close the shared in-memory DB;
        # hand out the same one and neutralize close().
        class _NoClose:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def close(self):
                pass

        return _NoClose(conn)

    monkeypatch.setattr(server, "_fetch_act_doc", fake_fetch)
    monkeypatch.setattr(server, "_open_caselaw", fake_open_caselaw)
    yield
    conn.close()


@pytest.mark.asyncio
async def test_all_verified():
    res = await _VERIFY("L'art. 2043 c.c. e l'art. 5 della legge 241/1990 si applicano.")
    sc = res.structured_content
    assert sc["status"] == "VERIFIED"
    assert res.is_error is False
    assert sc["total"] == 2
    assert sc["verified_count"] == 2
    assert sc["gaps"] == []
    assert all(c["status"] == "verified" for c in sc["citations"])


@pytest.mark.asyncio
async def test_hallucination_detected_with_range_hint():
    res = await _VERIFY("Ai sensi dell'art. 9999 della legge 241/1990 il termine decorre.")
    sc = res.structured_content
    assert sc["status"] == "HALLUCINATION_DETECTED"
    assert res.is_error is True
    check = sc["citations"][0]
    assert check["status"] == "not_found"
    assert "art. 9999 does not exist" in check["range_hint"]
    assert "art. 1-31" in check["range_hint"]
    text = res.content[0].text
    assert "[HALLUCINATION_DETECTED]" in text
    assert "NEVER report 'verification complete'" in text


@pytest.mark.asyncio
async def test_no_citations_is_not_success():
    res = await _VERIFY("Un testo senza alcuna citazione normativa.")
    sc = res.structured_content
    assert sc["status"] == "NO_CITATIONS_FOUND"
    assert res.is_error is False
    assert "NOT a verification success" in res.content[0].text


@pytest.mark.asyncio
async def test_content_match_ok_and_mismatch():
    ok = await _VERIFY("l'art. 2043 c.c. (risarcimento per fatto illecito) fonda la pretesa")
    assert ok.structured_content["status"] == "VERIFIED"
    cm = ok.structured_content["citations"][0]["content_match"]
    assert cm["matched"] is True

    bad = await _VERIFY("l'art. 2043 c.c. (durata del contratto di locazione) fonda la pretesa")
    sc = bad.structured_content
    assert sc["status"] == "PARTIAL_VERIFIED"   # signal, not a block
    assert bad.is_error is False
    check = sc["citations"][0]
    assert check["status"] == "content_mismatch"
    assert check["content_match"]["matched"] is False


@pytest.mark.asyncio
async def test_unparseable_citation_goes_to_gaps():
    res = await _VERIFY("come previsto dall'art. 12 in materia di trasparenza")
    sc = res.structured_content
    assert sc["status"] == "PARTIAL_VERIFIED"
    assert sc["citations"][0]["status"] == "unverified"
    assert any(g["gap_type"] == "unparseable_citation" for g in sc["gaps"])


@pytest.mark.asyncio
async def test_unresolvable_act_is_gap_not_hallucination():
    # An act Normattiva does not export must NOT count as a hallucination:
    # existence is unknown, not disproven.
    res = await _VERIFY("l'art. 3 della legge 9999/1993 non risulta")
    sc = res.structured_content
    assert sc["status"] == "PARTIAL_VERIFIED"
    assert res.is_error is False
    assert any(g["gap_type"] == "out_of_corpus" for g in sc["gaps"])


@pytest.mark.asyncio
async def test_ecli_cost_verified_and_missing():
    ok = await _VERIFY("v. ECLI:IT:COST:2024:1")
    assert ok.structured_content["status"] == "VERIFIED"
    assert ok.structured_content["citations"][0]["kind"] == "constitutional_caselaw"

    missing = await _VERIFY("v. ECLI:IT:COST:2024:99999")
    sc = missing.structured_content
    assert sc["status"] == "HALLUCINATION_DETECTED"
    assert missing.is_error is True
    assert "no such decision" in sc["citations"][0]["detail"]


@pytest.mark.asyncio
async def test_ecli_other_court_is_out_of_corpus_gap():
    res = await _VERIFY("v. ECLI:IT:CASS:2021:12345CIV")
    sc = res.structured_content
    assert sc["status"] == "PARTIAL_VERIFIED"
    assert sc["citations"][0]["kind"] == "caselaw_other"
    assert any(g["gap_type"] == "out_of_corpus" for g in sc["gaps"])


@pytest.mark.asyncio
async def test_comma_verified_and_comma_warning():
    ok = await _VERIFY("l'art. 5, comma 2, della legge 241/1990")
    assert ok.structured_content["status"] == "VERIFIED"

    warn = await _VERIFY("l'art. 5, comma 9, della legge 241/1990")
    sc = warn.structured_content
    assert sc["status"] == "PARTIAL_VERIFIED"
    assert sc["citations"][0]["status"] == "unverified"
    assert "comma 9" in sc["citations"][0]["detail"]


@pytest.mark.asyncio
async def test_max_citations_out_of_range():
    with pytest.raises(server.ITError, match=r"\[invalid_arg\]"):
        await _VERIFY("art. 1 c.c.", max_citations=0)
