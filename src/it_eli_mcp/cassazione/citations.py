"""Citation helpers for Corte di Cassazione decisions (SentenzeWeb records).

The Court's Solr index has no ECLI field, so we build a human citation from the
record's own coordinates instead. Italian convention:

    Cass. civ., Sez. V, ord. n. 21018/2021
    Cass. pen., Sez. III, sent. n. 12345/2020
    Cass. civ., Sez. lav., sent. n. 4567/2019      (szdec "L" - Labour Chamber)
    Cass. civ., Sez. trib., sent. n. 8901/2022     (szdec "5" - Tax Chamber)

``sicId`` values are the internal SentenzeWeb primary key; there is no cross-court
canonical identifier such as ECLI or a URN for Cassazione decisions today, so
``source_url`` (a stable, re-runnable SentenzeWeb query) is the grounding anchor.
"""

from __future__ import annotations

COURT_URL = "https://www.italgiure.giustizia.it/sncass/"

_KIND_LABELS: dict[str, str] = {
    "snciv": "Cass. civ.",
    "snpen": "Cass. pen.",
}

# tipoprov as returned by the index ("Sentenza", "Ordinanza", ...) mapped to the
# lowercase abbreviation used in Italian citation style.
_TIPO_ABBR: dict[str, str] = {
    "sentenza": "sent.",
    "ordinanza": "ord.",
    "decreto": "decr.",
}

# szdec sub-chamber codes -> section label. "0" means "not a specialized section"
# (an ordinary numbered civil/criminal section, reported instead via `ssz`/`numdec`
# context) - we only special-case the two named chambers the index documents.
_SZDEC_LABELS: dict[str, str] = {
    "L": "Sez. lav.",
    "5": "Sez. trib.",
}


def tipo_abbr(tipoprov: str | None) -> str:
    if not tipoprov:
        return "n."
    return _TIPO_ABBR.get(tipoprov.strip().lower(), "n.")


def section_label(kind: str | None, szdec: str | None, ssz: str | None) -> str | None:
    """Best-effort section label, e.g. 'Sez. lav.', 'Sez. trib.', 'Sez. III'."""
    if szdec and szdec.strip().upper() in _SZDEC_LABELS:
        return _SZDEC_LABELS[szdec.strip().upper()]
    if ssz and ssz.strip() not in ("", "0"):
        roman = _to_roman(ssz.strip())
        if roman:
            return f"Sez. {roman}"
    return None


_ROMAN_TABLE = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]


def _to_roman(n: str) -> str | None:
    try:
        i = int(n)
    except ValueError:
        return None
    if 1 <= i <= len(_ROMAN_TABLE):
        return _ROMAN_TABLE[i - 1]
    return None


def human_citation(
    kind: str | None,
    tipoprov: str | None,
    numdec: str | None,
    anno: str | None,
    szdec: str | None = None,
    ssz: str | None = None,
) -> str | None:
    """'Cass. civ., Sez. lav., sent. n. 21018/2021'. None if numdec/anno are missing."""
    if not numdec or not anno:
        return None
    kind_label = _KIND_LABELS.get((kind or "").strip().lower(), "Cass.")
    abbr = tipo_abbr(tipoprov)
    sez = section_label(kind, szdec, ssz)
    parts = [kind_label]
    if sez:
        parts.append(sez)
    parts.append(f"{abbr} n. {numdec}/{anno}")
    return ", ".join(parts)


def source_url(sic_id: str | None, kind: str | None = None) -> str:
    """SentenzeWeb has no stable per-decision permalink; point at the search portal
    with the record's internal id as query context so a human can re-find it."""
    if sic_id:
        return f"{COURT_URL}#id={sic_id}"
    return COURT_URL
