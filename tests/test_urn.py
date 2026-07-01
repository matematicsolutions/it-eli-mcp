"""Offline unit tests for URN:NIR building/parsing, the codes dict, and entry_url."""

from __future__ import annotations

import pytest

from it_eli_mcp.urn import (
    CODES,
    build_urn,
    entry_url,
    normalize_measure_type,
    parse_urn,
    resolve_code,
)


def test_build_urn_full_date():
    assert build_urn("legge", 1990, 241, month=8, day=7) == "urn:nir:stato:legge:1990-08-07;241"


def test_build_urn_partial_year_only():
    # A partial URN (year + number, no promulgation day) - still resolvable on Normattiva.
    assert build_urn("legge", 1990, 241) == "urn:nir:stato:legge:1990;241"


def test_build_urn_friendly_type_alias():
    assert build_urn("d.lgs", 2003, 196, month=6, day=30) == (
        "urn:nir:stato:decreto.legislativo:2003-06-30;196"
    )
    assert build_urn("dpr", 2000, 445, month=12, day=28, authority="presidente.repubblica") == (
        "urn:nir:presidente.repubblica:decreto.del.presidente.della.repubblica:2000-12-28;445"
    )


def test_normalize_measure_type():
    assert normalize_measure_type("D.Lgs.") == "decreto.legislativo"
    assert normalize_measure_type("legge") == "legge"


def test_parse_urn_roundtrip():
    ref = parse_urn("urn:nir:stato:legge:1990-08-07;241")
    assert ref.authority == "stato"
    assert ref.measure_type == "legge"
    assert ref.date == "1990-08-07"
    assert ref.number == "241"
    assert ref.human_label() == "Legge 7 agosto 1990, n. 241"


def test_parse_urn_partial():
    ref = parse_urn("urn:nir:stato:legge:1990;241")
    assert ref.measure_type == "legge"
    assert ref.date == "1990"
    assert ref.number == "241"
    assert ref.human_label() == "Legge n. 241/1990"


def test_parse_urn_rejects_garbage():
    with pytest.raises(ValueError):
        parse_urn("not-a-urn")


def test_resolve_code_and_aliases():
    assert resolve_code("codice civile")["urn"] == "urn:nir:stato:regio.decreto:1942-03-16;262"
    assert resolve_code("c.c.")["urn"] == "urn:nir:stato:regio.decreto:1942-03-16;262"
    assert resolve_code("GDPR")["urn"] == "urn:nir:stato:decreto.legislativo:2003-06-30;196"
    assert resolve_code("nonexistent") is None


def test_codes_dict_all_have_urn_and_label():
    for key, data in CODES.items():
        assert data["urn"].startswith("urn:nir:"), key
        assert data["label"], key


def test_entry_url_for_code_name():
    url = entry_url("codice civile")
    assert url == "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:regio.decreto:1942-03-16;262"


def test_entry_url_for_urn():
    url = entry_url("urn:nir:stato:legge:1990-08-07;241")
    assert url.endswith("uri-res/N2Ls?urn:nir:stato:legge:1990-08-07;241")


def test_entry_url_for_eli_path_adds_version():
    url = entry_url("eli/id/1990/08/18/090G0294")
    assert url == "https://www.normattiva.it/eli/id/1990/08/18/090G0294/CONSOLIDATED"


def test_entry_url_for_full_url_passthrough():
    src = "https://www.normattiva.it/eli/id/2003/07/29/003G0218/CONSOLIDATED"
    assert entry_url(src) == src


def test_entry_url_rejects_foreign_url():
    with pytest.raises(ValueError):
        entry_url("https://example.com/foo")


def test_entry_url_rejects_garbage():
    with pytest.raises(ValueError):
        entry_url("just some words")
