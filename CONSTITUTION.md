# Constitution - it-eli-mcp

The non-negotiable rules for this connector. Same charter as the eu-legal-mcp production line,
specialized to the Italian source.

## Article I - One source, official only

The only data source is Normattiva (`normattiva.it`), the official portal of the Ministero della
Giustizia. No third-party mirrors, no scraped aggregators, no model-generated legal text.

## Article II - Fail loud, never guess

If an act cannot be resolved, if the Akoma Ntoso export is missing, or if the audit write fails,
the tool returns a structured error. It never invents an ELI, a URN, an article number, a date, or
statutory text. Coverage gaps are stated, not papered over.

## Article III - Verbatim text

Statutory text is returned exactly as Normattiva serves it, only whitespace-normalized. No
summarizing, no paraphrasing, no reordering inside the connector.

## Article IV - Citation contract

Every act-bearing response carries `eli_uri`, `urn`, `human_readable_citation`, and `source_url`.
The ELI and URN are read from the act (`FRBRalias`), never synthesized when the source provides
them. This is what makes an answer checkable.

## Article V - Point-in-time honesty

Without `at_date`, text is the consolidated version in force today. With `at_date`, it is the
*multivigenza* version as it stood on that date. The response always says which.

## Article VI - Audit trail

Every tool call appends one JSONL line (timestamp, tool, input hash, output size, duration, status)
for AI Act art. 12 record-keeping. No raw query text is stored.

## Article VII - Licence discipline

Italian official texts are public (art. 5, l. 633/1941) and Normattiva declares CC-BY-4.0. The
connector relays individual acts on request with attribution; it does not bulk-harvest the
database. The boundary is honoured in code (single-act retrieval) and surfaced in `dataset_note`.
