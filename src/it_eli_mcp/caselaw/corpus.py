"""Lazy provisioning of the Corte Costituzionale case-law index (``cost.sqlite``).

The four ``it_case_*`` tools no longer require a manual ``italy-eli-mcp-caselaw-ingest``
run before they work. On first use they call :func:`ensure_index`, which returns a
ready-to-query SQLite path, provisioning it once if needed:

1. **env override / cache** - if ``IT_ELI_CASELAW_DB`` (or the default cache path) already
   holds a non-empty database, use it. Every later call is a pure offline query.
2. **release asset** - download a pre-built ``cost.sqlite`` from the GitHub release
   (``releases/latest/download/cost.sqlite``), verified against its ``.sha256`` sidecar,
   and place it atomically at the cache path. This is the fast path.
3. **local build** - if no verified release asset is available, build the index from the
   Corte Costituzionale official open data - the very same work the manual
   ``italy-eli-mcp-caselaw-ingest`` command does, now run automatically.
4. **clear error** - only if every provisioning path fails do we raise
   :class:`~it_eli_mcp.caselaw.db.DatabaseMissingError` with actionable guidance.

Governance: the data is always verbatim official material (a pre-built index is only
installed after its sha256 is verified; otherwise we build from the source dumps).
Provenance and freshness are stamped into the ``meta`` table and surfaced by
``it_case_stats`` - never a silent stale index.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from pathlib import Path

import anyio
import httpx

from . import db, ingest

# Pre-built index published as a GitHub release asset. The "latest" download URL
# self-activates the moment a release carrying cost.sqlite + cost.sqlite.sha256 is cut;
# until then the download simply 404s and we fall through to the local build.
DEFAULT_INDEX_URL = (
    "https://github.com/matematicsolutions/it-eli-mcp/releases/latest/download/cost.sqlite"
)
USER_AGENT = "it-eli-caselaw-mcp (+https://github.com/matematicsolutions/it-eli-mcp)"
_DOWNLOAD_TIMEOUT = httpx.Timeout(300.0, connect=15.0)
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}")

_ensure_lock = anyio.Lock()


def _asset_url() -> str:
    """Release-asset URL, overridable via ``IT_ELI_CASELAW_INDEX_URL`` ('' disables)."""
    return os.environ.get("IT_ELI_CASELAW_INDEX_URL", DEFAULT_INDEX_URL).strip()


def _autobuild_enabled() -> bool:
    """Whether to build locally from open data when no release asset is available."""
    return os.environ.get("IT_ELI_CASELAW_AUTOBUILD", "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


async def ensure_index() -> Path:
    """Return a ready-to-query index path, provisioning it once on first use.

    Raises :class:`~it_eli_mcp.caselaw.db.DatabaseMissingError` if every provisioning
    path fails (network down and no cached index), so callers can surface the existing
    ``index_missing`` error unchanged.
    """
    target = db.resolve_db_path()
    if _is_ready(target):
        return target

    async with _ensure_lock:
        # Re-check under the lock: a concurrent first call may have just provisioned it.
        if _is_ready(target):
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        errors: list[str] = []

        url = _asset_url()
        if url:
            try:
                await _download_verified_asset(url, target)
                return target
            except Exception as exc:  # any failure (404, network, bad hash) -> next path
                errors.append(f"release-asset ({url}): {type(exc).__name__}: {exc}")

        if _autobuild_enabled():
            try:
                await anyio.to_thread.run_sync(_build_local, target)
                return target
            except Exception as exc:  # fall through to the clear error below
                errors.append(f"local-build: {type(exc).__name__}: {exc}")

        raise db.DatabaseMissingError(_failure_message(target, errors))


def _is_ready(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


async def _download_verified_asset(url: str, target: Path) -> None:
    """Download the pre-built index and verify its sha256 before installing it atomically.

    We refuse to install an index we cannot verify: if no checksum is available (env
    ``IT_ELI_CASELAW_INDEX_SHA256`` or a ``<url>.sha256`` sidecar), this raises and the
    caller falls back to building from the official source data.
    """
    async with httpx.AsyncClient(
        timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        expected = await _expected_sha256(client, url)
        if not expected:
            raise RuntimeError(
                "no sha256 checksum available; refusing to install an unverified index"
            )
        tmp_path = target.with_suffix(target.suffix + ".part")
        digest = hashlib.sha256()
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with tmp_path.open("wb") as fh:
                async for chunk in resp.aiter_bytes():
                    fh.write(chunk)
                    digest.update(chunk)
        actual = digest.hexdigest()
        if actual.lower() != expected.lower():
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(f"sha256 mismatch: expected {expected}, got {actual}")

    _stamp_provenance(tmp_path, f"release-asset ({url})")
    os.replace(tmp_path, target)


async def _expected_sha256(client: httpx.AsyncClient, url: str) -> str | None:
    """Resolve the expected checksum: pinned env var first, else the ``.sha256`` sidecar."""
    pinned = os.environ.get("IT_ELI_CASELAW_INDEX_SHA256", "").strip()
    if pinned:
        match = _SHA256_RE.search(pinned)
        return match.group(0) if match else None
    resp = await client.get(f"{url}.sha256")
    if resp.status_code != 200:
        return None
    match = _SHA256_RE.search(resp.text)
    return match.group(0) if match else None


def _build_local(target: Path) -> None:
    """Build the index from the Court's official open data (same as the ingest command)."""
    ingest.build_index(target, list(ingest.DUMP_URLS), progress=True)
    _stamp_provenance(target, "local-build (Corte Costituzionale open data)")


def _stamp_provenance(path: Path, provenance: str) -> None:
    """Record how this index was provisioned, so ``it_case_stats`` can state it."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('provenance', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (provenance,),
        )
        conn.commit()
    finally:
        conn.close()


def _failure_message(target: Path, errors: list[str]) -> str:
    detail = " | ".join(errors) if errors else "no provisioning path was attempted"
    return (
        f"Could not provision the Corte Costituzionale case-law index at {target}. "
        f"Auto-provisioning failed ({detail}). "
        f"Check network access, or build it manually with `italy-eli-mcp-caselaw-ingest` "
        f"(downloads the Court's open data and indexes it), then retry."
    )
