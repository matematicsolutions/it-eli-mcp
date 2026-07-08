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
4. **Case law (Corte costituzionale / Cassazione).** Added in v0.2.0 for the Constitutional
   Court (see below); Cassazione stays out (subscription-gated).

## Feature 002 - Constitutional case law (v0.2.0, 2026-07-01)

Court-by-court probe (live):

- **Corte Costituzionale = BUILT.** Official open data at `dati.cortecostituzionale.it` (the `dati.`
  subdomain; the `www.` front sits behind a ShieldSquare/Radware bot manager, not used). Bulk
  downloads under `/opendata/distribuzione/` as zip-of-zips (outer archive of per-year archives,
  each one JSON file): three eras of decisions (1956-1980 / 1981-2000 / 2001-today), XML + CSV +
  JSON. Files are cp1252/latin-1 with HTML entities. Each decision carries a native `ecli`
  (`ECLI:IT:COST:YYYY:N`), full reasoning (`testo`), operative part (`dispositivo`), heading
  (`epigrafe`) and metadata. Verified on `ECLI:IT:COST:1956:1`.
- **Corte di Cassazione = revisited 2026-07-07, now BUILT.** The original note above conflated two
  different services. **ItalgiureWeb** (the Court's full-database search, 35M+ documents across all
  document types) is indeed subscription-gated - free only to the judiciary, paid for
  practitioners; that stays OUT. But the Court separately runs **SentenzeWeb**
  (`https://www.italgiure.giustizia.it/sncass/`), its own free, public, keyless search engine over
  case law specifically - a genuinely different, narrower, but real open channel. See "SentenzeWeb
  verification" below for the live probe that established this. `it_cassazione_search` /
  `it_cassazione_get` ship against SentenzeWeb, not ItalgiureWeb.
- **Giustizia Amministrativa (Consiglio di Stato) = investigated 2026-07-07, NOT built.** See
  "Consiglio di Stato / Open GA" below - the open-data portal ships docket metadata, not full text,
  as bulk machine-readable data.

Architecture: a **local SQLite FTS5 index** (the `mcp-eu-compliance` pattern), built once by
`it-eli-mcp-caselaw-ingest` and read offline by the `it_case_*` tools. This differs from the live
legislation tools by design, because the case law is a bulk open-data corpus, not a live API.

## SentenzeWeb verification (Corte di Cassazione) - 2026-07-07

Triggered by an external catalog (Legal Data Hunter, worldwidelaw/legal-sources manifest.yaml)
listing `IT/CassazioneCivile` as `status: complete`, `auth: none`, pointing at
`https://www.cortedicassazione.it` with the note "via SentenzeWeb Solr API. 423K+ decisions". This
contradicted our earlier "Cassazione = OUT (Italgiure subscription)" note, so it was verified from
scratch rather than taken on faith or dismissed.

- The Court's homepage (`cortedicassazione.it`) links a free service "SentenzeWeb - Il motore di
  ricerca per navigare tra le sentenze emesse dalla Corte", hosted at
  `https://www.italgiure.giustizia.it/sncass/` (same domain as ItalgiureWeb, different path/app).
- `GET https://www.italgiure.giustizia.it/sncass/` -> HTTP 200, a search form with no login wall,
  `startquery` hidden field `(kind:"snciv" OR kind:"snpen")`.
- The page's `index.js` (Z search-UI framework) declares the query backend:
  `solr:"/sn.solr/sn-collection"`, `solrIsapi:"isapi/hc.dll/sn.solr/sn-collection"`.
- Live query, no auth, no cookies:
  `GET https://www.italgiure.giustizia.it/sncass/isapi/hc.dll/sn.solr/sn-collection/select?q=kind:snciv&rows=1&wt=json`
  -> HTTP 200, JSON, `numFound: 190630`, full OCR text in field `ocr` for a real ordinanza (IRPEF
  case, 2021). `kind:snpen` -> `numFound: 237772`. `kind:snciv AND szdec:L` (Labour) ->
  `numFound: 30517`. `kind:snciv AND szdec:5` (Tax) -> `numFound: 59369`. Totals are close to LDH's
  186K/238K claim (dataset grows) - independently corroborated.
