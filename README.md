# it-eli-mcp

<!-- mcp-name: io.github.matematicsolutions/it-eli-mcp -->

An MCP server for **Italian law**, in two layers:

- **Legislation** via [Normattiva](https://www.normattiva.it), the official portal of the
  Ministero della Giustizia. It fetches acts as **Akoma Ntoso** with verifiable **URN:NIR** and
  **ELI** identifiers, and returns the text as it stood on any past date (*multivigenza*). Live and
  keyless.
- **Constitutional case law** (Corte Costituzionale): a local, keyless full-text index of every
  decision since 1956, each with its native **ECLI**, built from the Court's official open data.
- **Supreme Court case law** (Corte di Cassazione): live, keyless full-text search over SentenzeWeb,
  the Court's own free public search engine - civil and criminal decisions, full OCR text, no local
  index to build.
- **Administrative case law** (Consiglio di Stato, C.G.A.R.S., TAR): live, keyless search over the
  Giustizia Amministrativa portal's own public decision search - one backend for the whole
  administrative jurisdiction, 3.4M+ provvedimenti with native ECLI and structured full text.

Italy has the EU's largest legal profession by headcount - roughly 240,000 lawyers per CCBE
figures, ahead of Germany and Spain. No live, keyless MCP connector covered its statute book. This
one does, and it also covers the constitutional case law.

Part of the MateMatic `eu-legal-mcp` production line: the Italian sibling of `de-eli-mcp` (Germany)
and `sejm-eli-mcp` (Poland), built on the same architecture and citation contract against the
Italian source.

> **No JSON API.** Normattiva does not publish a REST API. This connector drives the same
> session-based flow a browser uses - resolve a URN, read the act page, fetch its Akoma Ntoso
> export - so every act comes back as structured XML with its ELI intact. See `DISCOVERY.md`.
>
> **Licence.** Italian official legal texts are outside copyright (art. 5, l. 633/1941), and
> Normattiva declares CC-BY-4.0 for its data from 2026-01-01. This connector relays individual
> acts on request, with attribution and a `source_url`; it does not bulk-harvest the database
> (Normattiva's terms restrict that). Every response carries a `dataset_note`. (A practitioner's
> read, not formal legal advice.)
>
> **Cassazione is NOT Italgiure/ItalgiureWeb.** The Court's full-database search
> (ItalgiureWeb, 35M+ documents) is free only for the judiciary; practitioners pay a
> subscription. This connector does **not** use that service. It queries **SentenzeWeb**
> (`italgiure.giustizia.it/sncass`), a **separate, free, public** search engine the Court
> itself publishes, under the **Italian Open Data License (IODL 2.0)**, with no authentication
> - verified live during development (see `DISCOVERY.md`). Coverage is narrower than the full
> Italgiure database but real: 420K+ civil and criminal decisions with full OCR text.

## Legislation tools (Normattiva, live)

| Tool | What it does |
|---|---|
| `it_list_codes` | The major Italian codes and consolidated acts (Codice civile, penale, di procedura, privacy/GDPR, CAD, D.Lgs. 231/2001, Costituzione, L. 241/1990) with their canonical URN. |
| `it_resolve` | Turns act coordinates (`act_type`, `year`, `number`) into a canonical, resolvable URN:NIR. Offline. |
| `it_get_act` | Fetches act metadata (title, date, ELI, article count) for a code name, URN, ELI path, or normattiva.it URL. |
| `it_get_text` | Fetches the text of a whole act or a single `article` - with `at_date` for the point-in-time version. |

## Constitutional case-law tools (Corte Costituzionale, local index)

| Tool | What it does |
|---|---|
| `it_case_search` | Full-text search over the decisions (heading, reasoning, operative part). Filters by year and type (sentenza/ordinanza). Accent-insensitive. |
| `it_case_get_decision` | The full text of one decision, by ECLI (`ECLI:IT:COST:2024:1`) or by year + number. |
| `it_case_recent` | The most recent decisions (newest first). |
| `it_case_stats` | Index coverage: total decisions, year range, counts by type, last build time. |

The case-law tools read a local SQLite index that is **provisioned automatically on the first
call** - no setup step. On first use the server downloads a pre-built `cost.sqlite` (sha256-verified)
from the release, or, if none is published, builds it from the Court's open data (all decisions
since 1956); the index is then cached under `~/.matematic` and every later call queries it offline.
`it_case_stats` reports `provenance` and `ingested_at` so you can see how fresh it is.

To refresh, or to pre-build it ahead of time (e.g. in an offline deployment), run:

```bash
italy-eli-mcp-caselaw-ingest
```

Tuning env vars: `IT_ELI_CASELAW_INDEX_URL` (override/disable the pre-built download),
`IT_ELI_CASELAW_INDEX_SHA256` (pin the checksum), `IT_ELI_CASELAW_AUTOBUILD=0` (skip the
automatic local build). The legislation tools need no index; they fetch live.

