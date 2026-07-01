"""Akoma Ntoso (LegalDocML) parser for Normattiva acts.

Normattiva serves each act as an Akoma Ntoso 3.0 XML document. This module reads
the two things we need without inventing anything:

- **identity** from ``meta/identification/FRBRWork`` - the ``urn:nir`` and ``eli``
  aliases (``FRBRalias``), the promulgation date (``FRBRdate``), and the AKN URI;
- **text** from ``body`` - the articles (``<article>`` with ``<num>`` and content),
  so a caller can fetch a whole act or a single article.

XPath uses the ``{*}`` wildcard namespace so the AKN default namespace and the
various Normattiva-specific prefixes (``na:``, ``nakn:`` ...) do not have to be
registered. Text is extracted verbatim (the act is never rewritten) and only
whitespace-normalized.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree

_WS_RE = re.compile(r"\s+")
_ART_NUM_RE = re.compile(
    r"(\d+)\s*(-?\s*(?:bis|ter|quater|quinquies|sexies|septies|octies|novies))?",
    re.IGNORECASE,
)


@dataclass
class Article:
    """A single article of an act."""

    eid: str | None
    num: str | None       # e.g. "Art. 2043." (verbatim)
    heading: str | None   # rubrica, if present
    text: str             # article body, whitespace-normalized


@dataclass
class AknDoc:
    """Parsed identity + articles of a Normattiva Akoma Ntoso act."""

    urn: str | None = None
    eli: str | None = None
    akn_uri: str | None = None
    doc_type: str | None = None
    doc_date: str | None = None
    title: str | None = None
    articles: list[Article] = field(default_factory=list)

    def article_count(self) -> int:
        return len(self.articles)


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    out = _WS_RE.sub(" ", text).strip()
    return out or None


def _all_text(el: etree._Element) -> str:
    """Concatenate all descendant text of an element, whitespace-normalized."""
    return _WS_RE.sub(" ", " ".join(el.itertext())).strip()


def _aliases(root: etree._Element) -> dict[str, str]:
    """Map every ``FRBRalias`` name -> value found in the document meta."""
    out: dict[str, str] = {}
    for alias in root.findall(".//{*}FRBRalias"):
        name = alias.get("name")
        value = alias.get("value")
        if name and value and name not in out:
            out[name] = value
    return out


def _attr(el: etree._Element | None, name: str) -> str | None:
    """Typed attribute read - lxml ``.get`` is untyped (Any)."""
    if el is None:
        return None
    val = el.get(name)
    return val if isinstance(val, str) and val else None


def _first_frbr_work_date(root: etree._Element) -> str | None:
    work = root.find(".//{*}identification/{*}FRBRWork")
    if work is not None:
        date = _attr(work.find("{*}FRBRdate"), "date")
        if date:
            return date
    return _attr(root.find(".//{*}FRBRdate"), "date")


def _first_frbr_uri(root: etree._Element) -> str | None:
    work = root.find(".//{*}identification/{*}FRBRWork")
    if work is not None:
        value = _attr(work.find("{*}FRBRuri"), "value")
        if value:
            return value
    return _attr(root.find(".//{*}FRBRuri"), "value")


def _title(root: etree._Element) -> str | None:
    dt = root.find(".//{*}preface//{*}docTitle")
    if dt is not None:
        t = _all_text(dt)
        if t:
            return t
    return _attr(root.find(".//{*}FRBRname"), "value")


def _article_heading(article: etree._Element) -> str | None:
    h = article.find("{*}heading")
    if h is not None:
        return _clean(_all_text(h))
    return None


def _article_text(article: etree._Element) -> str:
    """Body text of an article, excluding its own <num> and <heading>."""
    parts: list[str] = []
    for child in article:
        tag = etree.QName(child).localname if isinstance(child.tag, str) else ""
        if tag in ("num", "heading"):
            continue
        parts.append(_all_text(child))
    text = " ".join(p for p in parts if p)
    return _WS_RE.sub(" ", text).strip()


# Italian codes (Codice civile/penale ...) do not carry their articles as <article>
# elements. The enacting decree is a 2-article <act>; each code article lives in its own
# <attachment><doc name="... art. N"> with the text in a <mainBody> paragraph, e.g.
# "Art. 2043. (Risarcimento per fatto illecito). Qualunque fatto ...".
_DOC_ART_NAME_RE = re.compile(
    r"art\.\s*([0-9]+(?:[-\s]?(?:bis|ter|quater|quinquies|sexies|septies|octies|novies))?)",
    re.IGNORECASE,
)
_LEADING_ART_RE = re.compile(
    r"^\s*Art\.?\s*[\w-]+\.?\s*(?:\((?P<heading>[^)]*)\)\.?)?\s*(?P<body>.*)$", re.DOTALL
)


def _articles_from_docs(root: etree._Element) -> list[Article]:
    """Extract code articles from ``<attachment>/<doc name="... art. N">`` blocks."""
    out: list[Article] = []
    for doc in root.findall(".//{*}doc"):
        name = doc.get("name")
        if not name:
            continue
        m = _DOC_ART_NAME_RE.search(name)
        if not m:
            continue
        num_token = _WS_RE.sub("", m.group(1))
        body_el = doc.find(".//{*}mainBody")
        raw = _all_text(body_el) if body_el is not None else _all_text(doc)
        heading: str | None = None
        text = raw
        lead = _LEADING_ART_RE.match(raw)
        if lead:
            heading = _clean(lead.group("heading"))
            text = lead.group("body").strip() or raw
        out.append(
            Article(
                eid=doc.get("eId") or f"art_{num_token}",
                num=f"Art. {num_token}",
                heading=heading,
                text=_WS_RE.sub(" ", text).strip(),
            )
        )
    return out


def parse_akn(xml: bytes | str) -> AknDoc:
    """Parse a Normattiva Akoma Ntoso document into an ``AknDoc``.

    Raises ``ValueError`` if the payload is not parseable as Akoma Ntoso XML.
    """
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True, huge_tree=True)
    try:
        root = etree.fromstring(xml, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"Not parseable as Akoma Ntoso XML: {exc}") from exc
    if root is None:
        raise ValueError("Empty or invalid Akoma Ntoso XML.")

    aliases = _aliases(root)
    doc = AknDoc(
        urn=aliases.get("urn:nir"),
        eli=aliases.get("eli"),
        akn_uri=_first_frbr_uri(root),
        doc_date=_first_frbr_work_date(root),
        title=_title(root),
    )

    # doc type from the <act> element name attribute, if present.
    act = root.find(".//{*}act")
    if act is not None:
        doc.doc_type = act.get("name")

    # Code articles (from <attachment>/<doc>) take priority: for "art. 2043 c.c." the
    # user wants the code text, not the 2-article enacting decree.
    doc.articles.extend(_articles_from_docs(root))

    for article in root.findall(".//{*}article"):
        num_el = article.find("{*}num")
        doc.articles.append(
            Article(
                eid=article.get("eId"),
                num=_clean(_all_text(num_el)) if num_el is not None else None,
                heading=_article_heading(article),
                text=_article_text(article),
            )
        )
    return doc


def _norm_article_key(value: str) -> str:
    """Normalize an article label to a comparison key: 'Art. 2043.' -> '2043'."""
    m = _ART_NUM_RE.search(value)
    if not m:
        return _WS_RE.sub("", value).lower()
    num = m.group(1)
    suffix = m.group(2)
    if suffix:
        suffix = _WS_RE.sub("", suffix).lower().lstrip("-")
        return f"{num}-{suffix}"
    return num


def find_article(doc: AknDoc, article: str) -> Article | None:
    """Find an article by number ('2043', 'art. 2043', '2043-bis'). Case-insensitive."""
    want = _norm_article_key(article)
    for art in doc.articles:
        if art.num and _norm_article_key(art.num) == want:
            return art
        if art.eid and art.eid.lower() == f"art_{want}".replace("-", "_"):
            return art
    return None
