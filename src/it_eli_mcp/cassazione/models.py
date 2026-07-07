"""Pydantic v2 models for Cassazione tool I/O."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

DATASET_NOTE = (
    "Source: Corte Suprema di Cassazione, SentenzeWeb (live public Solr search, "
    "italgiure.giustizia.it/sncass) - full OCR text, 420K+ decisions (civil + criminal, "
    "including the Labour and Tax sub-chambers). Italian Open Data License (IODL 2.0), "
    "no authentication. This is NOT the subscription-gated ItalgiureWeb full-database "
    "search used by the judiciary; it is the Court's own free public search engine, "
    "queried live on every call (no local index to build or refresh)."
)


class _Tolerant(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class CassSearchHit(_Tolerant):
    sic_id: str | None = None
    citation: str | None = None
    kind: str | None = None
    anno: str | None = None
    numdec: str | None = None
    tipoprov: str | None = None
    materia: str | None = None
    data_decisione: str | None = None
    data_deposito: str | None = None
    source_url: str | None = None
    snippet: str | None = None


class CassSearchResult(_Tolerant):
    query: str
    total_found: int
    total_returned: int
    hits: list[CassSearchHit] = Field(default_factory=list)
    dataset_note: str = DATASET_NOTE


class CassDecisionFull(_Tolerant):
    sic_id: str | None = None
    citation: str | None = None
    kind: str | None = None
    anno: str | None = None
    numdec: str | None = None
    tipoprov: str | None = None
    materia: str | None = None
    presidente: str | None = None
    relatore: str | None = None
    data_decisione: str | None = None
    data_deposito: str | None = None
    testo: str | None = None
    massima: str | None = None
    source_url: str | None = None
    dataset_note: str = DATASET_NOTE
