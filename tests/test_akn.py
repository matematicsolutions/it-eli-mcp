"""Offline unit tests for the Akoma Ntoso parser against a fixture."""

from __future__ import annotations

from pathlib import Path

import pytest

from it_eli_mcp.akn import find_article, parse_akn
from it_eli_mcp.citations import build_contract, eli_source_url, iso_to_vigenza
from it_eli_mcp.urn import parse_urn

FIXTURE = (Path(__file__).parent / "fixtures" / "act_sample.akn.xml").read_bytes()


@pytest.fixture
def doc():
    return parse_akn(FIXTURE)


def test_parse_identity(doc):
    assert doc.urn == "urn:nir:stato:legge:1990-08-07;241"
    assert doc.eli == "eli/id/1990/08/18/090G0294/CONSOLIDATED/20260421"
    assert doc.doc_date == "1990-08-07"
    assert doc.doc_type == "legge"
    assert doc.title == "LEGGE 7 agosto 1990, n. 241"


def test_parse_articles(doc):
    assert doc.article_count() == 2
    nums = [a.num for a in doc.articles]
    assert "Art. 1." in nums
    assert "Art. 2043." in nums


def test_article_text_excludes_num_and_heading(doc):
    art = find_article(doc, "2043")
    assert art is not None
    assert art.heading == "Risarcimento per fatto illecito"
    assert "Qualunque fatto doloso o colposo" in art.text
    # the <num>/<heading> are not duplicated into the body text
    assert "Art. 2043." not in art.text
    assert "Risarcimento per fatto illecito" not in art.text


def test_find_article_variants(doc):
    assert find_article(doc, "2043") is not None
    assert find_article(doc, "art. 2043") is not None
    assert find_article(doc, "Art. 2043.") is not None
    assert find_article(doc, "9999") is None


def test_build_contract(doc):
    contract = build_contract(doc, parse_urn(doc.urn))
    assert contract["eli_uri"] == "eli/id/1990/08/18/090G0294/CONSOLIDATED/20260421"
    assert contract["urn"] == "urn:nir:stato:legge:1990-08-07;241"
    assert contract["human_readable_citation"] == "Legge 7 agosto 1990, n. 241"
    # source_url drops the trailing point-in-time stamp
    assert contract["source_url"] == (
        "https://www.normattiva.it/eli/id/1990/08/18/090G0294/CONSOLIDATED"
    )


def test_eli_source_url_trims_pit():
    assert eli_source_url("eli/id/1990/08/18/090G0294/CONSOLIDATED/20260421") == (
        "https://www.normattiva.it/eli/id/1990/08/18/090G0294/CONSOLIDATED"
    )


def test_iso_to_vigenza():
    assert iso_to_vigenza("2020-06-19") == "20200619"
    assert iso_to_vigenza("20200619") == "20200619"
    assert iso_to_vigenza("nonsense") is None
    assert iso_to_vigenza(None) is None


def test_parse_rejects_non_xml():
    with pytest.raises(ValueError):
        parse_akn(b"\x00\x01 not xml at all <<<")


# --- Italian codes: articles live in <attachment>/<doc>, not <article> --------

CODE_FIXTURE = (Path(__file__).parent / "fixtures" / "code_sample.akn.xml").read_bytes()


@pytest.fixture
def code_doc():
    return parse_akn(CODE_FIXTURE)


def test_code_articles_harvested_from_attachments(code_doc):
    # 2 enacting-decree <article> + 2 code <doc> articles.
    assert code_doc.article_count() == 4
    art = find_article(code_doc, "2043")
    assert art is not None
    assert art.num == "Art. 2043"
    assert art.heading == "Risarcimento per fatto illecito"
    assert "danno ingiusto" in art.text
    # the leading "Art. 2043." label and the (heading) are stripped from the body
    assert not art.text.startswith("Art. 2043")


def test_code_article_priority_over_enacting_article(code_doc):
    # Article "1" exists in both the enacting decree and (here) not the annex;
    # the annex articles are listed first so a code lookup wins when both match.
    annex_first = [a.num for a in code_doc.articles[:2]]
    assert annex_first == ["Art. 2043", "Art. 2044"]
