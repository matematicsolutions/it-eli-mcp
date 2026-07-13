"""Offline tests for the citation parser and content matcher (verify.py)."""

from __future__ import annotations

from it_eli_mcp.verify import (
    CONTENT_WARN_THRESHOLD,
    detect_commi,
    match_claim,
    normalize_text,
    parse_citations,
    range_hint,
    trigram_jaccard,
    trigram_overlap,
)

# ---------------------------------------------------------------------------
# Parser - statute citations
# ---------------------------------------------------------------------------


def test_parse_code_abbreviation_after():
    cites = parse_citations("Il danno e risarcibile ex art. 2043 c.c. in ogni caso.")
    assert len(cites) == 1
    c = cites[0]
    assert c.kind == "statute"
    assert c.article == "2043"
    assert c.code_key == "codice civile"


def test_parse_cpc_not_swallowed_by_cc():
    # "c.p.c." must resolve to procedura civile, never half-match "c.c." / "c.p.".
    cites = parse_citations("ai sensi dell'art. 360 c.p.c. e dell'art. 575 c.p.")
    assert [c.code_key for c in cites] == [
        "codice di procedura civile", "codice penale",
    ]


def test_parse_costituzione_abbrev_and_costituzionale_noise():
    cites = parse_citations("viola l'art. 117, comma 2, Cost. per questione costituzionale")
    assert len(cites) == 1
    assert cites[0].code_key == "costituzione"
    assert cites[0].article == "117"
    assert cites[0].comma == "2"


def test_parse_legge_full_date_after():
    cites = parse_citations("l'art. 5 della legge 7 agosto 1990, n. 241 dispone che...")
    c = cites[0]
    assert c.act_type == "legge"
    assert c.act_number == "241"
    assert c.act_year == 1990
    assert c.act_month == 8
    assert c.act_day == 7


def test_parse_legge_slash_year():
    cites = parse_citations("come previsto dall'art. 21-septies della l. 241/1990.")
    c = cites[0]
    assert c.article == "21-septies"
    assert c.act_type == "legge"
    assert c.act_number == "241"
    assert c.act_year == 1990


def test_parse_dlgs_not_matched_as_dl():
    cites = parse_citations("l'art. 6 del d.lgs. 231/2001 richiede il modello organizzativo.")
    c = cites[0]
    assert c.act_type == "decreto.legislativo"
    assert c.act_number == "231"
    assert c.act_year == 2001


def test_parse_decreto_legge_not_matched_as_legge():
    cites = parse_citations("l'art. 1 del decreto-legge 19 maggio 2020, n. 34 introduce...")
    assert cites[0].act_type == "decreto.legge"
    assert cites[0].act_number == "34"


def test_parse_act_before_article_lookback():
    cites = parse_citations("La legge 241/1990 disciplina, all'art. 5, il responsabile.")
    c = cites[0]
    assert c.act_type == "legge"
    assert c.act_number == "241"
    assert c.article == "5"


def test_parse_enumeration_artt():
    cites = parse_citations("le clausole vessatorie di cui agli artt. 1341 e 1342 c.c.")
    assert [c.article for c in cites] == ["1341", "1342"]
    assert all(c.code_key == "codice civile" for c in cites)


def test_parse_comma_not_an_enumeration():
    # "art. 5, comma 2" must stay ONE citation with comma=2, not articles 5 and 2.
    cites = parse_citations("l'art. 5, comma 2, della legge 241/1990")
    assert len(cites) == 1
    assert cites[0].article == "5"
    assert cites[0].comma == "2"


def test_parse_no_act_in_context():
    cites = parse_citations("come stabilito dall'art. 12 in materia di trasparenza")
    assert len(cites) == 1
    assert cites[0].code_key is None
    assert cites[0].act_type is None


def test_parse_claim_parenthetical():
    cites = parse_citations("l'art. 2043 c.c. (risarcimento per fatto illecito) impone...")
    assert cites[0].claim == "risarcimento per fatto illecito"


