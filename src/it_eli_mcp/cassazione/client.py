"""Live client for the Corte di Cassazione's SentenzeWeb Solr search.

SentenzeWeb (https://www.italgiure.giustizia.it/sncass/) is the Court's own free,
public search engine over its case law - distinct from ItalgiureWeb, the
subscription-gated full-database search used internally by the judiciary and paid
by practitioners. SentenzeWeb answers unauthenticated GET requests against a Solr
core reachable at:

    https://www.italgiure.giustizia.it/sncass/isapi/hc.dll/sn.solr/sn-collection/select

verified live (2026-07-07): HTTP 200, no auth headers/cookies required, returns
full OCR text (field ``ocr``) for civil (``kind:snciv``, ~190K) and criminal
(``kind:snpen``, ~238K) decisions, including the Labour (``szdec:L``) and Tax
(``szdec:5``) sub-chambers. See ``DISCOVERY.md`` for the verification transcript.

No ingest step, no local database: every tool call is a live query. Being a public
site (not a documented API), the endpoint path could change without notice - if
queries start failing, re-verify the path from the SentenzeWeb page's ``index.js``.
"""

from __future__ import annotations

import re
import ssl
from functools import lru_cache
from pathlib import Path
from typing import Any

import certifi
import httpx

from .records import Decision, normalize_decision

BASE_URL = "https://www.italgiure.giustizia.it/sncass/isapi/hc.dll/sn.solr/sn-collection/select"
USER_AGENT = "it-eli-mcp-cassazione/0.3.0 (+https://github.com/matematicsolutions/it-eli-mcp)"

# italgiure.giustizia.it's TLS handshake serves the wrong intermediate certificate
# (a "TI Trust Technologies DV CA" cross-cert, cross-signed by USERTrust) instead of
# the "TI Trust Technologies OV CA" that actually chains to the site's own leaf
# certificate. Browsers and Windows/Schannel-based tools (incl. curl on Windows)
# silently paper over this via AIA chasing; strict OpenSSL-based clients (httpx,
# requests, ...) do not, and fail with "unable to get local issuer certificate".
# The correct intermediate is fetchable from its own AIA URL and DOES chain to a
# root already in Mozilla's/certifi's trust store (USERTrust RSA CA), so this is a
# real, fixable server misconfiguration, not an untrusted/self-signed endpoint.
# Verified 2026-07-07; see DISCOVERY.md for the openssl s_client transcript.
_EXTRA_INTERMEDIATE = Path(__file__).parent / "certs" / "ti_trust_ov_ca.pem"


@lru_cache(maxsize=1)
def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.load_verify_locations(cafile=str(_EXTRA_INTERMEDIATE))
    return ctx

_ALL_FIELDS = "*"

# Reject characters that would let a caller break out of our controlled Solr query
# syntax (we build "ocr:\"<term>\"" ourselves; the term itself must not contain a
# literal quote or Solr boolean/range operators).
_UNSAFE_RE = re.compile(r'["{}\[\]]')


class CassazioneError(Exception):
    """A SentenzeWeb request failed or returned something we can't parse."""


def _sanitize_term(term: str) -> str:
    cleaned = _UNSAFE_RE.sub(" ", term).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        raise CassazioneError("Empty search query after sanitization.")
    return cleaned


def _kind_filter(chamber: str | None) -> str | None:
    if not chamber:
        return None
    c = chamber.strip().lower()
    if c in ("civ", "civile", "snciv"):
        return "snciv"
    if c in ("pen", "penale", "snpen"):
        return "snpen"
    raise CassazioneError(f"Unknown chamber={chamber!r}. Expected 'civile' or 'penale'.")


def _szdec_filter(sub_chamber: str | None) -> str | None:
    if not sub_chamber:
        return None
    s = sub_chamber.strip().lower()
    if s in ("lav", "lavoro", "labour", "l"):
        return "L"
    if s in ("trib", "tributaria", "tax", "5"):
        return "5"
    raise CassazioneError(
        f"Unknown sub_chamber={sub_chamber!r}. Expected 'lavoro' or 'tributaria'."
    )


async def _get(client: httpx.AsyncClient, params: dict[str, str]) -> dict[str, Any]:
    try:
        resp = await client.get(BASE_URL, params=params)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise CassazioneError(f"SentenzeWeb HTTP {exc.response.status_code}") from exc
    except httpx.TransportError as exc:
        raise CassazioneError(f"SentenzeWeb network error: {exc}") from exc
    try:
        result: dict[str, Any] = resp.json()
        return result
    except ValueError as exc:
        raise CassazioneError("SentenzeWeb returned non-JSON (endpoint may have moved).") from exc


async def search(
    query: str,
    *,
    chamber: str | None = None,
    sub_chamber: str | None = None,
    anno: str | None = None,
    limit: int = 20,
    timeout_s: float = 30.0,
) -> tuple[int, list[Decision], dict[str, list[str]]]:
    """Full-text search over ``ocr`` (the decision body). Returns (total_found,
    decisions, highlighting-by-sic_id)."""
    term = _sanitize_term(query)
    clauses = [f'ocr:"{term}"']
    kf = _kind_filter(chamber)
    if kf:
        clauses.append(f"kind:{kf}")
    sf = _szdec_filter(sub_chamber)
    if sf:
        clauses.append(f"szdec:{sf}")
    if anno:
        if not re.fullmatch(r"\d{4}", anno.strip()):
            raise CassazioneError(f"anno must be a 4-digit year, got {anno!r}.")
        clauses.append(f"anno:{anno.strip()}")

    params = {
        "q": " AND ".join(clauses),
        "rows": str(limit),
        "wt": "json",
        "hl": "true",
        "hl.fl": "ocr",
        "hl.snippets": "1",
        "hl.fragsize": "220",
    }
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_s, connect=10.0),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        verify=_ssl_context(),
    ) as client:
        data = await _get(client, params)

    resp = data.get("response", {})
    total = int(resp.get("numFound", 0))
    decisions: list[Decision] = []
    for raw in resp.get("docs", []):
        try:
            decisions.append(normalize_decision(raw))
        except ValueError:
            continue

    highlighting: dict[str, list[str]] = {}
    for doc_id, hl in (data.get("highlighting") or {}).items():
        frags = hl.get("ocr") if isinstance(hl, dict) else None
        if frags:
            highlighting[doc_id] = frags

    return total, decisions, highlighting


async def get_by_id(sic_id: str, *, timeout_s: float = 30.0) -> Decision | None:
    """Fetch one decision by its SentenzeWeb ``id`` (e.g. 'snciv2024D01234O')."""
    sic_id = sic_id.strip()
    if not sic_id or not re.fullmatch(r"[A-Za-z0-9]+", sic_id):
        raise CassazioneError(f"Invalid id={sic_id!r}: expected an alphanumeric SentenzeWeb id.")
    params = {"q": f"id:{sic_id}", "rows": "1", "wt": "json", "fl": _ALL_FIELDS}
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_s, connect=10.0),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        verify=_ssl_context(),
    ) as client:
        data = await _get(client, params)

    docs = data.get("response", {}).get("docs", [])
    if not docs:
        return None
    try:
        return normalize_decision(docs[0])
    except ValueError:
        return None
