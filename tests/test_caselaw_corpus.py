"""Offline tests for lazy index provisioning (``corpus.ensure_index``).

Covers the choice ladder - cached hit, release-asset download (real sha256 verify over
a localhost HTTP server), asset->build fallback, and the final clear error - without
touching the network or the ~100 MB official dumps.
"""

from __future__ import annotations

import functools
import hashlib
import http.server
import socketserver
import threading
from pathlib import Path

import pytest

from it_eli_mcp.caselaw import corpus, db
from it_eli_mcp.caselaw.records import normalize_decision

pytestmark = pytest.mark.skipif(not db.fts5_available(), reason="SQLite FTS5 not available")

DECISIONS = [
    {
        "ecli": "ECLI:IT:COST:1956:1", "numero_pronuncia": "1", "anno_pronuncia": "1956",
        "tipologia_pronuncia": "S", "data_deposito": "14/06/1956",
        "epigrafe": "giudizio di legittimita costituzionale",
        "testo": "La Corte dichiara l'illegittimita della norma sulla pubblica sicurezza.",
        "dispositivo": "dichiara l'illegittimita costituzionale",
    },
    {
        "ecli": "ECLI:IT:COST:2024:203", "numero_pronuncia": "203", "anno_pronuncia": "2024",
        "tipologia_pronuncia": "O", "data_deposito": "20/11/2024",
        "epigrafe": "questione in materia di protezione dei dati personali",
        "testo": "La societa ricorrente lamenta la violazione della privacy.",
        "dispositivo": "dichiara manifestamente inammissibile la questione",
    },
]


def _build_small_index(path: Path) -> None:
    """Write a tiny but real cost.sqlite (2 decisions) at ``path``."""
    conn = db.connect(path, must_exist=False)
    try:
        db.create_schema(conn)
        db.insert_decisions(conn, [normalize_decision(r) for r in DECISIONS])
        db.set_meta(conn, "ingested_at", "2026-07-11T00:00:00+00:00")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def target(tmp_path, monkeypatch):
    """Point resolve_db_path at a fresh (missing) target and clear tuning env vars."""
    dest = tmp_path / "cache" / "cost.sqlite"
    monkeypatch.setenv("IT_ELI_CASELAW_DB", str(dest))
    monkeypatch.delenv("IT_ELI_CASELAW_INDEX_URL", raising=False)
    monkeypatch.delenv("IT_ELI_CASELAW_INDEX_SHA256", raising=False)
    monkeypatch.delenv("IT_ELI_CASELAW_AUTOBUILD", raising=False)
    return dest


async def test_cached_hit_short_circuits(target, monkeypatch):
    """An existing non-empty index is returned without any download or build."""
    target.parent.mkdir(parents=True, exist_ok=True)
    _build_small_index(target)

    def _boom(*a, **k):  # pragma: no cover - must never be reached
        raise AssertionError("provisioning attempted despite a cached index")

    monkeypatch.setattr(corpus, "_build_local", _boom)
    monkeypatch.setenv("IT_ELI_CASELAW_INDEX_URL", "")  # disable asset path too

    assert await corpus.ensure_index() == target


async def test_download_verified_asset_over_http(target, monkeypatch, tmp_path):
    """Real download + sha256 verification of a pre-built index over localhost HTTP."""
    served = tmp_path / "release"
    served.mkdir()
    asset = served / "cost.sqlite"
    _build_small_index(asset)
    sha = hashlib.sha256(asset.read_bytes()).hexdigest()
    (served / "cost.sqlite.sha256").write_text(f"{sha}  cost.sqlite\n", encoding="utf-8")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(served))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        monkeypatch.setenv("IT_ELI_CASELAW_INDEX_URL", f"http://127.0.0.1:{port}/cost.sqlite")
        # If the download path is skipped, a build would fail (no real dumps) -> disable it,
        # so the test can only pass via a successful verified download.
        monkeypatch.setenv("IT_ELI_CASELAW_AUTOBUILD", "0")

        path = await corpus.ensure_index()
        assert path == target and path.exists()

        conn = db.connect(path)
        try:
            assert db.stats(conn)["total"] == 2
            assert db.get_meta(conn, "provenance").startswith("release-asset")
        finally:
            conn.close()
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


async def test_sha256_mismatch_falls_through_to_build(target, monkeypatch, tmp_path):
    """A checksum mismatch rejects the download and falls back to the local build."""
    served = tmp_path / "release"
    served.mkdir()
    _build_small_index(served / "cost.sqlite")
    (served / "cost.sqlite.sha256").write_text(f"{'0' * 64}  cost.sqlite\n", encoding="utf-8")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(served))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        monkeypatch.setenv("IT_ELI_CASELAW_INDEX_URL", f"http://127.0.0.1:{port}/cost.sqlite")
        monkeypatch.setattr(corpus, "_build_local", lambda p: _build_small_index(p))

        path = await corpus.ensure_index()
        conn = db.connect(path)
        try:
            assert db.get_meta(conn, "provenance") is None  # built, not from the asset
            assert db.stats(conn)["total"] == 2
        finally:
            conn.close()
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


async def test_build_fallback_when_no_asset(target, monkeypatch):
    """With the asset path disabled, the index is built locally and provenance is stamped."""
    monkeypatch.setenv("IT_ELI_CASELAW_INDEX_URL", "")

    def _fake_build(path: Path) -> None:
        _build_small_index(path)

    monkeypatch.setattr(corpus, "_build_local", _fake_build_stamped(_fake_build))
    path = await corpus.ensure_index()
    conn = db.connect(path)
    try:
        assert db.stats(conn)["total"] == 2
        assert db.get_meta(conn, "provenance").startswith("local-build")
    finally:
        conn.close()


def _fake_build_stamped(inner):
    """Wrap a builder so it also stamps provenance, like the real _build_local."""
    def _run(path: Path) -> None:
        inner(path)
        corpus._stamp_provenance(path, "local-build (test)")
    return _run


async def test_all_paths_fail_raises_database_missing(target, monkeypatch):
    """No asset and a failing build surface the clear DatabaseMissingError."""
    monkeypatch.setenv("IT_ELI_CASELAW_INDEX_URL", "")

    def _explode(path: Path) -> None:
        raise RuntimeError("dumps unreachable")

    monkeypatch.setattr(corpus, "_build_local", _explode)
    with pytest.raises(db.DatabaseMissingError) as exc:
        await corpus.ensure_index()
    assert "italy-eli-mcp-caselaw-ingest" in str(exc.value)


async def test_autobuild_disabled_raises_without_building(target, monkeypatch):
    """IT_ELI_CASELAW_AUTOBUILD=0 skips the build entirely when no asset is available."""
    monkeypatch.setenv("IT_ELI_CASELAW_INDEX_URL", "")
    monkeypatch.setenv("IT_ELI_CASELAW_AUTOBUILD", "0")

    def _boom(path: Path) -> None:  # pragma: no cover - must never run
        raise AssertionError("build ran despite AUTOBUILD=0")

    monkeypatch.setattr(corpus, "_build_local", _boom)
    with pytest.raises(db.DatabaseMissingError):
        await corpus.ensure_index()
