"""Async httpx client for Normattiva with a session + AKN cache.

Normattiva has no JSON API. Fetching an act's Akoma Ntoso XML is a two-step,
cookie-bound dance (verified 2026-07-01):

1. GET an entry URL (a URN resolver ``/uri-res/N2Ls?urn:nir:...`` or an ``/eli/id/...``
   page). This returns HTML and sets a session cookie. The HTML contains a link
   ``caricaAKN?dataGU=YYYYMMDD&codiceRedaz=XXXXXXXX&dataVigenza=YYYYMMDD`` carrying
   the Gazzetta date + the redazionale code needed for the XML export.
2. GET ``/do/atto/caricaAKN?...`` *within the same session* -> Akoma Ntoso XML.

We keep our own backoff + disk cache (upstream rate limits are undocumented).
Point-in-time text (multivigenza) is selected by overriding ``dataVigenza``.
"""

from __future__ import annotations

import re

import anyio
import httpx

from .cache import HttpCache

DEFAULT_TIMEOUT = httpx.Timeout(45.0, connect=10.0)
USER_AGENT = (
    "it-eli-mcp/0.1.0 (+https://github.com/matematicsolutions/it-eli-mcp) "
    "Mozilla/5.0 (compatible)"
)

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3

# caricaAKN link inside the act page (HTML-escaped &amp; tolerated).
_CARICA_RE = re.compile(
    r"caricaAKN\?dataGU=(\d{8})&(?:amp;)?codiceRedaz=([0-9A-Za-z]+)"
    r"(?:&(?:amp;)?dataVigenza=(\d{8}))?"
)


class NotAvailableError(Exception):
    """The act resolved to a page but no Akoma Ntoso export link was found."""


class NormattivaClient:
    """Async Normattiva client. Use as ``async with NormattivaClient() as c: ...``."""

    def __init__(
        self,
        base_url: str = "https://www.normattiva.it",
        cache: HttpCache | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._cache = cache or HttpCache()
        self._http = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "it,en;q=0.8"},
        )

    async def __aenter__(self) -> NormattivaClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def _get_with_backoff(self, url: str, *, accept: str) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await self._http.get(url, headers={"Accept": accept})
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in _RETRY_STATUS or attempt == _MAX_ATTEMPTS - 1:
                    raise
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt == _MAX_ATTEMPTS - 1:
                    raise
            await anyio.sleep(0.5 * (2**attempt))
        assert last_exc is not None
        raise last_exc

    async def resolve_carica_params(self, entry_url: str) -> tuple[str, str, str | None]:
        """Resolve an entry URL to ``(dataGU, codiceRedaz, dataVigenza)``.

        Sets the session cookie as a side effect. Raises ``NotAvailableError`` if the
        page carries no ``caricaAKN`` link (act missing or not machine-exportable).
        """
        cache_key = "carica::" + entry_url
        cached = self._cache.get(cache_key)
        if isinstance(cached, list) and len(cached) == 3:
            return cached[0], cached[1], cached[2]

        resp = await self._get_with_backoff(entry_url, accept="text/html")
        m = _CARICA_RE.search(resp.text)
        if not m:
            raise NotAvailableError(
                f"No Akoma Ntoso export link on the act page for {entry_url!r}. "
                f"The act may not exist or may not be machine-exportable."
            )
        data_gu, codice, vigenza = m.group(1), m.group(2), m.group(3)
        self._cache.set(cache_key, [data_gu, codice, vigenza], ttl=HttpCache.ttl_for("list"))
        return data_gu, codice, vigenza

    async def fetch_akn(
        self, data_gu: str, codice_redaz: str, data_vigenza: str | None = None
    ) -> tuple[bytes, str]:
        """Fetch the Akoma Ntoso XML for an act. Returns ``(xml_bytes, source_url)``.

        Must be called after ``resolve_carica_params`` (same client = same session).
        """
        url = f"{self.base_url}/do/atto/caricaAKN?dataGU={data_gu}&codiceRedaz={codice_redaz}"
        if data_vigenza:
            url += f"&dataVigenza={data_vigenza}"
        cache_key = "akn::" + url
        cached = self._cache.get(cache_key)
        if isinstance(cached, bytes):
            return cached, url
        resp = await self._get_with_backoff(url, accept="application/xml, text/xml")
        xml = resp.content
        self._cache.set(cache_key, xml, ttl=HttpCache.ttl_for("act"))
        return xml, url

    async def get_akn(
        self, entry_url: str, data_vigenza: str | None = None
    ) -> tuple[bytes, str]:
        """Full flow: resolve an entry URL, then fetch the AKN XML in-session.

        ``data_vigenza`` (YYYYMMDD) overrides the point-in-time; when omitted the
        consolidated ("today") version linked on the page is used.
        """
        data_gu, codice, page_vigenza = await self.resolve_carica_params(entry_url)
        return await self.fetch_akn(data_gu, codice, data_vigenza or page_vigenza)
