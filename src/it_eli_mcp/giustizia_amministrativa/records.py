"""Parse the giustizia-amministrativa.it search HTML and the mdp document XML.

Two payload shapes, both verified live 2026-07-08 (see DISCOVERY.md):

- The Liferay portlet's search response is server-rendered HTML: one
  ``<article class="ricerca--item">`` per hit, carrying the mdp full-text URL,
  a ``<b>TIPO</b> sede di <b>SEDE</b>, sezione <b>SEZ</b>, numero provv.: <b>N</b>``
  metadata line, a snippet, the NRG ("Numero ricorso") and a NATIVE ECLI.
- The mdp ``visualizza`` endpoint returns the decision as structured GA XML
  (``<GA><Provvedimento><meta>...<epigrafe>...<motivazione>...<dispositivo>``),
  with the registry coordinates in ``<descrittori>`` and the text in
  ``h:div`` elements. We extract text section by section, never rewriting it.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from lxml import etree

from .citations import human_citation, split_numero_provvedimento

_ARTICLE_RE = re.compile(r'<article class="ricerca--item">(.*?)</article>', re.S)
_TOTAL_RE = re.compile(r"Trovati\s*<strong>\s*(\d+)\s*</strong>\s*risultati")
_DOC_URL_RE = re.compile(
    r'"(https://mdp\.giustizia-amministrativa\.it/visualizza/\?[^"]+)"'
)
_META_RE = re.compile(
    r"<b>([^<]+)</b>\s*sede di\s*<b>([^<]+)</b>,\s*sezione\s*<b>([^<]*)</b>,"
    r"\s*numero provv\.:\s*<b>(\d+)</b>"
)
_SNIPPET_RE = re.compile(r'<div class="col-sm-12 snippet">\s*(.*?)\s*</div>', re.S)
_NRG_RE = re.compile(r"Numero ricorso:\s*<b>(\d+)</b>")
_ECLI_RE = re.compile(r"<b>(ECLI:IT:[A-Z0-9:]+)</b>")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


class GaParseError(Exception):
    """The portal HTML / document XML did not match the known shape."""


def _strip_tags(html: str) -> str:
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", html)).strip()


@dataclass
class GaHit:
    """One search hit from the decision search (CdS / C.G.A.R.S. / TAR)."""

    tipo: str
    sede: str
    sezione: str
    numero_provvedimento: str
    anno: str
    numero: str
    numero_ricorso: str
    ecli: str
    citation: str
    document_url: str
    document_format: str  # 'xml' (machine-readable full text) or 'pdf' (PDF-only)
    snippet: str

    def as_row(self) -> dict[str, str]:
        return asdict(self)


def parse_search_html(html: str) -> tuple[int, list[GaHit]]:
    """Extract (total_found, hits) from a portlet search response.

    Raises ``GaParseError`` if the total marker is absent (the portal layout
    changed, or the response is an error page).
    """
    m_total = _TOTAL_RE.search(html)
    if not m_total:
        raise GaParseError(
            "No 'Trovati N risultati' marker in the search response - "
            "the portal layout may have changed."
        )
    total = int(m_total.group(1))

    hits: list[GaHit] = []
    for m_art in _ARTICLE_RE.finditer(html):
        block = m_art.group(1)
        m_meta = _META_RE.search(block)
        urls = [u.replace("&amp;", "&") for u in _DOC_URL_RE.findall(block)]
        if not m_meta or not urls:
            continue  # a malformed item; skip rather than mis-cite
        # some provvedimenti are published PDF-only (nomeFile=..._NN.pdf);
        # prefer the machine-readable .html (GA XML) variant when present
        html_urls = [u for u in urls if ".html" in u]
        doc_url = html_urls[0] if html_urls else urls[0]
        doc_format = "xml" if html_urls else "pdf"
        tipo, sede, sezione, numero_provv = (g.strip() for g in m_meta.groups())
        anno, numero = split_numero_provvedimento(numero_provv)
        m_snip = _SNIPPET_RE.search(block)
        m_nrg = _NRG_RE.search(block)
        m_ecli = _ECLI_RE.search(block)
        hits.append(
            GaHit(
                tipo=tipo,
                sede=sede,
                sezione=sezione,
                numero_provvedimento=numero_provv,
                anno=anno,
                numero=numero,
                numero_ricorso=m_nrg.group(1) if m_nrg else "",
                ecli=m_ecli.group(1) if m_ecli else "",
                citation=human_citation(tipo, sede, sezione, numero_provv) or numero_provv,
                document_url=doc_url,
                document_format=doc_format,
                snippet=_strip_tags(m_snip.group(1)) if m_snip else "",
            )
        )
    return total, hits


@dataclass
class GaDocument:
    """A full decision fetched from the mdp ``visualizza`` endpoint."""

    tipologia: str
    urn: str
    anno: str
    numero: str
    nrg_anno: str
    nrg_numero: str
    data_pubblicazione: str
    testo: str

    def as_row(self) -> dict[str, str]:
        return asdict(self)


# Body sections in reading order. The *Ted variants (bilingual Bolzano/Trento
# German text) are included when present.
_BODY_SECTIONS = (
    "epigrafe",
    "oggetto",
    "ricorrenti",
    "resistenti",
    "controinteressati",
    "intervenienti",
    "altro",
    "visto",
    "esaminato",
    "premessa",
    "motivazione",
    "dispositivo",
    "sottoscrizioni",
)


def _section_text(root: etree._Element, tag: str) -> str:
    parts: list[str] = []
    for sec in root.iter(tag):
        for div in sec.iter("{http://www.w3.org/HTML/1998/html4}div"):
            t = _WS_RE.sub(" ", "".join(div.itertext())).strip()
            if t:
                parts.append(t)
    return "\n".join(parts)


def _iso_date(dd_mm_yyyy: str) -> str:
    """'01/07/2026' -> '2026-07-01'. '' if not that shape."""
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", (dd_mm_yyyy or "").strip())
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def parse_document(content: bytes) -> GaDocument:
    """Parse the GA XML returned by mdp ``visualizza`` into a ``GaDocument``.

    Raises ``GaParseError`` for non-XML (e.g. the mdp 404 HTML page) or XML
    without the ``<Provvedimento>`` structure.
    """
    # strip a UTF-8 BOM and stray leading whitespace before the XML declaration
    # (production-line gotcha: some GA documents arrive BOM-prefixed)
    content = content.lstrip(b"\xef\xbb\xbf\xff\xfe\r\n\t ")
    try:
        root = etree.fromstring(content)  # bytes: honours the XML encoding decl
    except etree.XMLSyntaxError as exc:
        raise GaParseError(
            "Document is not the expected GA XML (got HTML or malformed XML - "
            "the id may not exist, or the mdp endpoint changed)."
        ) from exc
    prov = root.find("Provvedimento")
    if prov is None:
        raise GaParseError("GA XML lacks a <Provvedimento> element.")

    def _find_text(path: str) -> str:
        el = prov.find(path)
        return (el.text or "").strip() if el is not None else ""

    fascicolo = prov.find("meta/descrittori/fascicolo")
    registro = prov.find("meta/descrittori/registro")
    body = "\n\n".join(
        t for t in (_section_text(prov, s) for s in _BODY_SECTIONS) if t
    )
    return GaDocument(
        tipologia=_find_text("meta/tipologia"),
        urn=_find_text("meta/descrittori/urn"),
        anno=(fascicolo.get("anno") or "") if fascicolo is not None else "",
        numero=(fascicolo.get("n") or "") if fascicolo is not None else "",
        nrg_anno=(registro.get("anno") or "") if registro is not None else "",
        nrg_numero=(registro.get("n") or "") if registro is not None else "",
        data_pubblicazione=_iso_date(_find_text("meta/dataPubblicazione")),
        testo=body,
    )
