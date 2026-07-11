"""Pydantic v2 models for it-cost-mcp tool I/O."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

DATASET_NOTE = (
    "Source: Corte Costituzionale official open data (dati.cortecostituzionale.it) - "
    "every decision since 1956, ECLI-native, public for reuse. This is a LOCAL index, "
    "provisioned automatically on first use (a sha256-verified pre-built index or a build "
    "from the open data) and cached under ~/.matematic; see 'provenance'/'ingested_at' in "
    "it_case_stats for freshness, and run 'italy-eli-mcp-caselaw-ingest' to refresh. Scope: "
    "the Italian Constitutional Court only - not the Corte di Cassazione or administrative courts."
)


class _Tolerant(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class SearchHit(_Tolerant):
    ecli: str
    citation: str | None = None
    anno: str | None = None
    numero: str | None = None
    tipologia_label: str | None = None
    data_deposito: str | None = None
    source_url: str | None = None
    snippet: str | None = None


class SearchResult(_Tolerant):
    query: str
    total_returned: int
    hits: list[SearchHit] = Field(default_factory=list)
    dataset_note: str = DATASET_NOTE


class DecisionFull(_Tolerant):
    ecli: str
    citation: str | None = None
    anno: str | None = None
    numero: str | None = None
    tipologia_label: str | None = None
    data_decisione: str | None = None
    data_deposito: str | None = None
    presidente: str | None = None
    relatore: str | None = None
    collegio: str | None = None
    epigrafe: str | None = None
    testo: str | None = None
    dispositivo: str | None = None
    source_url: str | None = None
    dataset_note: str = DATASET_NOTE


class RecentItem(_Tolerant):
    ecli: str
    citation: str | None = None
    anno: str | None = None
    numero: str | None = None
    tipologia_label: str | None = None
    data_deposito: str | None = None
    source_url: str | None = None


class Stats(_Tolerant):
    total: int
    year_min: int | None = None
    year_max: int | None = None
    by_tipologia: dict[str, int] = Field(default_factory=dict)
    ingested_at: str | None = None
    provenance: str | None = None
    dataset_note: str = DATASET_NOTE
