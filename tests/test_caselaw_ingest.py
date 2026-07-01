"""Offline tests for the archive walk + decoding, using an in-memory zip-of-zips."""

from __future__ import annotations

import io
import json
import zipfile

from it_eli_mcp.caselaw.ingest import _decisions_from_archive, _decode


def _make_nested_zip() -> bytes:
    payload = {
        "elenco_pronunce": [
            {"ecli": "ECLI:IT:COST:1956:1", "numero_pronuncia": "1", "anno_pronuncia": "1956",
             "tipologia_pronuncia": "S", "testo": "prima decisione", "dispositivo": "d1",
             "epigrafe": "e1", "data_decisione": "05/06/1956", "data_deposito": "14/06/1956",
             "presidente": "", "relatore_pronuncia": "", "redattore_pronuncia": "", "collegio": ""},
            {"numero_pronuncia": "2", "anno_pronuncia": "1956", "tipologia_pronuncia": "O",
             "testo": "seconda", "dispositivo": "d2", "epigrafe": "e2", "data_decisione": "",
             "data_deposito": "", "presidente": "", "relatore_pronuncia": "",
             "redattore_pronuncia": "", "collegio": ""},  # no ecli -> built from coordinates
        ]
    }
    # cp1252-encoded JSON (as the Court ships it)
    inner_json = json.dumps(payload, ensure_ascii=False).encode("cp1252")

    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w") as z:
        z.writestr("Cc_Opendata_Pronunce_1956.json", inner_json)

    outer_buf = io.BytesIO()
    with zipfile.ZipFile(outer_buf, "w") as z:
        z.writestr("Cc_Opendata_Pronunce_1956_json.zip", inner_buf.getvalue())
    return outer_buf.getvalue()


def test_decode_cp1252():
    raw = "società è legittimità".encode("cp1252")
    assert _decode(raw) == "società è legittimità"


def test_decode_utf8_still_works():
    raw = "società".encode()
    # utf-8 is tried first
    assert _decode(raw) == "società"


def test_walk_nested_zip_and_parse():
    decisions = list(_decisions_from_archive(_make_nested_zip()))
    assert len(decisions) == 2
    eclis = {d.ecli for d in decisions}
    assert "ECLI:IT:COST:1956:1" in eclis
    assert "ECLI:IT:COST:1956:2" in eclis  # built from coordinates when ecli absent
