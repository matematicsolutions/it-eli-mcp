"""Normalize a raw Corte Costituzionale open-data decision into a clean record.

The open data ships each decision as a JSON object inside ``elenco_pronunce`` with the
fields below. Text fields are cp1252/latin-1 encoded at the file level and carry HTML
entities (``&#13;`` and friends) plus column-alignment whitespace; we unescape and
normalize, but never rewrite the wording.
"""

from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass
from typing import Any

from .citations import human_citation, source_url, tipologia_label

_SPACES_RE = re.compile(r"[ \t]+")
_NL_RE = re.compile(r"\n{3,}")


def _clean(text: Any) -> str:
    """Unescape HTML entities and normalize whitespace, preserving paragraph breaks."""
    if not isinstance(text, str):
        return ""
    s = html.unescape(text)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = _SPACES_RE.sub(" ", s)
    s = _NL_RE.sub("\n\n", s)
    # strip trailing spaces on each line
    s = "\n".join(line.strip() for line in s.split("\n"))
    return s.strip()


@dataclass
class Decision:
    """A normalized Corte Costituzionale decision."""

    ecli: str
    numero: str
    anno: str
    tipologia: str
    tipologia_label: str
    data_decisione: str
    data_deposito: str
    presidente: str
    relatore: str
    redattore: str
    collegio: str
    epigrafe: str
    testo: str
    dispositivo: str
    citation: str
    source_url: str

    def as_row(self) -> dict[str, str]:
        return asdict(self)


def _s(d: dict[str, Any], key: str) -> str:
    v = d.get(key)
    return v.strip() if isinstance(v, str) else ""


def normalize_decision(raw: dict[str, Any]) -> Decision:
    """Turn one ``elenco_pronunce`` item into a ``Decision``.

    Raises ``ValueError`` if the record lacks a usable ECLI and coordinates.
    """
    numero = _s(raw, "numero_pronuncia")
    anno = _s(raw, "anno_pronuncia")
    tipologia = _s(raw, "tipologia_pronuncia")
    ecli = _s(raw, "ecli") or (f"ECLI:IT:COST:{anno}:{numero}" if anno and numero else "")
    if not ecli:
        raise ValueError("Decision has neither an ECLI nor anno+numero coordinates.")

    return Decision(
        ecli=ecli,
        numero=numero,
        anno=anno,
        tipologia=tipologia,
        tipologia_label=tipologia_label(tipologia) or "",
        data_decisione=_s(raw, "data_decisione"),
        data_deposito=_s(raw, "data_deposito"),
        presidente=_clean(raw.get("presidente")),
        relatore=_clean(raw.get("relatore_pronuncia")),
        redattore=_clean(raw.get("redattore_pronuncia")),
        collegio=_clean(raw.get("collegio")),
        epigrafe=_clean(raw.get("epigrafe")),
        testo=_clean(raw.get("testo")),
        dispositivo=_clean(raw.get("dispositivo")),
        citation=human_citation(numero, anno, tipologia) or ecli,
        source_url=source_url(anno, numero),
    )
