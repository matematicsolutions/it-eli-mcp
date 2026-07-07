"""Normalize a raw SentenzeWeb Solr document into a clean record.

Solr returns most text fields as single-element lists (``["value"]``); we unwrap
them, unescape nothing (the OCR text is not HTML-escaped), and only normalize
whitespace. We never rewrite the wording of ``ocr``/``ocrdis``.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .citations import human_citation, source_url

_SPACES_RE = re.compile(r"[ \t]+")
_NL_RE = re.compile(r"\n{3,}")


def _first(v: Any) -> str:
    """Solr multi-valued fields arrive as ``["x"]``; scalar fields as ``"x"``."""
    if isinstance(v, list):
        return str(v[0]).strip() if v else ""
    if isinstance(v, str):
        return v.strip()
    return "" if v is None else str(v).strip()


def _clean(text: Any) -> str:
    s = _first(text)
    if not s:
        return ""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = _SPACES_RE.sub(" ", s)
    s = _NL_RE.sub("\n\n", s)
    s = "\n".join(line.strip() for line in s.split("\n"))
    return s.strip()


def _iso_date(yyyymmdd: str) -> str:
    """'20210722' -> '2021-07-22'. Returns '' if not 8 digits."""
    s = (yyyymmdd or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return ""


@dataclass
class Decision:
    """A normalized Corte di Cassazione (SentenzeWeb) decision."""

    sic_id: str
    kind: str
    numdec: str
    anno: str
    tipoprov: str
    szdec: str
    ssz: str
    materia: str
    presidente: str
    relatore: str
    data_decisione: str
    data_deposito: str
    testo: str
    massima: str
    citation: str
    source_url: str

    def as_row(self) -> dict[str, str]:
        return asdict(self)


def normalize_decision(raw: dict[str, Any]) -> Decision:
    """Turn one SentenzeWeb Solr document into a ``Decision``.

    Raises ``ValueError`` if the record lacks the coordinates needed to cite it
    (year + decision number).
    """
    sic_id = _first(raw.get("id")) or _first(raw.get("sicId"))
    kind = _first(raw.get("kind"))
    numdec = _first(raw.get("numdec"))
    anno = _first(raw.get("anno"))
    if not numdec or not anno:
        raise ValueError("Decision lacks anno+numdec coordinates; cannot cite it.")

    tipoprov = _first(raw.get("tipoprov"))
    szdec = _first(raw.get("szdec"))
    ssz = _first(raw.get("ssz"))

    return Decision(
        sic_id=sic_id,
        kind=kind,
        numdec=numdec,
        anno=anno,
        tipoprov=tipoprov,
        szdec=szdec,
        ssz=ssz,
        materia=_clean(raw.get("materia")),
        presidente=_clean(raw.get("presidente")),
        relatore=_clean(raw.get("relatore")),
        data_decisione=_iso_date(_first(raw.get("datdec"))),
        data_deposito=_iso_date(_first(raw.get("datdep")) or _first(raw.get("pd"))),
        testo=_clean(raw.get("ocr")),
        massima=_clean(raw.get("ocrdis")),
        citation=human_citation(kind, tipoprov, numdec, anno, szdec, ssz) or sic_id,
        source_url=source_url(sic_id, kind),
    )
