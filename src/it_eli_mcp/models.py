"""Pydantic v2 models for it-eli-mcp tool I/O.

Models are tolerant (``extra="allow"``). The citation contract fields
(``eli_uri`` / ``urn`` / ``human_readable_citation`` / ``source_url``) are the
ones downstream tools depend on.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TextFormat = Literal["text", "akn_xml"]

DATASET_NOTE = (
    "Source: Normattiva (Ministero della Giustizia / Istituto Poligrafico e Zecca dello "
    "Stato). Italian official legal texts are outside copyright (art. 5 l. 633/1941); "
    "Normattiva additionally declares CC-BY-4.0 for its data (from 2026-01-01). Text is "
    "the consolidated (multivigenza) version as in force today unless 'at_date' is given. "
    "Bulk reuse of the database is restricted by Normattiva's terms - this connector "
    "relays individual acts on request, with attribution and a source_url."
)


class _Tolerant(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class CodeEntry(_Tolerant):
    """An entry in the curated codes dictionary."""

    key: str
    urn: str
    label: str


class ResolveResult(_Tolerant):
    """Result of ``it_resolve`` - a constructed, resolvable identifier."""

    urn: str
    human_readable_citation: str | None = None
    source_url: str
    note: str = (
        "URN built from coordinates and resolvable on normattiva.it. Call it_get_act "
        "for the ELI and metadata, or it_get_text for the text."
    )


class ActInfo(_Tolerant):
    """Act metadata - result of ``it_get_act``."""

    eli_uri: str | None = None
    urn: str | None = None
    human_readable_citation: str | None = None
    title: str | None = None
    doc_date: str | None = None
    article_count: int = 0
    source_url: str
    dataset_note: str = DATASET_NOTE


class ActText(_Tolerant):
    """Result of ``it_get_text`` - full act or a single article."""

    eli_uri: str | None = None
    urn: str | None = None
    human_readable_citation: str | None = None
    source_url: str
    at_date: str | None = None
    article: str | None = None
    article_num: str | None = None
    article_heading: str | None = None
    format: TextFormat = "text"
    content: str = ""
    byte_size: int = 0
    article_count: int = 0
    dataset_note: str = DATASET_NOTE


class ResolveQuery(_Tolerant):
    """Arguments for ``it_resolve``."""

    act_type: str = Field(description="e.g. 'legge', 'decreto.legislativo', 'dpr', 'regio.decreto'")
    year: int = Field(ge=1861, le=2100)
    number: int | None = Field(default=None, ge=1)
    month: int | None = Field(default=None, ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)
    authority: str = "stato"


# ---------------------------------------------------------------------------
# it_verify_citations
# ---------------------------------------------------------------------------

CitationStatus = Literal["verified", "not_found", "content_mismatch", "unverified"]
VerificationStatus = Literal[
    "VERIFIED", "PARTIAL_VERIFIED", "HALLUCINATION_DETECTED", "NO_CITATIONS_FOUND"
]
GapType = Literal[
    "out_of_corpus",          # the reference cannot be checked against any backing source
    "unparseable_citation",   # an article number with no recognizable act in context
    "act_unresolvable",       # act named, but no coordinates a URN can be built from
    "upstream_unavailable",   # Normattiva / the local index could not be reached
    "comma_not_checkable",    # article exists but its commi are not machine-detectable
]


class ContentMatch(_Tolerant):
    """Trigram comparison of a claimed description against the real provision."""

    matched: bool
    method: Literal["exact", "trigram-jaccard", "trigram-overlap"]
    score: float


class CitationCheck(_Tolerant):
    """Verification outcome for one citation found in the input text."""

    raw: str
    kind: Literal["statute", "constitutional_caselaw", "caselaw_other"]
    act_reference: str | None = None
    article: str | None = None
    comma: str | None = None
    status: CitationStatus
    detail: str
    range_hint: str | None = None
    claim: str | None = None
    content_match: ContentMatch | None = None
    human_readable_citation: str | None = None
    source_url: str | None = None


class VerificationGap(_Tolerant):
    """An explicit incompleteness of the verification - never hidden in prose."""

    gap_type: GapType
    citation: str | None = None
    note: str


class CitationVerificationResult(_Tolerant):
    """Result of ``it_verify_citations``."""

    status: VerificationStatus
    summary: str
    total: int
    verified_count: int
    failed_count: int
    warning_count: int
    citations: list[CitationCheck] = Field(default_factory=list)
    gaps: list[VerificationGap] = Field(default_factory=list)
    dataset_note: str = DATASET_NOTE
