# Changelog

All notable changes to `italy-eli-mcp` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses [SemVer](https://semver.org/).

## [0.5.1] - 2026-07-11

### Added
- **Fast-path release asset.** `release.yml` now builds the Corte Costituzionale index in CI,
  gzips it, and attaches `cost.sqlite.gz` + `cost.sqlite.gz.sha256` to each release. The lazy
  download path (step 2 of the provisioning ladder) picks it up automatically, so a fresh
  install fetches a small, sha256-verified pre-built index in seconds instead of building the
  ~100 MB of open data locally. The build path remains the fallback when the asset is absent.

### Changed
- `corpus.ensure_index()` now handles a gzipped asset: the checksum is verified against the
  downloaded `.gz`, which is then stream-decompressed (constant memory) before install. The
  default `IT_ELI_CASELAW_INDEX_URL` points at `…/cost.sqlite.gz`; a plain `.sqlite` URL still
  works (the `.gz` suffix drives decompression).

## [0.5.0] - 2026-07-11

### Changed
- **Constitutional case-law index is now provisioned automatically on first use.** The
  `it_case_search` / `it_case_get_decision` / `it_case_recent` / `it_case_stats` tools no
  longer fail with `index_missing` on a fresh install. On the first call, `ensure_index()`
  resolves the index through a fallback ladder:
  1. env override / existing cache (`IT_ELI_CASELAW_DB` or `~/.matematic/data/it-eli-caselaw/cost.sqlite`);
  2. a pre-built `cost.sqlite` downloaded from the GitHub release asset and **verified against
     its `.sha256` sidecar** (an unverifiable download is refused);
  3. a local build from the Corte Costituzionale official open data (the same work the
     manual `italy-eli-mcp-caselaw-ingest` command does), run automatically;
  4. only if every path fails does the clear `index_missing` error surface, with guidance.
  All subsequent calls query the cached index offline. The manual ingest command still works
  for refreshing. (Pattern mirrors pk-eli-mcp's `ensure_corpus()`.)
- `it_case_stats` now reports `provenance` (`release-asset …` or `local-build …`) alongside
  `ingested_at`, so index freshness is always stated - no silent staleness.
- `INSTRUCTIONS` and the case-law `dataset_note` updated to describe automatic provisioning.

### Added
- Env knobs: `IT_ELI_CASELAW_INDEX_URL` (override / disable the release-asset download),
  `IT_ELI_CASELAW_INDEX_SHA256` (pin the expected checksum instead of the sidecar), and
  `IT_ELI_CASELAW_AUTOBUILD=0` (skip the local build and prefer the `index_missing` error).
- `tests/test_caselaw_corpus.py` - offline coverage of the provisioning ladder, including a
  real sha256-verified download over a localhost HTTP server.

### Fixed
- `__version__` in `it_eli_mcp/__init__.py` was stale (`0.2.2`); it is now synced to the
  package version.

## [0.4.0] - 2026-07-08
- Administrative case law (Consiglio di Stato, C.G.A.R.S., TAR) via the Giustizia
  Amministrativa portal search (live, keyless).
- Corte di Cassazione case law via SentenzeWeb (live, keyless).

## [0.2.2] - 2026-07-01
- Federal legislation via Normattiva (Akoma Ntoso / URN:NIR / ELI, point-in-time text) and
  Corte Costituzionale case law from the Court's official open data (local FTS5 index).
