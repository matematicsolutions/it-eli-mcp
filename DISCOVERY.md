# Discovery: Normattiva (normattiva.it) - Italy

Date: 2026-07-01. **Status: CLOSED - BUILD.** Every claim below was verified with a live probe on
2026-07-01, not inferred from the eu-legal-mcp coverage matrix (which flagged IT as "no clean REST,
low confidence" - a hypothesis this discovery overturns in practice).

## Why Italy

Italy is the EU's largest legal market by number of lawyers: ~236k (source: MateMatic
legaltech-market-report), ahead of Germany (~166k) and Spain (~150k). No live, keyless MCP
connector covered the Italian statute book. A curated competitor exists (see below) but does not
do what this production line does.

## Base source properties (CONFIRMED live)

- **Portal:** `https://www.normattiva.it` (Ministero della Giustizia / Istituto Poligrafico e
  Zecca dello Stato).
- **API:** none. No REST/JSON. Search is a session-based SPA. `dati.normattiva.it` exposes an
  OpenData layer (bulk ZIP / predefined searches; `/api/` returns 409 to a bare request).
- **Authentication:** none - keyless. Qualifies for drop-in, "as simple as a skill" distribution.
- **Identifiers:** **URN:NIR** (`urn:nir:stato:legge:1990-08-07;241`) and **ELI**
  (`eli/id/1990/08/18/090G0294/CONSOLIDATED`), both embedded in the Akoma Ntoso `FRBRalias`.
- **Format:** Akoma Ntoso 3.0 (LegalDocML) XML per act, with `eli:` namespace and FRBR levels.
- **Point-in-time:** *multivigenza* - the `dataVigenza=YYYYMMDD` parameter yields the text as in
  force on that date. A first-class feature.

## The fetch flow (VERIFIED on D.Lgs. 196/2003 and L. 241/1990)

Normattiva has "no clean REST", but a deterministic, keyless flow exists:

1. `GET /uri-res/N2Ls?urn:nir:...` (URN resolver) or `GET /eli/id/.../CONSOLIDATED` - returns the
   act's HTML page and sets a session cookie.
2. The page contains a link `caricaAKN?dataGU=YYYYMMDD&codiceRedaz=XXXXXXXX&dataVigenza=YYYYMMDD`.
   Extract `dataGU` + `codiceRedaz`.
3. `GET /do/atto/caricaAKN?dataGU=..&codiceRedaz=..&dataVigenza=..` **in the same session** -> the
   Akoma Ntoso XML (verified: `text/xml`, ~1.5 MB for D.Lgs. 196, 221 `<article>`, ELI present).

A **partial URN** (`urn:nir:stato:legge:1990;241`, year + number, no promulgation day) resolves too
- so a lawyer's "L. 241/1990" citation is enough to fetch the act. Verified for four acts.

## Identifiers extracted (VERIFIED on L. 241/1990)

- `FRBRalias name="urn:nir" value="urn:nir:stato:legge:1990-08-07;241"` -> `urn`.
- `FRBRalias name="eli" value="eli/id/1990/08/18/090G0294/CONSOLIDATED/20260421"` -> `eli_uri`.
  **ELI available at the source - Article IV met directly, no compromise.**
- `FRBRdate date="1990-08-07"` -> promulgation date.
- `<article eId="art_1"><num>Art. 1.</num>...` -> article-structured body.

## Codes dictionary (each URN verified to resolve, 2026-07-01)

Costituzione; Codice civile (R.D. 262/1942); Codice penale (R.D. 1398/1930); Codice di procedura
civile (R.D. 1443/1940); Codice di procedura penale (D.P.R. 447/1988); Codice privacy (D.Lgs.
196/2003); CAD (D.Lgs. 82/2005); D.Lgs. 231/2001; L. 241/1990.

## Competition (kardynalna doktryna - step 0)

- `Ansvar-Systems/italian-law-mcp` - an Italian-law MCP, but a **curated SQLite snapshot** of a
  fixed set of topics (privacy, penal, D.Lgs. 231, CAD, NIS2), served over HTTP/Docker on port
  3000. Not a live connector over the whole corpus. **Differentiation:** we are live + keyless +
  stdio drop-in, ELI-grounded over the entire Normattiva statute book, point-in-time capable, with
  an audit trail.
- `ondata/normattiva_2_md` (MIT) - a Python CLI that fetches an act's AKN and converts to Markdown;
  its search leg requires an Exa AI key (not keyless). A useful reference for the session flow; we
  implement our own thin client (httpx + lxml) to keep the dependency surface small and auditable.

## Citation contract (Article IV) - CLOSED for IT

- `eli_uri` = the `eli` FRBRalias (verbatim). ELI at the source.
- `urn` = the `urn:nir` FRBRalias, or the URN built from coordinates.
- `human_readable_citation` = Italian convention from the URN ("Legge 7 agosto 1990, n. 241").
- `source_url` = the stable, human-openable Normattiva ELI page.

## Decision: BUILD

Blocking questions resolved in favour: (1) machine-readable text YES (AKN via session flow);
(2) stable identifiers YES (URN + ELI); (3) keyless YES; (4) licence YES (art. 5 l. 633/1941 +
CC-BY-4.0 overlay). Architecture: a new `client.py` (session + resolver + caricaAKN) and `akn.py`
(lxml Akoma Ntoso parser); the cache / audit / models / server skeleton reused from `de-eli-mcp`.

## Residual risks / watch-items (non-blocking)

1. **No full-text search that is keyless.** MVP ships coordinate/code retrieval; free-text
   discovery search (Exa-backed or SPA reverse-engineering) is a Phase 2 item. Documented, not
   hidden.
2. **Session/cookie fragility.** If Normattiva changes the act-page markup, the `caricaAKN`
   extraction regex needs updating. Covered by the smoke tests (fail loud).
3. **Undocumented rate-limit.** Own backoff + disk cache regardless.
4. **Case law (Corte costituzionale / Cassazione).** Out of MVP scope - separate sub-family.
