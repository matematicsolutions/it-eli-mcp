# it-eli-mcp - Claude plugin

Italian law with verifiable citations, as a Claude plugin. It runs the
[it-eli-mcp](https://github.com/matematicsolutions/it-eli-mcp) MCP server, version 0.7.3
from PyPI (PyPI package `italy-eli-mcp`). `server/uv.lock` pins that package and every dependency with hashes, and the
plugin starts it with `uv run --frozen`, so it runs exactly what was reviewed. Every
answer carries the official source, so a citation can be checked instead of trusted.

What it covers: legislation from Normattiva (resolve a reference, act metadata and point-in-time text of an act or article), Constitutional Court decisions from a local full-text index of the Court's official open data, Court of Cassation decisions via SentenzeWeb (italgiure.giustizia.it), administrative decisions via the Giustizia Amministrativa portal, and a tool that checks the Italian citations in a text. The full tool list is in the
[main README](https://github.com/matematicsolutions/it-eli-mcp#readme).

## Requirements

Claude Code or the Claude desktop app, and [uv](https://docs.astral.sh/uv/) on your
machine (it installs the locked packages on first start and runs the server).

## Install

```
/plugin marketplace add matematicsolutions/it-eli-mcp
/plugin install it-eli-mcp@it-eli-mcp
```

## Data

The server runs on your machine. Each tool call sends your query to the official Italian source it names (normattiva.it, italgiure.giustizia.it for the Court of Cassation, or giustizia-amministrativa.it); Constitutional Court searches run on a local index
and to nothing else; nothing goes to MateMatic. Your query and the results also pass
through whatever model you use, the same way as any other message.

On the first Constitutional Court call the server downloads that local index once: a pre-built, compressed SQLite file (about 200 MB) of the Court's official open data, attached to this repository's GitHub release v0.7.3. The plugin pins that exact file and its SHA-256 in `plugin.json` (`IT_ELI_CASELAW_INDEX_URL`, `IT_ELI_CASELAW_INDEX_SHA256`), and the server refuses a file whose checksum does not match. If the download is not possible, it builds the index itself from the Court's open data at dati.cortecostituzionale.it. The request carries no query content.

Three things are written locally, in your home directory:

- a response cache (`~/.matematic/cache/it-eli`), so a repeated lookup does not hit
  the source again. Court decisions are public records and can name the parties.
- an audit log (`~/.matematic/audit/it-eli-mcp.jsonl`), one line per tool call: the
  tool name, a SHA-256 hash of the input (not the input itself), result size, time
  and status.
- the Constitutional Court index (`~/.matematic/data/it-eli-caselaw/cost.sqlite`), built once as described above; `IT_ELI_CASELAW_DB` moves it.

Delete either folder at any time; `IT_ELI_CACHE_DIR` and `IT_ELI_AUDIT_DIR` move them.

## Licence

Apache-2.0, see the repository's [LICENSE](https://github.com/matematicsolutions/it-eli-mcp/blob/main/LICENSE).
