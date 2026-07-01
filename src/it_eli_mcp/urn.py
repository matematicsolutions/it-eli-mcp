"""Italian legal identifiers: URN:NIR, the Normattiva ELI, and the codes dictionary.

Italy does not expose a clean REST API. It exposes two stable, keyless identifier
schemes that both resolve on ``normattiva.it``:

- **URN:NIR** - ``urn:nir:{authority}:{measure-type}:{date};{number}``
  e.g. ``urn:nir:stato:legge:1990-08-07;241`` (Legge 7 agosto 1990, n. 241).
- **ELI** - ``eli/id/{year}/{month}/{day}/{codiceRedazionale}/{version}[/{pit}]``
  e.g. ``eli/id/1990/08/18/090G0294/CONSOLIDATED`` (embedded in the Akoma Ntoso
  ``FRBRalias name="eli"``).

A URN is constructible from act coordinates (type + date + number), so we build it;
the ELI is only knowable after resolving the act (it embeds the Gazzetta code), so we
read it from the AKN and never invent it.

The codes dictionary maps friendly names ("codice civile") to the canonical URN of
the founding act. Every URN here was verified to resolve on normattiva.it (the act
page carries a ``caricaAKN`` link) on 2026-07-01.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

NORMATTIVA_BASE = "https://www.normattiva.it"

# Friendly measure-type input -> canonical URN:NIR measure-type token.
MEASURE_TYPE_ALIASES: dict[str, str] = {
    "legge": "legge",
    "l": "legge",
    "decreto.legislativo": "decreto.legislativo",
    "decreto legislativo": "decreto.legislativo",
    "dlgs": "decreto.legislativo",
    "d.lgs": "decreto.legislativo",
    "d.lgs.": "decreto.legislativo",
    "decreto.legge": "decreto.legge",
    "decreto legge": "decreto.legge",
    "dl": "decreto.legge",
    "d.l": "decreto.legge",
    "d.l.": "decreto.legge",
    "dpr": "decreto.del.presidente.della.repubblica",
    "d.p.r": "decreto.del.presidente.della.repubblica",
    "d.p.r.": "decreto.del.presidente.della.repubblica",
    "regio.decreto": "regio.decreto",
    "regio decreto": "regio.decreto",
    "rd": "regio.decreto",
    "r.d": "regio.decreto",
    "r.d.": "regio.decreto",
    "costituzione": "costituzione",
}

# Human label for a measure-type token (Italian citation convention).
MEASURE_TYPE_LABELS: dict[str, str] = {
    "legge": "Legge",
    "decreto.legislativo": "Decreto legislativo",
    "decreto.legge": "Decreto-legge",
    "decreto.del.presidente.della.repubblica": "D.P.R.",
    "regio.decreto": "Regio decreto",
    "costituzione": "Costituzione",
}

# Codes / consolidated acts -> canonical URN. Each URN verified to resolve (2026-07-01).
CODES: dict[str, dict[str, str]] = {
    "costituzione": {
        "urn": "urn:nir:stato:costituzione:1947-12-27",
        "label": "Costituzione della Repubblica Italiana",
    },
    "codice civile": {
        "urn": "urn:nir:stato:regio.decreto:1942-03-16;262",
        "label": "Codice civile (R.D. 16 marzo 1942, n. 262)",
    },
    "codice penale": {
        "urn": "urn:nir:stato:regio.decreto:1930-10-19;1398",
        "label": "Codice penale (R.D. 19 ottobre 1930, n. 1398)",
    },
    "codice di procedura civile": {
        "urn": "urn:nir:stato:regio.decreto:1940-10-28;1443",
        "label": "Codice di procedura civile (R.D. 28 ottobre 1940, n. 1443)",
    },
    "codice di procedura penale": {
        "urn": "urn:nir:presidente.repubblica:decreto:1988-09-22;447",
        "label": "Codice di procedura penale (D.P.R. 22 settembre 1988, n. 447)",
    },
    "codice privacy": {
        "urn": "urn:nir:stato:decreto.legislativo:2003-06-30;196",
        "label": "Codice in materia di protezione dei dati personali (D.Lgs. 196/2003)",
    },
    "codice dell'amministrazione digitale": {
        "urn": "urn:nir:stato:decreto.legislativo:2005-03-07;82",
        "label": "Codice dell'amministrazione digitale - CAD (D.Lgs. 82/2005)",
    },
    "decreto legislativo 231/2001": {
        "urn": "urn:nir:stato:decreto.legislativo:2001-06-08;231",
        "label": "Responsabilita amministrativa degli enti (D.Lgs. 231/2001)",
    },
    "legge 241/1990": {
        "urn": "urn:nir:stato:legge:1990-08-07;241",
        "label": "Norme sul procedimento amministrativo (L. 241/1990)",
    },
}

# Common aliases mapped to a codes-dictionary key.
CODE_ALIASES: dict[str, str] = {
    "cc": "codice civile",
    "c.c.": "codice civile",
    "cp": "codice penale",
    "c.p.": "codice penale",
    "cpc": "codice di procedura civile",
    "c.p.c.": "codice di procedura civile",
    "cpp": "codice di procedura penale",
    "c.p.p.": "codice di procedura penale",
    "cad": "codice dell'amministrazione digitale",
    "gdpr": "codice privacy",
    "d.lgs. 231/2001": "decreto legislativo 231/2001",
    "231/2001": "decreto legislativo 231/2001",
    "l. 241/1990": "legge 241/1990",
    "241/1990": "legge 241/1990",
    "costituzione italiana": "costituzione",
}

_URN_RE = re.compile(
    r"^urn:nir:(?P<authority>[a-z.]+):(?P<mtype>[a-z.]+)"
    r"(?::(?P<date>\d{4}(?:-\d{2}-\d{2})?)(?:;(?P<number>[\w-]+))?)?$"
)
_ELI_PATH_RE = re.compile(r"eli/id/\d{4}/\d{2}/\d{2}/[0-9A-Za-z]+")


@dataclass(frozen=True)
class UrnRef:
    """A parsed URN:NIR reference to an Italian act."""

    urn: str
    authority: str
    measure_type: str
    date: str | None = None
    number: str | None = None

    def human_label(self) -> str:
        """Italian citation, e.g. 'Legge 7 agosto 1990, n. 241'.

        For a partial URN (year only, no promulgation day) falls back to the
        practitioner short form 'Legge n. 241/1990'.
        """
        base = MEASURE_TYPE_LABELS.get(self.measure_type, self.measure_type)
        date = self.date
        if date and len(date) == 10 and self.number:
            return f"{base} {_date_it(date)}, n. {self.number}"
        if date and len(date) == 10:
            return f"{base} {_date_it(date)}"
        if date and self.number:  # year-only partial
            return f"{base} n. {self.number}/{date}"
        if date:
            return f"{base} {date}"
        return base


_MONTHS_IT = [
    "", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


def _date_it(iso: str) -> str:
    """'1990-08-07' -> '7 agosto 1990'."""
    try:
        y, m, d = iso.split("-")
        return f"{int(d)} {_MONTHS_IT[int(m)]} {int(y)}"
    except (ValueError, IndexError):
        return iso


def normalize_measure_type(value: str) -> str:
    """Map a friendly measure-type input to a canonical URN token."""
    key = value.strip().lower()
    return MEASURE_TYPE_ALIASES.get(key, key)


def build_urn(
    measure_type: str,
    year: int,
    number: int | str | None = None,
    *,
    month: int | None = None,
    day: int | None = None,
    authority: str = "stato",
) -> str:
    """Build a URN:NIR from act coordinates.

    A full URN needs the exact promulgation date (``year-month-day``); when only the
    year is known the URN is incomplete and will not resolve - callers should prefer
    a known code from ``CODES`` or supply month/day.
    """
    mtype = normalize_measure_type(measure_type)
    if month and day:
        date = f"{year:04d}-{month:02d}-{day:02d}"
        if number is not None:
            return f"urn:nir:{authority}:{mtype}:{date};{number}"
        return f"urn:nir:{authority}:{mtype}:{date}"
    # Year-only: return a best-effort partial (may not resolve).
    if number is not None:
        return f"urn:nir:{authority}:{mtype}:{year};{number}"
    return f"urn:nir:{authority}:{mtype}:{year}"


def parse_urn(value: str) -> UrnRef:
    """Parse a URN:NIR string into a ``UrnRef``. Raises ``ValueError`` on bad input."""
    m = _URN_RE.match(value.strip())
    if not m:
        raise ValueError(
            f"Not a URN:NIR: {value!r}. Expected e.g. 'urn:nir:stato:legge:1990-08-07;241'."
        )
    return UrnRef(
        urn=value.strip(),
        authority=m.group("authority"),
        measure_type=m.group("mtype"),
        date=m.group("date"),
        number=m.group("number"),
    )


def is_urn(value: str) -> bool:
    return value.strip().lower().startswith("urn:nir:")


def resolve_code(name: str) -> dict[str, str] | None:
    """Resolve a friendly code name / alias to its dictionary entry (urn + label)."""
    key = name.strip().lower()
    key = CODE_ALIASES.get(key, key)
    return CODES.get(key)


def entry_url(reference: str) -> str:
    """Return the Normattiva entry URL for any supported reference.

    Accepts: a URN:NIR, an ``eli/id/...`` path, a full normattiva.it URL, or a
    friendly code name (resolved via ``CODES`` / ``CODE_ALIASES``).
    Raises ``ValueError`` if nothing matches.
    """
    ref = reference.strip()

    # 1. Already a normattiva URL.
    if ref.startswith("http://") or ref.startswith("https://"):
        if "normattiva.it" not in ref:
            raise ValueError(f"Only normattiva.it URLs are supported, got: {ref!r}")
        return ref

    # 2. A friendly code name.
    code = resolve_code(ref)
    if code is not None:
        return f"{NORMATTIVA_BASE}/uri-res/N2Ls?{code['urn']}"

    # 3. A URN:NIR.
    if is_urn(ref):
        return f"{NORMATTIVA_BASE}/uri-res/N2Ls?{ref}"

    # 4. An ELI path (optionally with a leading slash).
    eli = ref.lstrip("/")
    if _ELI_PATH_RE.match(eli):
        # Ensure a version segment so Normattiva serves a concrete manifestation.
        segments = eli.split("/")
        if len(segments) == 6:  # eli/id/Y/M/D/CODE without a version segment
            eli = eli + "/CONSOLIDATED"
        return f"{NORMATTIVA_BASE}/{eli}"

    raise ValueError(
        f"Unrecognized reference: {reference!r}. Expected a URN:NIR "
        f"(urn:nir:stato:legge:1990-08-07;241), an ELI path (eli/id/1990/08/18/090G0294), "
        f"a normattiva.it URL, or a known code name (see it_list_codes)."
    )
