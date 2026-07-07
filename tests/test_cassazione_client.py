"""Offline tests for the Cassazione client's query-building/sanitization (no network)."""

from __future__ import annotations

import pytest

from it_eli_mcp.cassazione.client import (
    CassazioneError,
    _kind_filter,
    _sanitize_term,
    _szdec_filter,
)


def test_sanitize_term_strips_quotes_and_braces():
    assert _sanitize_term('foo "bar" [baz]') == "foo bar baz"


def test_sanitize_term_empty_raises():
    with pytest.raises(CassazioneError):
        _sanitize_term('   ')


def test_kind_filter_aliases():
    assert _kind_filter("civile") == "snciv"
    assert _kind_filter("CIV") == "snciv"
    assert _kind_filter("penale") == "snpen"
    assert _kind_filter(None) is None


def test_kind_filter_invalid():
    with pytest.raises(CassazioneError):
        _kind_filter("amministrativo")


def test_szdec_filter_aliases():
    assert _szdec_filter("lavoro") == "L"
    assert _szdec_filter("Tax") == "5"
    assert _szdec_filter(None) is None


def test_szdec_filter_invalid():
    with pytest.raises(CassazioneError):
        _szdec_filter("bogus")