- Phrase search works via `q=ocr:"exact phrase"` (bare multi-word terms without quotes get parsed
  as noisy OR of individual tokens against the default field - quote them). Solr highlighting
  (`hl=true&hl.fl=ocr&hl.snippets=1`) returns usable snippets.
- **Fields returned per document:** `id`, `kind`, `numdec`, `anno`, `tipoprov`, `szdec`, `ssz`,
  `materia`, `presidente`, `relatore`, `datdec`, `datdep`/`pd`, `ocr` (full text), `ocrdis`
  (massima/summary), `sicId`, `filename`. No ECLI field - Cassazione does not mint ECLIs for these
  records the way Corte Costituzionale does, so the citation contract for this connector builds an
  Italian-convention `citation` string from `kind`+`tipoprov`+`numdec`+`anno`(+`szdec`/`ssz` for
  section) instead, and treats a re-runnable SentenzeWeb query as the grounding `source_url`.
- **License:** IODL 2.0 (Italian Open Data License), per LDH's manifest entry - consistent with the
  page carrying no paywall, login, or ToS gate for read access.

### A real TLS gotcha found and fixed

`httpx` (and any strict OpenSSL-based client) fails against
`www.italgiure.giustizia.it` with `CERTIFICATE_VERIFY_FAILED: unable to get local issuer
certificate`, even though `curl` on Windows succeeds. `openssl s_client -showcerts` shows why: the
server serves the WRONG intermediate certificate - a "TI Trust Technologies **DV** CA" (cross-signed
by USERTrust), when the leaf's issuer is actually "TI Trust Technologies **OV** CA". This is a
genuine server misconfiguration, not a self-signed/untrusted endpoint: the correct OV intermediate
is fetchable from its own AIA URL
(`http://tiTrust.crt.sectigo.com/TITrustTechnologiesOVCA.crt`) and chains to a root already in
Mozilla's/certifi's trust store (USERTrust RSA Certification Authority) - verified with
`openssl verify -CAfile certifi.where() -untrusted <ov_ca.pem> <leaf.pem>` -> `OK`. Windows/Schannel
(and therefore `curl.exe` on Windows) silently works around this via automatic AIA chasing; Python's
`ssl`/OpenSSL does not do this by default. Fix shipped in
`src/it_eli_mcp/cassazione/client.py`: bundle the correct intermediate
(`src/it_eli_mcp/cassazione/certs/ti_trust_ov_ca.pem`) and build an `ssl.SSLContext` from
`certifi.where()` + that extra cert, passed as `verify=` to the `httpx.AsyncClient`. Confirmed fixed
by the live smoke tests (`tests/test_cassazione_smoke.py`).

## Consiglio di Stato / Open GA - investigated, NOT built (2026-07-07)

The LDH manifest also lists `IT/ConsiglioDiStato` (`status: complete`, `auth: none`, CC BY 4.0,
`url: https://www.giustizia-amministrativa.it`). Verification:

- `giustizia-amministrativa.it` links `openga.giustizia-amministrativa.it` ("Open GA"), a CKAN portal
  launched in 2024 (PNRR-funded). `GET /api/3/action/package_list` -> HTTP 200, dozens of datasets
  per court (Consiglio di Stato `cds-*`, each TAR, CGA Sicilia), including `cds-sentenze`.
- `GET /api/3/action/package_show?id=cds-sentenze` -> CSV/JSON/ODS resources per year (2023-2026),
  no auth, no license declared on the package itself (site-wide CC BY 4.0 per LDH).
- **The catch:** the `cds-sentenze` JSON is **docket metadata only** - fields like
  `TIPO_PROVVEDIMENTO`, `NUMERO_PROVVEDIMENTO`, `NUMERO_RICORSO`, `DATA_PUBBLICAZIONE`,
  `ESITO_PROVVEDIMENTO`, `OGGETTO_RICORSO` (a short subject line) - no decision body/reasoning text.
  This is the same shape LDH itself would have harvested; it does not contradict LDH's
  `status: complete` (the docket data genuinely is open and complete), but it means "case law" here
  is docket-level, not full-text.
- Full decision text DOES exist and IS reachable without auth, at
  `https://portali.giustizia-amministrativa.it/portale/pages/istituzionale/visualizza/?schema=cds&nrg=<anno><numero_ricorso>&nomeFile=<anno_fascicolo><numero_fascicolo>_<doctype>.html&subDir=Provvedimenti`
  -> full-text XML (~30KB), parties, panel, signatures, `urn:nir:consiglio.di.stato;sezione.N:...`.
  Verified against 3 sample links scraped from the homepage.
