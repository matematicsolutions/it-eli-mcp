"""Pydantic v2 models for Giustizia Amministrativa tool I/O."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

DATASET_NOTE = (
    "Source: Giustizia Amministrativa (www.giustizia-amministrativa.it), the official "
    "public decision search of the Italian administrative jurisdiction - Consiglio di "
    "Stato (501K+ provvedimenti), C.G.A.R.S. (53K+) and the 29 regional TAR seats "
    "(3.4M+ portal-wide), queried live, keyless, on every call. Search hits carry the "
    "court's NATIVE ECLI; full texts are the portal's own GA XML. Italian official "
    "legal texts are outside copyright (art. 5, l. 633/1941). This connector relays "
    "individual decisions on request; it does not bulk-harvest. The portal's year "
    "filter is applied client-side (see tool docs); total_found is the upstream, "
    "year-unfiltered total."
)


class _Tolerant(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class GaSearchHit(_Tolerant):
    ecli: str | None = None
    citation: str | None = None
    tipo: str | None = None
    sede: str | None = None
    sezione: str | None = None
    anno: str | None = None
    numero: str | None = None
    numero_provvedimento: str | None = None
    numero_ricorso: str | None = None
    document_url: str | None = None
    document_format: str | None = None
    source_url: str | None = None
    snippet: str | None = None


class GaSearchResult(_Tolerant):
    query: str | None = None
    total_found: int
    total_returned: int
    hits: list[GaSearchHit] = Field(default_factory=list)
    dataset_note: str = DATASET_NOTE


class GaDecisionFull(_Tolerant):
    citation: str | None = None
    ecli: str | None = None
    tipologia: str | None = None
    urn: str | None = None
    anno: str | None = None
    numero: str | None = None
    nrg_anno: str | None = None
    nrg_numero: str | None = None
    data_pubblicazione: str | None = None
    testo: str | None = None
    document_url: str | None = None
    source_url: str | None = None
    dataset_note: str = DATASET_NOTE
