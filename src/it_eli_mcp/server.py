"""FastMCP entry point - Italian legislation tools over Normattiva (Akoma Ntoso / ELI).

Run:

    python -m it_eli_mcp.server

Configuration via env:

- ``IT_ELI_CACHE_DIR`` (default ``~/.matematic/cache/it-eli``)
- ``IT_ELI_AUDIT_DIR`` (default ``~/.matematic/audit``)
- ``IT_ELI_BASE_URL`` (default ``https://www.normattiva.it``)
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from typing import Any

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .akn import find_article, parse_akn
from .audit import AuditLogger, hash_input, timer
from .caselaw import corpus as ccorpus
from .caselaw import db as cdb
from .caselaw.citations import build_ecli as cc_build_ecli
from .caselaw.citations import parse_ecli as cc_parse_ecli
from .caselaw.models import DecisionFull as CaseDecisionFull
from .caselaw.models import RecentItem as CaseRecentItem
from .caselaw.models import SearchHit as CaseSearchHit
from .caselaw.models import SearchResult as CaseSearchResult
from .caselaw.models import Stats as CaseStats
from .cassazione import client as cass_client
from .cassazione.client import CassazioneError
from .cassazione.models import CassDecisionFull, CassSearchHit, CassSearchResult
from .citations import build_contract, iso_to_vigenza
from .client import NormattivaClient, NotAvailableError
from .giustizia_amministrativa import client as ga_client
from .giustizia_amministrativa.client import GaError
from .giustizia_amministrativa.models import GaDecisionFull, GaSearchHit, GaSearchResult
from .models import (
    ActInfo,
    ActText,
    CodeEntry,
    ResolveQuery,
    ResolveResult,
    TextFormat,
)
from .urn import CODES, NORMATTIVA_BASE, UrnRef, build_urn, entry_url, parse_urn

INSTRUCTIONS = """\
This MCP server exposes Italian federal legislation via Normattiva (rechtsinformationen's Italian counterpart), the official portal of the Ministero della Giustizia. Italy is the EU's largest legal market by number of lawyers. There is no JSON API: acts are fetched as Akoma Ntoso XML through a session-bound flow, and every response carries the citation contract - `eli_uri` (read from the act's ELI), `urn` (URN:NIR), `human_readable_citation`, `source_url` - plus a `dataset_note`.

## Identifiers

- **URN:NIR** - `urn:nir:{authority}:{type}:{date};{number}`, e.g. `urn:nir:stato:legge:1990-08-07;241`. A PARTIAL urn with year only (`urn:nir:stato:legge:1990;241`) also resolves - so you can cite an act you only know as "L. 241/1990".
- **ELI** - `eli/id/{year}/{month}/{day}/{code}/CONSOLIDATED`, embedded in the act. Read it from `eli_uri`; never invent it.

## Call order

1. `it_list_codes` - the major Italian codes and consolidated acts (Codice civile, penale, di procedura, privacy/GDPR, CAD, D.Lgs. 231/2001, Costituzione ...) with their canonical URN. Start here when the user names a code.
2. `it_resolve` - turn act coordinates (`act_type`, `year`, `number`) into a canonical, resolvable URN + `source_url`. Use when the user cites "D.Lgs. 231/2001" or "legge 241 del 1990". Offline; no fetch.
3. `it_get_act` - fetch act metadata (title, date, ELI, article_count) for a `reference` (a code name, a URN, an ELI path, or a normattiva.it URL).
4. `it_get_text` - fetch the text of a whole act or a single `article` (e.g. `"2043"` for art. 2043 c.c.). Pass `at_date` (ISO, e.g. `"2020-01-01"`) for the point-in-time (multivigenza) version as it stood on that date.

### Constitutional case law (Corte Costituzionale)

These tools run on a LOCAL full-text index of every Constitutional Court decision since 1956 (native ECLI, full reasoning + operative part), built from the Court's official open data. Scope is the Constitutional Court ONLY - not the Corte di Cassazione (subscription-gated) or the administrative courts.

- `it_case_search` - full-text search over the decisions; filter by `anno` (year) and `tipologia` ('S' sentenza / 'O' ordinanza). Accent-insensitive. Returns ranked hits with ECLI, citation, snippet.
- `it_case_get_decision` - the full text of one decision, by `ecli` (`ECLI:IT:COST:2024:1`) or by `anno` + `numero`.
- `it_case_recent` - the most recent decisions (newest first).
- `it_case_stats` - index coverage and freshness (totals, year range, counts by type, last build time).

The index is provisioned AUTOMATICALLY on the first `it_case_*` call (a pre-built index is downloaded and sha256-verified, or built from the Court's open data if none is published) and cached under `~/.matematic`; there is no manual step. `it_case_stats` reports `provenance` and `ingested_at` so you can state the index's freshness. The `index_missing` error appears only if every provisioning path fails (e.g. no network on a fresh machine); then `italy-eli-mcp-caselaw-ingest` builds it manually. The legislation tools above fetch live and need no index.

### Supreme Court case law (Corte di Cassazione, SentenzeWeb) - LIVE, no ingest

These tools query SentenzeWeb (italgiure.giustizia.it/sncass), the Court's own free public search engine, live on every call - no local index to build. This is NOT the subscription-gated ItalgiureWeb full-database search used by the judiciary and paid by practitioners; SentenzeWeb is a distinct, keyless, IODL-2.0-licensed public service covering civil and criminal decisions with full OCR text, including the Labour and Tax sub-chambers.

- `it_cassazione_search` - full-text search over decision bodies (`query`), with optional `chamber` ('civile'/'penale'), `sub_chamber` ('lavoro'/'tributaria'), and `anno` filters. Returns ranked hits with a highlighted snippet.
- `it_cassazione_get` - the full text of one decision by its SentenzeWeb `id` (returned as `sic_id` from search).

### Administrative case law (Consiglio di Stato, C.G.A.R.S., TAR) - LIVE, no ingest

These tools query the Giustizia Amministrativa portal's own public decision search (www.giustizia-amministrativa.it) live on every call - keyless, no local index. One backend covers the WHOLE administrative jurisdiction: Consiglio di Stato (501K+ provvedimenti), C.G.A.R.S. (Sicily, 53K+) and the 29 regional TAR seats - 3.4M+ decisions portal-wide. Search hits carry the court's NATIVE ECLI (e.g. `ECLI:IT:CDS:2026:5450SENT`); never invent one.

- `it_ga_search` - full-text search (`query`) and/or decision-number lookup (`numero`), with optional `sede` ('Consiglio di Stato', 'C.G.A.R.S', or a TAR seat city like 'Roma'/'Milano'), `tipo` ('sentenza'/'ordinanza'/'decreto'/'parere'/'plenaria'), and `anno`. `sede`, `tipo` and `numero` filter server-side; `anno` is applied client-side over the returned page (the portal's own year field is a no-op), so for an exact lookup pass `numero` + `anno` + `sede`. Returns newest-first hits with ECLI, citation, snippet and `document_url`.
- `it_ga_get_decision` - the full text of one decision by its `document_url` (take it verbatim from a search hit). Hits with `document_format` 'xml' return machine-readable full text; a few provvedimenti are published PDF-only ('pdf') - for those, relay the `document_url` to the user instead of quoting text.

## Hard constraints

- **ELI/URN are the keys to citability** - relay `human_readable_citation` + `source_url` to the user (e.g. "Codice civile, art. 2043 - urn:nir:stato:regio.decreto:1942-03-16;262").
- **No modification of official text** - the act is returned verbatim from Normattiva, only whitespace-normalized.
- **Point-in-time** - without `at_date` the text is the version in force TODAY (consolidated). Say which version you quoted.
- **Audit log JSONL** - every tool call appends to `~/.matematic/audit/it-eli-mcp.jsonl` (metadata + input hash only).
- **Licence** - Italian official texts are public (art. 5 l. 633/1941) and Normattiva declares CC-BY-4.0; cite the source. Do not bulk-harvest.

## Error iteration

Tools return a structured error with a `[code]` prefix:
- `invalid_arg` - a reference or coordinate is malformed. Expected e.g. a URN `urn:nir:stato:legge:1990-08-07;241`, an ELI `eli/id/1990/08/18/090G0294`, or a known code name (see `it_list_codes`).
- `not_available` - the reference resolved to a page but Normattiva exposes no machine-readable (Akoma Ntoso) export for it. The act may not exist; check the coordinates.
- `not_found` - a requested `article` does not exist in the act.
- `unsupported_format` - `format` for `it_get_text` must be `text` or `akn_xml`.
- `parse_error` - the Akoma Ntoso XML could not be parsed. Retry once, then surface.
- `upstream_error` - a Normattiva network/HTTP error. Retry once before surfacing.
- `index_missing` - automatic provisioning of the constitutional case-law index failed (no cached index, the pre-built asset was unreachable, and the local build could not run - typically no network). Retry when online, or run `italy-eli-mcp-caselaw-ingest` to build it manually.
- `query_error` - a case-law search query could not be parsed (e.g. empty after sanitization).
- `cassazione_error` - a SentenzeWeb request failed, returned no usable JSON, or the query/id was invalid.
- `ga_error` - a giustizia-amministrativa.it request failed, the response did not match the known portal layout, or an argument (sede/tipo/numero/anno/document_url) was invalid.

## Response style

- Cite in Italian convention with the identifier: "Legge 7 agosto 1990, n. 241 (urn:nir:stato:legge:1990-08-07;241)".
- NEVER invent an ELI, a URN, an article number or a date - take each from the response.
- State whether you quoted the consolidated (today) or a point-in-time version.
"""


class ITError(Exception):
    """Structured error for it-eli MCP tools - visible to the LLM with a [code] prefix."""

    VALID_CODES = frozenset({
        "invalid_arg",
        "not_available",
        "not_found",
        "unsupported_format",
        "parse_error",
        "upstream_error",
        "index_missing",
        "query_error",
        "cassazione_error",
        "ga_error",
    })

    def __init__(self, code: str, message: str):
        if code not in self.VALID_CODES:
            raise ValueError(f"Unknown ITError code: {code}. Valid: {sorted(self.VALID_CODES)}")
        self.code = code
        super().__init__(f"[{code}] {message}")


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    idempotentHint=True,
    destructiveHint=False,
    openWorldHint=True,  # upstream Normattiva live
)

mcp: FastMCP = FastMCP(name="it-eli-mcp", instructions=INSTRUCTIONS)


def _base_url() -> str:
    return os.environ.get("IT_ELI_BASE_URL", NORMATTIVA_BASE).rstrip("/")


def _audit() -> AuditLogger:
    return AuditLogger()


def _maybe_urn(reference: str) -> UrnRef | None:
    """Parse ``reference`` as a URN, or return None if it is not one (code name / ELI / URL)."""
    with contextlib.suppress(ValueError):
        return parse_urn(reference)
    return None


def _map_error(exc: Exception) -> Exception:
    if isinstance(exc, NotAvailableError):
        return ITError("not_available", str(exc))
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ITError("upstream_error", f"Normattiva error: {type(exc).__name__}: {exc}")
    return exc


# ---------------------------------------------------------------------------
# it_list_codes
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def it_list_codes() -> list[CodeEntry]:
    """List the major Italian codes and consolidated acts with their canonical URN.

    A curated, verified dictionary (Codice civile/penale/procedura, Codice privacy,
    CAD, D.Lgs. 231/2001, Costituzione, L. 241/1990). Feed any ``urn`` to
    ``it_get_act`` / ``it_get_text``.
    """
    audit = _audit()
    with timer() as t:
        entries = [
            CodeEntry(key=key, urn=data["urn"], label=data["label"])
            for key, data in CODES.items()
        ]
    audit.log(
        tool="it_list_codes",
        input_hash=hash_input({}),
        output_count_or_size=len(entries),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return entries


# ---------------------------------------------------------------------------
# it_resolve
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def it_resolve(query: ResolveQuery) -> ResolveResult:
    """Build a canonical, resolvable URN:NIR from act coordinates.

    Offline (no network). ``act_type`` accepts friendly forms ('legge', 'd.lgs',
    'dpr', 'regio.decreto'). With only ``year`` + ``number`` the partial URN still
    resolves on Normattiva; add ``month``/``day`` for the exact promulgation date.

    Args:
        query: ``ResolveQuery`` (act_type, year, number, month?, day?, authority).

    Returns:
        ``ResolveResult`` with ``urn``, ``human_readable_citation``, ``source_url``.
    """
    audit = _audit()
    input_hash = hash_input(query.model_dump(mode="json"))
    with timer() as t:
        try:
            urn = build_urn(
                query.act_type,
                query.year,
                query.number,
                month=query.month,
                day=query.day,
                authority=query.authority,
            )
            ref = parse_urn(urn)
            source = f"{_base_url()}/uri-res/N2Ls?{urn}"
            result = ResolveResult(
                urn=urn,
                human_readable_citation=ref.human_label(),
                source_url=source,
            )
        except ValueError as exc:
            audit.log(
                tool="it_resolve", input_hash=input_hash, output_count_or_size=0,
                duration_ms=t.duration_ms, status="error", error=str(exc),
            )
            raise ITError("invalid_arg", str(exc)) from exc
    audit.log(
        tool="it_resolve", input_hash=input_hash, output_count_or_size=1,
        duration_ms=t.duration_ms, status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# it_get_act
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def it_get_act(reference: str) -> ActInfo:
    """Fetch act metadata from Normattiva.

    Args:
        reference: a code name ("codice civile"), a URN
            ("urn:nir:stato:legge:1990-08-07;241"), an ELI path
            ("eli/id/1990/08/18/090G0294"), or a normattiva.it URL.

    Returns:
        ``ActInfo`` with ``eli_uri``, ``urn``, ``human_readable_citation``,
        ``title``, ``doc_date``, ``article_count``, ``source_url``.
    """
    audit = _audit()
    input_hash = hash_input({"reference": reference})
    base = _base_url()

    try:
        url = entry_url(reference)
    except ValueError as exc:
        raise ITError("invalid_arg", str(exc)) from exc
    urn_ref = _maybe_urn(reference)

    with timer() as t:
        try:
            async with NormattivaClient(base_url=base) as client:
                xml, _src = await client.get_akn(url)
            doc = parse_akn(xml)
        except NotAvailableError as exc:
            audit.log(tool="it_get_act", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms, status="error", error=str(exc))
            raise ITError("not_available", str(exc)) from exc
        except ValueError as exc:
            audit.log(tool="it_get_act", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms, status="error", error=str(exc))
            raise ITError("parse_error", str(exc)) from exc
        except Exception as exc:
            audit.log(tool="it_get_act", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms, status="error", error=f"{type(exc).__name__}: {exc}")
            raise _map_error(exc) from exc

    contract = build_contract(doc, urn_ref, base_url=base)
    act = ActInfo(
        eli_uri=contract["eli_uri"],
        urn=contract["urn"],
        human_readable_citation=contract["human_readable_citation"],
        title=contract["title"],
        doc_date=contract["doc_date"],
        article_count=doc.article_count(),
        source_url=contract["source_url"] or base,
    )
    audit.log(tool="it_get_act", input_hash=input_hash, output_count_or_size=1,
              duration_ms=t.duration_ms, status="ok")
    return act


# ---------------------------------------------------------------------------
# it_get_text
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def it_get_text(
    reference: str,
    article: str | None = None,
    at_date: str | None = None,
    format: TextFormat = "text",
) -> ActText:
    """Fetch the text of a whole act or a single article.

    Args:
        reference: a code name, URN, ELI path, or normattiva.it URL.
        article: an article number ("2043", "art. 2043", "2043-bis"). Omit for the whole act.
        at_date: ISO date ("2020-01-01") for the point-in-time (multivigenza) version;
            omit for the version in force today (consolidated).
        format: ``"text"`` (extracted, whitespace-normalized) or ``"akn_xml"`` (raw
            Akoma Ntoso; only valid for the whole act).

    Returns:
        ``ActText`` with the citation contract, ``content``, and article metadata.
    """
    audit = _audit()
    input_hash = hash_input(
        {"reference": reference, "article": article, "at_date": at_date, "format": format}
    )
    base = _base_url()

    if format not in ("text", "akn_xml"):
        raise ITError("unsupported_format", f"Unsupported format: {format!r}. Allowed: text, akn_xml.")
    if format == "akn_xml" and article is not None:
        raise ITError("unsupported_format", "akn_xml returns the whole act; drop 'article'.")

    try:
        url = entry_url(reference)
    except ValueError as exc:
        raise ITError("invalid_arg", str(exc)) from exc
    urn_ref = _maybe_urn(reference)

    vigenza = iso_to_vigenza(at_date)
    if at_date and vigenza is None:
        raise ITError("invalid_arg", f"at_date must be ISO (YYYY-MM-DD), got {at_date!r}.")

    with timer() as t:
        try:
            async with NormattivaClient(base_url=base) as client:
                xml, _src = await client.get_akn(url, data_vigenza=vigenza)
            if format == "akn_xml":
                doc = parse_akn(xml)  # still parse for the contract
                content = xml.decode("utf-8", errors="replace")
                art_obj = None
            else:
                doc = parse_akn(xml)
                if article is not None:
                    art_obj = find_article(doc, article)
                    if art_obj is None:
                        raise ITError(
                            "not_found",
                            f"Article {article!r} not found in the act "
                            f"({doc.article_count()} articles).",
                        )
                    content = (f"{art_obj.num} {art_obj.heading}\n{art_obj.text}"
                               if art_obj.heading else f"{art_obj.num}\n{art_obj.text}").strip()
                else:
                    art_obj = None
                    content = "\n\n".join(
                        f"{a.num or ''} {a.heading or ''}".strip() + ("\n" + a.text if a.text else "")
                        for a in doc.articles
                    ).strip()
        except ITError:
            audit.log(tool="it_get_text", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms, status="error")
            raise
        except NotAvailableError as exc:
            audit.log(tool="it_get_text", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms, status="error", error=str(exc))
            raise ITError("not_available", str(exc)) from exc
        except ValueError as exc:
            audit.log(tool="it_get_text", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms, status="error", error=str(exc))
            raise ITError("parse_error", str(exc)) from exc
        except Exception as exc:
            audit.log(tool="it_get_text", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms, status="error", error=f"{type(exc).__name__}: {exc}")
            raise _map_error(exc) from exc

    contract = build_contract(doc, urn_ref, base_url=base)
    result = ActText(
        eli_uri=contract["eli_uri"],
        urn=contract["urn"],
        human_readable_citation=contract["human_readable_citation"],
        source_url=contract["source_url"] or base,
        at_date=at_date,
        article=article,
        article_num=art_obj.num if art_obj else None,
        article_heading=art_obj.heading if art_obj else None,
        format=format,
        content=content,
        byte_size=len(content.encode("utf-8")),
        article_count=doc.article_count(),
    )
    audit.log(tool="it_get_text", input_hash=input_hash, output_count_or_size=result.byte_size,
              duration_ms=t.duration_ms, status="ok")
    return result


# ---------------------------------------------------------------------------
# Constitutional case law (Corte Costituzionale) - local FTS5 index
# ---------------------------------------------------------------------------


async def _open_caselaw() -> sqlite3.Connection:
    """Lazily provision the index on first use, then open it for a read-only query.

    ``ensure_index`` downloads a verified pre-built index or builds it from the Court's
    open data; only if every provisioning path fails do we surface ``index_missing``.
    """
    try:
        path = await ccorpus.ensure_index()
    except cdb.DatabaseMissingError as exc:
        raise ITError("index_missing", str(exc)) from exc
    return cdb.connect(path, must_exist=True)


@mcp.tool(annotations=READ_ONLY)
async def it_case_search(
    query: str,
    anno: str | None = None,
    tipologia: str | None = None,
    limit: int = 20,
) -> CaseSearchResult:
    """Full-text search of Corte Costituzionale (Constitutional Court) decisions.

    Args:
        query: search terms (Italian; accents are ignored by the index).
        anno: optional year filter (e.g. "2024").
        tipologia: optional type filter, "S" (sentenza) or "O" (ordinanza).
        limit: max hits (1..100).

    Returns:
        ``CaseSearchResult`` with ranked ``hits`` (ecli, citation, snippet, source_url).
    """
    audit = _audit()
    input_hash = hash_input({"q": query, "anno": anno, "tipologia": tipologia, "limit": limit})
    if not 1 <= limit <= 100:
        raise ITError("invalid_arg", f"limit={limit} out of range 1..100.")
    with timer() as t:
        conn = await _open_caselaw()
        try:
            rows = cdb.search(conn, query, anno=anno, tipologia=tipologia, limit=limit)
        except ValueError as exc:
            audit.log(tool="it_case_search", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms, status="error", error=str(exc))
            raise ITError("query_error", str(exc)) from exc
        finally:
            conn.close()
    result = CaseSearchResult(
        query=query,
        total_returned=len(rows),
        hits=[CaseSearchHit.model_validate(r) for r in rows],
    )
    audit.log(tool="it_case_search", input_hash=input_hash, output_count_or_size=len(rows),
              duration_ms=t.duration_ms, status="ok")
    return result


@mcp.tool(annotations=READ_ONLY)
async def it_case_get_decision(
    ecli: str | None = None,
    anno: str | None = None,
    numero: str | None = None,
) -> CaseDecisionFull:
    """Fetch the full text of one Constitutional Court decision, by ECLI or year + number.

    Args:
        ecli: an ECLI, e.g. "ECLI:IT:COST:2024:1".
        anno: year (used with ``numero`` when ``ecli`` is not given).
        numero: decision number (used with ``anno``).

    Returns:
        ``CaseDecisionFull`` with epigrafe, testo, dispositivo and the citation contract.
    """
    audit = _audit()
    input_hash = hash_input({"ecli": ecli, "anno": anno, "numero": numero})

    if ecli:
        resolved = ecli.strip()
        if cc_parse_ecli(resolved) is None:
            raise ITError("invalid_arg", f"Not a Constitutional-Court ECLI: {ecli!r}. "
                                         f"Expected e.g. 'ECLI:IT:COST:2024:1'.")
    elif anno and numero:
        resolved = cc_build_ecli(anno.strip(), numero.strip())
    else:
        raise ITError("invalid_arg", "Provide either 'ecli' or both 'anno' and 'numero'.")

    with timer() as t:
        conn = await _open_caselaw()
        try:
            row = cdb.get_by_ecli(conn, resolved)
        finally:
            conn.close()
    if row is None:
        audit.log(tool="it_case_get_decision", input_hash=input_hash, output_count_or_size=0,
                  duration_ms=t.duration_ms, status="error", error="not_found")
        raise ITError("not_found", f"No decision {resolved} in the case-law index.")
    decision = CaseDecisionFull.model_validate(row)
    audit.log(tool="it_case_get_decision", input_hash=input_hash, output_count_or_size=1,
              duration_ms=t.duration_ms, status="ok")
    return decision


@mcp.tool(annotations=READ_ONLY)
async def it_case_recent(limit: int = 20) -> list[CaseRecentItem]:
    """The most recent Constitutional Court decisions in the index (newest first).

    Args:
        limit: max items (1..100).
    """
    audit = _audit()
    input_hash = hash_input({"limit": limit})
    if not 1 <= limit <= 100:
        raise ITError("invalid_arg", f"limit={limit} out of range 1..100.")
    with timer() as t:
        conn = await _open_caselaw()
        try:
            rows = cdb.recent(conn, limit=limit)
        finally:
            conn.close()
    items = [CaseRecentItem.model_validate(r) for r in rows]
    audit.log(tool="it_case_recent", input_hash=input_hash, output_count_or_size=len(items),
              duration_ms=t.duration_ms, status="ok")
    return items


@mcp.tool(annotations=READ_ONLY)
async def it_case_stats() -> CaseStats:
    """Constitutional case-law index coverage and freshness (totals, years, last build)."""
    audit = _audit()
    with timer() as t:
        conn = await _open_caselaw()
        try:
            s = cdb.stats(conn)
            ingested_at = cdb.get_meta(conn, "ingested_at")
            provenance = cdb.get_meta(conn, "provenance")
        finally:
            conn.close()
    result = CaseStats(
        total=s["total"],
        year_min=s["year_min"],
        year_max=s["year_max"],
        by_tipologia=s["by_tipologia"],
        ingested_at=ingested_at,
        provenance=provenance,
    )
    audit.log(tool="it_case_stats", input_hash=hash_input({}), output_count_or_size=s["total"],
              duration_ms=t.duration_ms, status="ok")
    return result


# ---------------------------------------------------------------------------
# Supreme Court case law (Corte di Cassazione) - live SentenzeWeb Solr search
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def it_cassazione_search(
    query: str,
    chamber: str | None = None,
    sub_chamber: str | None = None,
    anno: str | None = None,
    limit: int = 20,
) -> CassSearchResult:
    """Full-text search of Corte di Cassazione (Supreme Court) decisions, live.

    Queries SentenzeWeb (the Court's own free public search engine) in real time -
    no local index. Free-text search matches the decision body (``ocr``).

    Args:
        query: search terms, matched as a phrase against the decision text.
        chamber: optional, "civile" (civil) or "penale" (criminal).
        sub_chamber: optional, "lavoro" (Labour) or "tributaria" (Tax) - both are
            sub-chambers of the civil section.
        anno: optional 4-digit year filter (decision year, e.g. "2021").
        limit: max hits (1..100).

    Returns:
        ``CassSearchResult`` with ``total_found`` (index-wide) and ranked ``hits``
        (sic_id, citation, snippet, source_url).
    """
    audit = _audit()
    input_hash = hash_input(
        {"q": query, "chamber": chamber, "sub_chamber": sub_chamber, "anno": anno, "limit": limit}
    )
    if not 1 <= limit <= 100:
        raise ITError("invalid_arg", f"limit={limit} out of range 1..100.")
    with timer() as t:
        try:
            total, decisions, highlighting = await cass_client.search(
                query, chamber=chamber, sub_chamber=sub_chamber, anno=anno, limit=limit
            )
        except CassazioneError as exc:
            audit.log(tool="it_cassazione_search", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms, status="error", error=str(exc))
            raise ITError("cassazione_error", str(exc)) from exc
    hits = []
    for d in decisions:
        row: dict[str, Any] = dict(d.as_row())
        frags = highlighting.get(d.sic_id) or highlighting.get(f"{d.kind}{d.numdec}{d.anno}") or []
        row["snippet"] = " ... ".join(frags) if frags else (d.testo[:220] if d.testo else None)
        hits.append(CassSearchHit.model_validate(row))
    result = CassSearchResult(query=query, total_found=total, total_returned=len(hits), hits=hits)
    audit.log(tool="it_cassazione_search", input_hash=input_hash, output_count_or_size=len(hits),
              duration_ms=t.duration_ms, status="ok")
    return result


@mcp.tool(annotations=READ_ONLY)
async def it_cassazione_get(sic_id: str) -> CassDecisionFull:
    """Fetch the full text of one Corte di Cassazione decision, live, by its SentenzeWeb id.

    Args:
        sic_id: the SentenzeWeb ``id`` (e.g. "snciv2024D01234O"), as returned by
            ``it_cassazione_search`` hits.

    Returns:
        ``CassDecisionFull`` with the full OCR text, massima (summary/holding
        extract), and the citation contract.
    """
    audit = _audit()
    input_hash = hash_input({"sic_id": sic_id})
    with timer() as t:
        try:
            decision = await cass_client.get_by_id(sic_id)
        except CassazioneError as exc:
            audit.log(tool="it_cassazione_get", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms, status="error", error=str(exc))
            raise ITError("cassazione_error", str(exc)) from exc
    if decision is None:
        audit.log(tool="it_cassazione_get", input_hash=input_hash, output_count_or_size=0,
                  duration_ms=t.duration_ms, status="error", error="not_found")
        raise ITError("not_found", f"No Cassazione decision with id {sic_id!r}.")
    result = CassDecisionFull.model_validate(decision.as_row())
    audit.log(tool="it_cassazione_get", input_hash=input_hash, output_count_or_size=1,
              duration_ms=t.duration_ms, status="ok")
    return result


# ---------------------------------------------------------------------------
# Administrative case law (Consiglio di Stato / C.G.A.R.S. / TAR) - live portal
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def it_ga_search(
    query: str | None = None,
    sede: str | None = None,
    tipo: str | None = None,
    numero: str | None = None,
    anno: str | None = None,
    limit: int = 20,
) -> GaSearchResult:
    """Search Italian administrative case law (Consiglio di Stato, C.G.A.R.S., TAR), live.

    Queries the Giustizia Amministrativa portal's own public decision search in
    real time - one backend for the whole administrative jurisdiction (3.4M+
    provvedimenti). Provide a full-text ``query``, a decision ``numero``, or both.

    Args:
        query: full-text search terms, matched against the decision text.
        sede: optional court seat - "Consiglio di Stato", "C.G.A.R.S", or a TAR
            seat city ("Roma", "Milano", "Napoli", ...). Filters server-side.
        tipo: optional - "sentenza", "ordinanza", "decreto", "parere",
            "plenaria" (Adunanza Plenaria). Filters server-side.
        numero: optional decision number (1-5 digits) for an exact lookup.
            Filters server-side; combine with ``anno`` + ``sede`` to pin one
            decision.
        anno: optional 4-digit publication year. Applied CLIENT-SIDE over the
            returned page (the portal's year field is a no-op upstream);
            ``total_found`` stays the upstream, year-unfiltered total.
        limit: max hits (1..60; the portal serves pages of 20/40/60, newest first).

    Returns:
        ``GaSearchResult`` with ``total_found`` (upstream) and hits carrying the
        NATIVE ECLI, citation, snippet and ``document_url``.
    """
    audit = _audit()
    input_hash = hash_input(
        {"q": query, "sede": sede, "tipo": tipo, "numero": numero, "anno": anno, "limit": limit}
    )
    if not 1 <= limit <= 60:
        raise ITError("invalid_arg", f"limit={limit} out of range 1..60.")
    with timer() as t:
        try:
            total, ga_hits = await ga_client.search(
                query, sede=sede, tipo=tipo, numero=numero, anno=anno, limit=limit
            )
        except GaError as exc:
            audit.log(tool="it_ga_search", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms, status="error", error=str(exc))
            raise ITError("ga_error", str(exc)) from exc
    hits = []
    for h in ga_hits:
        row: dict[str, Any] = dict(h.as_row())
        row["source_url"] = h.document_url
        hits.append(GaSearchHit.model_validate(row))
    result = GaSearchResult(
        query=query, total_found=total, total_returned=len(hits), hits=hits
    )
    audit.log(tool="it_ga_search", input_hash=input_hash, output_count_or_size=len(hits),
              duration_ms=t.duration_ms, status="ok")
    return result


@mcp.tool(annotations=READ_ONLY)
async def it_ga_get_decision(document_url: str) -> GaDecisionFull:
    """Fetch the full text of one administrative decision, live, by its document URL.

    Args:
        document_url: the ``document_url`` of an ``it_ga_search`` hit, verbatim
            (an ``https://mdp.giustizia-amministrativa.it/visualizza/?...`` URL).

    Returns:
        ``GaDecisionFull`` with the full decision text (epigrafe through
        dispositivo), the portal's own URN and registry coordinates, and the
        citation contract.
    """
    audit = _audit()
    input_hash = hash_input({"document_url": document_url})
    with timer() as t:
        try:
            doc = await ga_client.get_document(document_url)
        except GaError as exc:
            audit.log(tool="it_ga_get_decision", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms, status="error", error=str(exc))
            raise ITError("ga_error", str(exc)) from exc
    citation = (
        f"{doc.tipologia} n. {doc.numero}/{doc.anno}"
        if doc.tipologia and doc.numero and doc.anno
        else None
    )
    result = GaDecisionFull.model_validate(
        {
            **doc.as_row(),
            "citation": citation,
            "document_url": document_url,
            "source_url": document_url,
        }
    )
    audit.log(tool="it_ga_get_decision", input_hash=input_hash,
              output_count_or_size=len(doc.testo), duration_ms=t.duration_ms, status="ok")
    return result


def main() -> None:
    """Run the MCP server over stdio (default for Claude Code)."""
    mcp.run()


if __name__ == "__main__":
    main()
