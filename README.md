# it-eli-mcp

An MCP server for **Italian federal legislation** via [Normattiva](https://www.normattiva.it),
the official portal of the Ministero della Giustizia. It fetches acts as **Akoma Ntoso** with
verifiable **URN:NIR** and **ELI** identifiers, and returns the text as it stood on any past date
(*multivigenza*).

Italy has the EU's largest legal profession by headcount - roughly 240,000 lawyers per CCBE
figures, ahead of Germany and Spain. No live, keyless MCP connector covered its statute book. This
one does.

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

## The four tools

| Tool | What it does |
|---|---|
| `it_list_codes` | The major Italian codes and consolidated acts (Codice civile, penale, di procedura, privacy/GDPR, CAD, D.Lgs. 231/2001, Costituzione, L. 241/1990) with their canonical URN. |
| `it_resolve` | Turns act coordinates (`act_type`, `year`, `number`) into a canonical, resolvable URN:NIR. Offline. |
| `it_get_act` | Fetches act metadata (title, date, ELI, article count) for a code name, URN, ELI path, or normattiva.it URL. |
| `it_get_text` | Fetches the text of a whole act or a single `article` - with `at_date` for the point-in-time version. |

Every response carries the citation contract: `eli_uri` (e.g.
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
    "it-eli-mcp": { "command": "it-eli-mcp" }
  }
}
```

Environment:

- `IT_ELI_BASE_URL` - default `https://www.normattiva.it`
- `IT_ELI_CACHE_DIR` - default `~/.matematic/cache/it-eli`
- `IT_ELI_AUDIT_DIR` - default `~/.matematic/audit`

## Tests

```bash
pip install -e ".[dev]"
pytest -m "not smoke"   # offline unit tests (URN, Akoma Ntoso parser, drift)
pytest -m smoke         # live tests against Normattiva
```

## Audit trail

Every tool call appends one JSON line to `~/.matematic/audit/it-eli-mcp.jsonl` (timestamp, tool,
input hash, output size, duration, status) for AI Act art. 12 record-keeping. No raw query text is
stored.

## Licence

Apache-2.0. See `LICENSE`.
