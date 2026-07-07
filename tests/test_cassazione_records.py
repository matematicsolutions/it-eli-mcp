"""Offline tests: normalizing a raw SentenzeWeb Solr document into a clean record.

RAW mirrors the actual shape returned live by the endpoint (captured 2026-07-07,
see tests/fixtures/cassazione_sample_solr_response.json) - most text fields are
Solr multi-valued (wrapped in a list), a few are scalars.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from it_eli_mcp.cassazione.records import normalize_decision

FIXTURE = Path(__file__).parent / "fixtures" / "cassazione_sample_solr_response.json"

RAW = {
    "materia": ["IRPEF ILOR ACCERTAMENTO"],
    "ocrdis": ["P.Q.M. La Corte dichiara estinto il giudizio."],
    "pd": "20210722",
    "numdec": "21018",
    "szdec": "5",
    "datdep": ["20210722"],
    "kind": "snciv",
    "sicId": ["sic2021521018O004112"],
    "datdec": "20210512",
    "ocr": ["la seguente ORDINANZA sul ricorso iscritto al n. 4112/2015 R.G. ..."],
    "tipoprov": "Ordinanza",
    "ssz": "0",
    "relatore": ["ROSSI RAFFAELE"],
    "anno": "2021",
    "presidente": ["CIRILLO ETTORE"],
    "id": "snciv2021521018O",
    "filename": ["./20210722/snciv@s50@a2021@n21018@tO.pdf"],
}


def test_normalize_basic_fields():
    d = normalize_decision(RAW)
    assert d.sic_id == "snciv2021521018O"
    assert d.kind == "snciv"
    assert d.numdec == "21018"
    assert d.anno == "2021"
    assert d.tipoprov == "Ordinanza"
    assert d.szdec == "5"  # Tax chamber


def test_citation_uses_tax_chamber_label():
    d = normalize_decision(RAW)
    assert d.citation == "Cass. civ., Sez. trib., ord. n. 21018/2021"


def test_dates_converted_to_iso():
    d = normalize_decision(RAW)
    assert d.data_decisione == "2021-05-12"
    assert d.data_deposito == "2021-07-22"


def test_multivalued_fields_unwrapped():
    d = normalize_decision(RAW)
    assert d.presidente == "CIRILLO ETTORE"
    assert d.relatore == "ROSSI RAFFAELE"
    assert d.materia == "IRPEF ILOR ACCERTAMENTO"
    assert "ordinanza" in d.testo.lower() or "ORDINANZA" in d.testo


def test_source_url():
    d = normalize_decision(RAW)
    assert d.source_url == "https://www.italgiure.giustizia.it/sncass/#id=snciv2021521018O"


def test_missing_identifier_raises():
    with pytest.raises(ValueError):
        normalize_decision({"ocr": ["x"], "kind": "snciv"})


def test_criminal_chamber_citation():
    raw = dict(RAW, kind="snpen", szdec="0", tipoprov="Sentenza", numdec="999", anno="2020")
    d = normalize_decision(raw)
    assert d.citation == "Cass. pen., sent. n. 999/2020"


def test_real_fixture_normalizes():
    """Sanity check against the actual live response captured during discovery."""
    if not FIXTURE.exists():
        pytest.skip("fixture not present")
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    doc = data["response"]["docs"][0]
    d = normalize_decision(doc)
    assert d.anno and d.numdec
    assert d.testo
