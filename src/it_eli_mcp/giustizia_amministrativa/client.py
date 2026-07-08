"""Live client for the giustizia-amministrativa.it public decision search.

The Giustizia Amministrativa portal (Consiglio di Stato, C.G.A.R.S. and the 29
regional TAR seats) exposes its decision search as a Liferay portlet at
``/web/guest/dcsnprr``. There is no JSON API, but the portlet answers plain
HTTP: a GET on the search page yields a session cookie and a ``p_auth`` CSRF
token embedded in the page; a POST to the portlet action URL with that token
runs the search and returns server-rendered HTML with, for every hit, the
full-text URL on ``mdp.giustizia-amministrativa.it`` (including the
``nomeFile=..._NN.html`` type-code segment that the Open GA bulk export lacks)
and a NATIVE ECLI. The mdp endpoint then returns the decision as structured GA
XML. All verified live 2026-07-08 - see DISCOVERY.md for the transcript.

This reverses the earlier rejection of IT/ConsiglioDiStato: the bulk export
alone is still metadata-only, but the portal's own search supplies the missing
segment, so a reliable search -> full-text path exists. Totals at check time:
3 419 411 provvedimenti portal-wide, 501 032 Consiglio di Stato, 53 214
C.G.A.R.S.

Filter honesty notes (each verified by comparing totals):
- ``sede`` and ``tipo`` narrow server-side (e.g. 'responsabilita': 1 128 all
  seats -> 182 CdS -> 26 Milano).
- ``numero`` (provvedimento number) narrows server-side in ``provv`` mode.
- The portal's year field is a SILENT NO-OP for this action URL, so ``anno``
  is applied CLIENT-SIDE here, deterministically: the portal's decision id is
  ``YYYYNNNNN``, year first. ``total_found`` always reports the upstream
  (year-unfiltered) total.
- Pagination is likewise ignored by this action URL; the tool returns the
  first page (newest first), page size 20/40/60.
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx

from .records import GaDocument, GaHit, GaParseError, parse_document, parse_search_html

PORTAL_BASE = "https://www.giustizia-amministrativa.it"
SEARCH_PAGE_URL = f"{PORTAL_BASE}/web/guest/dcsnprr"
MDP_DOCUMENT_PREFIX = "https://mdp.giustizia-amministrativa.it/visualizza/?"

_PORTLET = "decisioni_pareri_web_DecisioniPareriWebPortlet_INSTANCE_XKc17mrB8J10"
_P = f"_{_PORTLET}_"

USER_AGENT = "it-eli-mcp-ga/0.4.0 (+https://github.com/matematicsolutions/it-eli-mcp)"

_P_AUTH_RE = re.compile(r"p_auth=([A-Za-z0-9]+)")

# The portlet's page-size select offers exactly these values; anything else
# silently falls back to 20.
_PAGE_SIZES = (20, 40, 60)

# Session cache: the p_auth token is bound to the JSESSIONID cookie. Tokens are
# short-lived; refresh after this many seconds or on a parse failure.
_SESSION_TTL_S = 600.0

_CDS = "Consiglio di Stato"
_CGARS = "C.G.A.R.S"
# TAR seats exactly as listed in the portal's sede select (option values).
_TAR_SEATS = (
    "Ancona", "Aosta", "Bari", "Bologna", "Bolzano", "Brescia", "Cagliari",
    "Campobasso", "Catania", "Catanzaro", "Firenze", "Genova", "L'Aquila",
    "Latina", "Lecce", "Milano", "Napoli", "Palermo", "Parma", "Perugia",
    "Pescara", "Potenza", "Reggio Calabria", "Roma", "Salerno", "Torino",
    "Trento", "Trieste", "Venezia",
)

_SEDE_ALIASES: dict[str, str] = {
    "cds": _CDS,
    "consiglio di stato": _CDS,
    "cgars": _CGARS,
    "c.g.a.r.s": _CGARS,
    "c.g.a.r.s.": _CGARS,
    **{seat.lower(): seat for seat in _TAR_SEATS},
    "l'aquila": "L'Aquila",
}

_TIPO_VALUES: dict[str, str] = {
    "sentenza": "Sentenza",
    "ordinanza": "Ordinanza",
    "decreto": "Decreto",
    "parere": "Parere",
    "plenaria": "P",
    "adunanza plenaria": "P",
    "adunanza generale": "C",
}


class GaError(Exception):
    """A giustizia-amministrativa.it request failed or returned the unexpected."""


def resolve_sede(sede: str | None) -> str | None:
    if not sede:
        return None
    key = sede.strip().lower().replace("t.a.r.", "").replace("tar ", "").strip()
    resolved = _SEDE_ALIASES.get(key) or _SEDE_ALIASES.get(sede.strip().lower())
    if not resolved:
        raise GaError(
            f"Unknown sede={sede!r}. Expected 'Consiglio di Stato', 'C.G.A.R.S' "
            f"or a TAR seat city: {', '.join(_TAR_SEATS)}."
        )
    return resolved


def resolve_tipo(tipo: str | None) -> str | None:
    if not tipo:
        return None
    resolved = _TIPO_VALUES.get(tipo.strip().lower())
    if not resolved:
        raise GaError(
            f"Unknown tipo={tipo!r}. Expected one of: "
            "sentenza, ordinanza, decreto, parere, plenaria, adunanza generale."
        )
    return resolved


def _page_size_for(limit: int) -> int:
    for size in _PAGE_SIZES:
        if limit <= size:
            return size
    return _PAGE_SIZES[-1]


class _Session:
    def __init__(self, cookies: httpx.Cookies, p_auth: str) -> None:
        self.cookies = cookies
        self.p_auth = p_auth
        self.fetched_at = time.monotonic()

    @property
    def stale(self) -> bool:
        return (time.monotonic() - self.fetched_at) > _SESSION_TTL_S


_session_cache: _Session | None = None


def _client(cookies: httpx.Cookies | None = None, timeout_s: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_s, connect=10.0),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        cookies=cookies,
    )


async def _fetch_session(timeout_s: float = 60.0) -> _Session:
    async with _client(timeout_s=timeout_s) as client:
        try:
            resp = await client.get(SEARCH_PAGE_URL)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise GaError(f"Could not open the GA search page: {exc}") from exc
        m = _P_AUTH_RE.search(resp.text)
        if not m:
            raise GaError(
                "No p_auth token on the GA search page - the portal layout may have changed."
            )
        return _Session(client.cookies, m.group(1))


async def _get_session(*, force_refresh: bool = False, timeout_s: float = 60.0) -> _Session:
    global _session_cache  # deliberate module-level session cache
    if force_refresh or _session_cache is None or _session_cache.stale:
        _session_cache = await _fetch_session(timeout_s=timeout_s)
    return _session_cache


def _search_params(session_p_auth: str) -> dict[str, str]:
    return {
        "p_p_id": _PORTLET,
        "p_p_lifecycle": "1",
        "p_p_state": "normal",
        "p_p_mode": "view",
        f"{_P}javax.portlet.action": "search",
        "p_auth": session_p_auth,
    }


async def _post_search(form: dict[str, str], timeout_s: float) -> tuple[int, list[GaHit]]:
    session = await _get_session(timeout_s=timeout_s)
    for attempt in (1, 2):
        async with _client(cookies=session.cookies, timeout_s=timeout_s) as client:
            try:
                resp = await client.post(
                    SEARCH_PAGE_URL, params=_search_params(session.p_auth), data=form
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise GaError(f"GA search request failed: {exc}") from exc
        try:
            return parse_search_html(resp.text)
        except GaParseError:
            if attempt == 1:  # stale p_auth/cookie pair - refresh once and retry
                session = await _get_session(force_refresh=True, timeout_s=timeout_s)
                continue
            raise
    raise GaError("unreachable")  # pragma: no cover


async def search(
    query: str | None = None,
    *,
    sede: str | None = None,
    tipo: str | None = None,
    numero: str | None = None,
    anno: str | None = None,
    limit: int = 20,
    timeout_s: float = 60.0,
) -> tuple[int, list[GaHit]]:
    """Search decisions. Returns (total_found_upstream, hits).

    Either ``query`` (full-text) or ``numero`` (decision-number lookup, optionally
    with client-side ``anno`` narrowing) must be provided; both together also work.
    """
    q = (query or "").strip()
    num = (numero or "").strip()
    if num and not re.fullmatch(r"\d{1,5}", num):
        raise GaError(f"numero must be 1-5 digits, got {numero!r}.")
    year = (anno or "").strip()
    if year and not re.fullmatch(r"\d{4}", year):
        raise GaError(f"anno must be a 4-digit year, got {anno!r}.")
    if not q and not num:
        raise GaError("Provide a full-text query, a decision numero, or both.")

    form = {
        f"{_P}searchtextProvvedimenti": q,
        f"{_P}sedeProvvedimenti": resolve_sede(sede) or "",
        f"{_P}TipoProvvedimentoItem": resolve_tipo(tipo) or "",
        f"{_P}isAdvancedSearch": "false",
        f"{_P}pageSize": str(_page_size_for(limit)),
    }
    if num:
        form[f"{_P}asSearchMode"] = "provv"
        form[f"{_P}numeroProvvedimenti"] = num

    total, hits = await _post_search(form, timeout_s)
    if year:
        hits = [h for h in hits if h.anno == year]
    return total, hits[:limit]


async def get_document(document_url: str, *, timeout_s: float = 60.0) -> GaDocument:
    """Fetch one decision's full text by its mdp ``document_url`` (from a search hit)."""
    url = (document_url or "").strip()
    if not url.startswith(MDP_DOCUMENT_PREFIX):
        raise GaError(
            f"document_url must start with {MDP_DOCUMENT_PREFIX!r} "
            "(take it verbatim from an it_ga_search hit)."
        )
    async with _client(timeout_s=timeout_s) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise GaError(f"GA document request failed: {exc}") from exc
    if resp.content.lstrip()[:5] == b"%PDF-":
        raise GaError(
            "This provvedimento is published as PDF only (no machine-readable GA XML). "
            "Relay the document_url to the user instead of quoting text from it."
        )
    try:
        return parse_document(resp.content)
    except GaParseError as exc:
        raise GaError(str(exc)) from exc


def source_url_for(hit_or_url: str | Any) -> str:
    """The grounding anchor for a GA decision is its mdp full-text URL itself."""
    if isinstance(hit_or_url, str):
        return hit_or_url
    return str(getattr(hit_or_url, "document_url", "") or SEARCH_PAGE_URL)
