"""Citation helpers for administrative case law (giustizia-amministrativa.it).

Italian convention:

    Cons. St., sez. IV, sent. n. 5450/2026
    C.G.A.R.S., sent. n. 123/2025
    T.A.R. Roma, sez. 1B, sent. n. 11970/2026

The portal's ``numero provvedimento`` is ``YYYYNNNNN`` (publication year + a
zero-padded sequence number); the human citation uses the unpadded sequence
number plus the year. Search results also carry a NATIVE ECLI
(e.g. ``ECLI:IT:CDS:2026:5450SENT``) - we relay it verbatim, never build one.
"""

from __future__ import annotations

_TIPO_ABBR: dict[str, str] = {
    "sentenza": "sent.",
    "ordinanza": "ord.",
    "decreto": "decr.",
    "parere": "parere",
}

_CDS_LABELS = {"consiglio di stato": "Cons. St.", "c.g.a.r.s": "C.G.A.R.S."}


def split_numero_provvedimento(numero_provvedimento: str | None) -> tuple[str, str]:
    """'202605450' -> ('2026', '5450'). ('', '') if not the 9-digit YYYYNNNNN shape."""
    s = (numero_provvedimento or "").strip()
    if len(s) == 9 and s.isdigit():
        return s[:4], s[4:].lstrip("0") or "0"
    return "", ""


def court_label(sede: str | None) -> str:
    """'ROMA' -> 'T.A.R. Roma'; 'CONSIGLIO DI STATO' -> 'Cons. St.'."""
    s = (sede or "").strip()
    if not s:
        return ""
    low = s.lower().rstrip(".")
    if low in _CDS_LABELS:
        return _CDS_LABELS[low]
    return f"T.A.R. {s.title()}"


def tipo_abbr(tipo: str | None) -> str:
    if not tipo:
        return "n."
    return _TIPO_ABBR.get(tipo.strip().lower(), "n.")


def human_citation(
    tipo: str | None,
    sede: str | None,
    sezione: str | None,
    numero_provvedimento: str | None,
) -> str | None:
    """'Cons. St., sez. IV, sent. n. 5450/2026'. None without usable coordinates."""
    anno, seq = split_numero_provvedimento(numero_provvedimento)
    court = court_label(sede)
    if not (anno and seq and court):
        return None
    parts = [court]
    sez = (sezione or "").strip()
    if sez:
        sez_short = sez.upper().removeprefix("SEZIONE").strip()
        if sez_short:
            parts.append(f"sez. {sez_short}")
    abbr = tipo_abbr(tipo)
    parts.append(f"{abbr} n. {seq}/{anno}" if abbr != "n." else f"n. {seq}/{anno}")
    return ", ".join(parts)
