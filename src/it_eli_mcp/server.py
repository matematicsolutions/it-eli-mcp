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

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .akn import find_article, parse_akn
from .audit import AuditLogger, hash_input, timer
from .caselaw import db as cdb
from .caselaw.citations import build_ecli as cc_build_ecli
from .caselaw.citations import parse_ecli as cc_parse_ecli
from .caselaw.models import DecisionFull as CaseDecisionFull
from .caselaw.models import RecentItem as CaseRecentItem
from .caselaw.models import SearchHit as CaseSearchHit
from .caselaw.models import SearchResult as CaseSearchResult
from .caselaw.models import Stats as CaseStats
from .citations import build_contract, iso_to_vigenza
from .client import NormattivaClient, NotAvailableError
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

The case-law index must be built once with the `it-eli-mcp-caselaw-ingest` command. If these tools report `index_missing`, tell the user to run it. The legislation tools above need no such step - they fetch live.

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
- `index_missing` - the constitutional case-law index has not been built. Run `it-eli-mcp-caselaw-ingest`.
- `query_error` - a case-law search query could not be parsed (e.g. empty after sanitization).

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


def _open_caselaw() -> sqlite3.Connection:
    try:
        return cdb.connect(must_exist=True)
    except cdb.DatabaseMissingError as exc:
        raise ITError("index_missing", str(exc)) from exc


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
        conn = _open_caselaw()
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
        conn = _open_caselaw()
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
        conn = _open_caselaw()
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
        conn = _open_caselaw()
        try:
            s = cdb.stats(conn)
            ingested_at = cdb.get_meta(conn, "ingested_at")
        finally:
            conn.close()
    result = CaseStats(
        total=s["total"],
        year_min=s["year_min"],
        year_max=s["year_max"],
        by_tipologia=s["by_tipologia"],
        ingested_at=ingested_at,
    )
    audit.log(tool="it_case_stats", input_hash=hash_input({}), output_count_or_size=s["total"],
              duration_ms=t.duration_ms, status="ok")
    return result


def main() -> None:
    """Run the MCP server over stdio (default for Claude Code)."""
    mcp.run()


if __name__ == "__main__":
    main()
