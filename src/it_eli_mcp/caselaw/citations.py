"""ECLI + Italian citation helpers for Corte Costituzionale decisions.

The ECLI is native in the open data (``ecli`` field, e.g. ``ECLI:IT:COST:1956:1``) -
we relay it, we never build it. The human citation follows the Italian convention:
``Corte cost., sent. n. 1/1956`` (sentenza) or ``ord. n. 1/1956`` (ordinanza).
"""

from __future__ import annotations

import re

COURT_URL = "https://www.cortecostituzionale.it"

# tipologia_pronuncia codes in the Court's open data.
TIPOLOGIA_LABELS: dict[str, str] = {
    "S": "Sentenza",
    "O": "Ordinanza",
}
_TIPOLOGIA_ABBR: dict[str, str] = {
    "S": "sent.",
    "O": "ord.",
}

_ECLI_RE = re.compile(r"^ECLI:IT:COST:(\d{4}):(\d+)$", re.IGNORECASE)


def tipologia_label(code: str | None) -> str | None:
    if not code:
        return None
    return TIPOLOGIA_LABELS.get(code.strip().upper(), code.strip())


def human_citation(numero: str | None, anno: str | None, tipologia: str | None) -> str | None:
    """Italian citation, e.g. 'Corte cost., sent. n. 1/1956'."""
    if not numero or not anno:
        return None
    abbr = _TIPOLOGIA_ABBR.get((tipologia or "").strip().upper(), "n.")
    if abbr == "n.":
        return f"Corte cost., n. {numero}/{anno}"
    return f"Corte cost., {abbr} n. {numero}/{anno}"


def source_url(anno: str | None, numero: str | None) -> str:
    """Canonical, human-openable decision page on the Court's site."""
    if anno and numero:
        return f"{COURT_URL}/actionSchedaPronuncia.do?anno={anno}&numero={numero}"
    return COURT_URL


def parse_ecli(ecli: str) -> tuple[str, str] | None:
    """'ECLI:IT:COST:1956:1' -> ('1956', '1'). Returns None if not a COST ECLI."""
    m = _ECLI_RE.match(ecli.strip())
    if not m:
        return None
    return m.group(1), m.group(2)


def build_ecli(anno: str, numero: str) -> str:
    return f"ECLI:IT:COST:{anno}:{numero}"