def test_parse_claim_rejects_amendment_note():
    cites = parse_citations("l'art. 5 della l. 241/1990 (come modificato nel 2005) prevede...")
    assert cites[0].claim is None


def test_parse_dedupe():
    text = "l'art. 2043 c.c. e ancora l'art. 2043 c.c."
    assert len(parse_citations(text)) == 1


def test_parse_max_citations_cap():
    text = " ".join(f"art. {n} c.c." for n in range(1, 40))
    assert len(parse_citations(text, max_citations=5)) == 5


def test_parse_no_citations():
    assert parse_citations("Questo testo non contiene alcuna citazione normativa.") == []


# ---------------------------------------------------------------------------
# Parser - ECLI
# ---------------------------------------------------------------------------


def test_parse_ecli_cost_and_other():
    cites = parse_citations("v. ECLI:IT:COST:2024:1 e ECLI:IT:CASS:2021:12345CIV")
    eclis = [c for c in cites if c.kind == "ecli"]
    assert len(eclis) == 2
    assert eclis[0].ecli == "ECLI:IT:COST:2024:1"
    assert eclis[0].ecli_court == "COST"
    assert eclis[1].ecli_court == "CASS"


# ---------------------------------------------------------------------------
# Trigram content matcher
# ---------------------------------------------------------------------------


def test_normalize_strips_accents_and_punct():
    assert normalize_text("Responsabilità  civile!") == "responsabilita civile"


def test_trigram_jaccard_identical():
    assert trigram_jaccard("risarcimento del danno", "risarcimento del danno") == 1.0


def test_trigram_jaccard_unrelated_below_threshold():
    score = trigram_jaccard("risarcimento per fatto illecito", "durata del contratto di locazione")
    assert score < CONTENT_WARN_THRESHOLD


def test_trigram_overlap_claim_in_long_body():
    body = ("Qualunque fatto doloso o colposo, che cagiona ad altri un danno ingiusto, "
            "obbliga colui che ha commesso il fatto a risarcire il danno.") * 3
    assert trigram_overlap("cagiona ad altri un danno ingiusto", body) > 0.8


def test_match_claim_exact_layer():
    matched, method, score = match_claim(
        "risarcimento per fatto illecito",
        "Risarcimento per fatto illecito",
        "Qualunque fatto doloso o colposo...",
    )
    assert matched and method == "exact" and score == 1.0


def test_match_claim_paraphrase_via_heading():
    matched, method, _ = match_claim(
        "il risarcimento del fatto illecito",
        "Risarcimento per fatto illecito",
        "Qualunque fatto doloso o colposo, che cagiona ad altri un danno ingiusto...",
    )
    assert matched
    assert method in ("trigram-jaccard", "trigram-overlap")


def test_match_claim_mismatch():
    matched, _, score = match_claim(
        "durata massima del contratto di lavoro",
        "Risarcimento per fatto illecito",
        "Qualunque fatto doloso o colposo, che cagiona ad altri un danno ingiusto, "
        "obbliga colui che ha commesso il fatto a risarcire il danno.",
    )
    assert not matched
    assert score < CONTENT_WARN_THRESHOLD


# ---------------------------------------------------------------------------
# Range hint and comma detection
# ---------------------------------------------------------------------------


def test_range_hint_format():
    labels = [f"Art. {n}." for n in range(1, 373)]
    hint = range_hint(labels, "9999")
    assert "art. 9999 does not exist" in hint
    assert "372 articles" in hint
    assert "art. 1-372" in hint


def test_range_hint_no_articles():
    assert "exposes no numbered articles" in range_hint([], "5")


def test_detect_commi():
    text = "1. Il responsabile provvede. 2. Entro trenta giorni. 3. Salvo diversa previsione."
    assert detect_commi(text) == [1, 2, 3]


def test_detect_commi_not_plausible():
    # A single stray "1990. " must not be read as a commi sequence.
    assert detect_commi("Legge del 1990. Testo unico senza numerazione.") == []
