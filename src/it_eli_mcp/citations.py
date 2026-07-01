"""Citation contract for Italian acts: eli_uri / human_readable_citation / source_url.

The ELI is read from the Akoma Ntoso ``FRBRalias name="eli"`` (never invented). The
human citation follows the Italian convention and is built from the URN coordinates
(``Legge 7 agosto 1990, n. 241``). The source URL is the stable, human-openable
Normattiva ELI page.
"""

from __future__ import annotations

import re

from .akn import AknDoc
from .urn import NORMATTIVA_BASE, UrnRef, parse_urn

_TRAILING_DATE_RE = re.compile(r"/\d{8}$")


def iso_to_vigenza(iso: str | None) -> str | None:
    """'2020-06-19' -> '20200619' (Normattiva dataVigenza). Returns None if unparseable."""
    if not iso:
        return None
    s = iso.strip()
    if re.fullmatch(r"\d{8}", s):
        return s
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    return None


def eli_source_url(eli: str | None, base_url: str = NORMATTIVA_BASE) -> str:
    """Stable, human-openable Normattiva ELI page URL (trailing point-in-time dropped)."""
    if not eli:
        return base_url
    path = eli.strip().lstrip("/")
    path = _TRAILING_DATE_RE.sub("", path)  # drop the /YYYYMMDD manifestation stamp
    return f"{base_url}/{path}"


def human_citation(doc: AknDoc, urn_ref: UrnRef | None) -> str | None:
    """Italian citation, preferring the URN coordinates, falling back to the AKN."""
    if urn_ref is not None:
        return urn_ref.human_label()
    if doc.urn:
        try:
            return parse_urn(doc.urn).human_label()
        except ValueError:
            pass
    return doc.title


def build_contract(
    doc: AknDoc, urn_ref: UrnRef | None, base_url: str = NORMATTIVA_BASE
) -> dict[str, str | None]:
    """Assemble the citation-contract fields for a parsed act."""
    eli = doc.eli
    return {
        "eli_uri": eli or doc.urn,
        "urn": doc.urn or (urn_ref.urn if urn_ref else None),
        "human_readable_citation": human_citation(doc, urn_ref),
        "title": doc.title,
        "source_url": eli_source_url(eli, base_url),
        "doc_date": doc.doc_date,
    }