- **Why it's not buildable today:** `nrg` derives cleanly from the docket's `registro` (anno+n), but
  the `nomeFile` fascicolo-anno+n part needs a `<doctype>` suffix (observed `_11` for "Sentenza",
  `_23` for "Sentenza breve") that is NOT present in the `cds-sentenze` bulk dataset and isn't a
  fixed constant - it would require either brute-forcing a small enum of suffixes per record (fragile,
  N calls per decision, no guarantee of completeness) or scraping a separate search-results page to
  recover the real filename (out of scope for a "free bulk metadata + direct fetch" architecture).
- **Verdict:** real, free, keyless, but the full-text channel is not machine-readable-by-design for
  bulk/reliable use the way Cassazione's SentenzeWeb Solr index is. Parking rather than shipping a
  half-working tool. Revisit if Open GA ever adds the doctype code to its bulk export, or if TAR
  decisions (same portal family) turn out to have a more deterministic URL pattern.
Licence: official open data for reuse - confirm the exact terms before redistribution.

## Consiglio di Stato / Giustizia Amministrativa - REJECTION REVERSED, built (2026-07-08)

The 2026-07-07 parking verdict above assumed the only entry points were the Open GA bulk export
(metadata-only) and a hand-derived `nomeFile` URL. Re-check (feature-004 widen round, STALE-REJ
policy) found the missing piece: the portal's OWN public decision search supplies the full
`nomeFile=..._NN.html` segment for every hit, so a reliable search -> full-text path exists
without guessing doctype suffixes. Transcript of the live verification (2026-07-08, re-probed at
ship time the same day):

- Search backend: Liferay portlet at `https://www.giustizia-amministrativa.it/web/guest/dcsnprr`.
  Plain HTTP, keyless: `GET` the page -> session cookie + `p_auth` CSRF token embedded in the HTML;
  `POST` the same URL with `p_p_id=decisioni_pareri_web_DecisioniPareriWebPortlet_INSTANCE_XKc17mrB8J10`,
  `javax.portlet.action=search` and the form fields -> server-rendered HTML, one
  `<article class="ricerca--item">` per hit with the mdp full-text URL, a NATIVE ECLI
  (e.g. `ECLI:IT:CDS:2026:5268SENT`), sede/sezione/numero metadata and a snippet.
- Corpus totals from the portal's own `Trovati <strong>N</strong> risultati` field (empty search):
  3 419 429 provvedimenti portal-wide; sede-filtered: Consiglio di Stato 501 034, C.G.A.R.S. 53 215;
  plus all 29 TAR seats. One backend = the whole administrative jurisdiction.
- Filter honesty (verified by comparing totals, after a day that caught three silent filter no-ops
  in other APIs): query `espropriazione` -> 28 412 all seats, 5 667 CdS, 886 TAR Milano,
  404 CdS+`tipo=ordinanza` - `sede`, `tipo` and `numero` genuinely narrow server-side.
  The portal's year field and pagination ARE silent no-ops on this action URL: `anno` is therefore
  applied client-side (deterministic - the decision id is `YYYYNNNNN`, year first) and only the
  first page (newest first, pageSize 20/40/60) is served.
- Full text: the hit's mdp URL, e.g.
  `https://mdp.giustizia-amministrativa.it/visualizza/?nodeRef=&schema=cds&nrg=202500402&nomeFile=202605268_11.html&subDir=Provvedimenti`
  -> structured GA XML (`<GA><Provvedimento>` with `meta/descrittori` registry coordinates and the
  body in epigrafe..dispositivo sections; sample fetch: Sentenza 05268/2026, published 2026-07-01,
  21 620 chars extracted). A few provvedimenti are PDF-only (`nomeFile=..._NN.pdf`); those are
  flagged `document_format: pdf` and their text is not extracted.
- Licence: Italian official legal texts are outside copyright (art. 5, l. 633/1941); no TDM
  reservation found on the portal. The connector relays individual decisions live on request, it
  does not bulk-harvest.

Shipped as `src/it_eli_mcp/giustizia_amministrativa/` with tools `it_ga_search` /
`it_ga_get_decision` (v0.4.0).