## Supreme Court case-law tools (Corte di Cassazione, SentenzeWeb, live)

| Tool | What it does |
|---|---|
| `it_cassazione_search` | Full-text search over decision bodies. Filters: `chamber` ('civile'/'penale'), `sub_chamber` ('lavoro'/'tributaria'), `anno` (year). Returns ranked hits with a highlighted snippet. |
| `it_cassazione_get` | The full text of one decision by its SentenzeWeb `sic_id` (from a search hit). |

No ingest step - every call queries SentenzeWeb live. Coverage: civil (`snciv`, ~190K) and
criminal (`snpen`, ~238K) decisions, including the Labour (`szdec:L`, ~30K) and Tax (`szdec:5`,
~59K) sub-chambers, full OCR text.

Scope is Corte di Cassazione only. Consiglio di Stato and the TAR (administrative courts) were
evaluated and NOT implemented: their open-data portal (Open GA,
`openga.giustizia-amministrativa.it`, CKAN) publishes only docket metadata (case numbers, parties,
outcome codes) in bulk CSV/JSON - not full decision text as structured, bulk-fetchable data. Full
texts do exist on `portali.giustizia-amministrativa.it` but behind a per-decision URL pattern
(`nomeFile=<fascicolo>_<doctype-code>.html`) whose doctype-code segment is not derivable from the
docket metadata alone, so a reliable search+get tool isn't buildable from open data today.

Every legislation response carries the citation contract: `eli_uri` (e.g.
`eli/id/1990/08/18/090G0294/CONSOLIDATED`), `urn` (e.g. `urn:nir:stato:legge:1990-08-07;241`),
`human_readable_citation` (e.g. `Legge 7 agosto 1990, n. 241`), and `source_url`.

## How it identifies an act

- **URN:NIR** - `urn:nir:{authority}:{type}:{date};{number}`. A partial URN with the year alone
  (`urn:nir:stato:legge:1990;241`) also resolves, so you can cite an act you only know as
  "L. 241/1990".
- **ELI** - `eli/id/{year}/{month}/{day}/{code}/CONSOLIDATED`, read from the act itself. Never
  invented.

## Examples

```
it_list_codes()
→ [{key: "codice civile", urn: "urn:nir:stato:regio.decreto:1942-03-16;262", ...}, ...]

it_resolve(act_type="d.lgs", year=2001, number=231)
→ {urn: "urn:nir:stato:decreto.legislativo:2001;231",
   human_readable_citation: "Decreto legislativo n. 231/2001", source_url: "..."}

it_get_text(reference="codice civile", article="2043")
→ art. 2043 c.c. (Risarcimento per fatto illecito), with eli_uri + source_url

it_get_text(reference="codice privacy", article="1", at_date="2010-01-01")
→ the privacy code's art. 1 as it stood on 1 January 2010

it_cassazione_search(query="responsabilita medica", chamber="civile", limit=5)
→ {total_found: 81177, hits: [{sic_id: "snciv2025224393O",
   citation: "Cass. civ., ord. n. 24393/2025", snippet: "...", source_url: "..."}, ...]}

it_cassazione_get(sic_id="snciv2025224393O")
→ {citation: "Cass. civ., ord. n. 24393/2025", testo: "...", massima: "...", source_url: "..."}
```

## Install

```bash
cd it-eli-mcp
pip install -e .
```

## Configure (Claude Code / any MCP client)

Copy `.mcp.json.example`:

```json
{
  "mcpServers": {
    "it-eli-mcp": { "command": "italy-eli-mcp" }
  }
}
```

Environment:

- `IT_ELI_BASE_URL` - default `https://www.normattiva.it`
- `IT_ELI_CACHE_DIR` - default `~/.matematic/cache/it-eli`
- `IT_ELI_AUDIT_DIR` - default `~/.matematic/audit`
- `IT_ELI_CASELAW_DB` - constitutional case-law index path (default `~/.matematic/data/it-eli-caselaw/cost.sqlite`)
- `IT_ELI_CASELAW_INDEX_URL` - pre-built index download URL (default: the GitHub release asset; `''` disables)
- `IT_ELI_CASELAW_INDEX_SHA256` - pin the expected index checksum instead of fetching the `.sha256` sidecar
- `IT_ELI_CASELAW_AUTOBUILD` - `0` to skip the automatic local build (prefer the `index_missing` error)

## Tests

```bash
pip install -e ".[dev]"
pytest -m "not smoke"   # offline (URN, Akoma Ntoso parser, case-law index, drift)
pytest -m smoke         # live: Normattiva + Corte Costituzionale open data + SentenzeWeb
```

## Audit trail

Every tool call appends one JSON line to `~/.matematic/audit/it-eli-mcp.jsonl` (timestamp, tool,
input hash, output size, duration, status) for AI Act art. 12 record-keeping. No raw query text is
stored.

## Licence

Apache-2.0. See `LICENSE`.
