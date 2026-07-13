"""Citation parsing and content matching for ``it_verify_citations``.

Pure functions only - no network, no SQLite. The tool in ``server.py`` does the
lookups; this module extracts Italian statute citations from free text and
scores a claimed description against the real provision text.

Pattern credit: the parse-verify-report loop (act-name lookback with a stopword
strip, existence check with a range hint, optional content matching, hard
``[HALLUCINATION_DETECTED]`` semantics) is adapted from chrisryugj/korean-law-mcp
(MIT). The Korean original uses character bigrams because Korean is agglutinative;
for Italian (Latin script) character trigrams discriminate better, so the content
matcher here is trigram-based. See THIRD_PARTY.md.

Supported citation shapes (all case-insensitive):

- ``art. 2043 c.c.`` / ``art. 2043 cod. civ.`` / ``articolo 2043 del codice civile``
- ``artt. 1341 e 1342 c.c.`` (enumerations)
- ``art. 5 della legge 7 agosto 1990, n. 241`` / ``art. 5 l. 241/1990``
- ``art. 6 del d.lgs. 231/2001`` / ``art. 21-septies della l. n. 241 del 1990``
- ``art. 117, comma 2, Cost.``
- ``ECLI:IT:COST:2024:1`` (Constitutional Court, checked against the local index)

The act reference is searched AFTER the article number first (the usual Italian
order), then BEFORE it (``la legge 241/1990, all'art. 5``). A claimed description
in parentheses right after the citation (``art. 2043 c.c. (risarcimento per fatto
illecito)``) becomes the content-check claim.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Citation parsing
# ---------------------------------------------------------------------------

_SUFFIX = r"(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies|undecies|duodecies)"

# "art. 2043", "artt. 1341", "articolo 21-septies"
_ART_RE = re.compile(
    rf"\bart(?:icol[oi]|t)?\.?\s*(\d+)(?:\s*-\s*({_SUFFIX}))?\b",
    re.IGNORECASE,
)

# Enumeration continuation: "artt. 1341 e 1342", "artt. 2, 3 e 4".
# The lookaheads keep "art. 5, comma 2" and ordinals ("2°") out of the list.
_ART_CONT_RE = re.compile(
    rf"\s*(?:,|;|\be\b|\bed\b)\s*(\d+)(?:\s*-\s*({_SUFFIX}))?\b(?!\s*°)(?!\s*comma)",
    re.IGNORECASE,
)

# ", comma 2" / ", co. 1-bis" right after the article number(s)
_COMMA_RE = re.compile(
    rf"^\s*,?\s*(?:co\.|comma)\s*(\d+(?:\s*-\s*{_SUFFIX})?)",
    re.IGNORECASE,
)

# ECLI of any Italian court; only ECLI:IT:COST is locally checkable.
_ECLI_RE = re.compile(r"\bECLI:IT:([A-Z]+):(\d{4}):([0-9A-Z]+)\b", re.IGNORECASE)

# Code abbreviations, LONGEST FIRST so "c.p.c." never half-matches as "c.p.".
# Each pattern maps to a key of urn.CODES. Word/dot boundaries guard the short
# forms (the KP-vs-KPC lesson: short legal abbreviations without boundaries
# produce mass noise).
_CODE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<![\w.])(?:c\.p\.p\.|cod\.\s*proc\.\s*pen\."
                r"|codice\s+di\s+procedura\s+penale)", re.IGNORECASE),
     "codice di procedura penale"),
    (re.compile(r"(?<![\w.])(?:c\.p\.c\.|cod\.\s*proc\.\s*civ\."
                r"|codice\s+di\s+procedura\s+civile)", re.IGNORECASE),
     "codice di procedura civile"),
    (re.compile(r"(?<![\w.])(?:c\.c\.|cod\.\s*civ\.|codice\s+civile)", re.IGNORECASE),
     "codice civile"),
    (re.compile(r"(?<![\w.])(?:c\.p\.|cod\.\s*pen\.|codice\s+penale)", re.IGNORECASE),
     "codice penale"),
    (re.compile(r"(?<![\w.])(?:cost\.|costituzione\b)", re.IGNORECASE),
     "costituzione"),
    (re.compile(r"(?<![\w.])(?:codice\s+privacy"
                r"|codice\s+in\s+materia\s+di\s+protezione\s+dei\s+dati)", re.IGNORECASE),
     "codice privacy"),
    (re.compile(r"(?<![\w.])(?:cad\b|codice\s+dell'amministrazione\s+digitale)", re.IGNORECASE),
     "codice dell'amministrazione digitale"),
]

_MONTHS_IT = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}
_MONTHS_ALT = "|".join(_MONTHS_IT)

# Act coordinates: "legge 7 agosto 1990, n. 241", "l. 241/1990", "d.lgs. n. 196
# del 2003", "d.p.r. 447/1988", "r.d. 262/1942". Alternatives are ordered so
# "d.lgs." wins over "d.l." at the same position; regex earliest-match keeps
# "decreto legge" from resolving as bare "legge".
_COORD_RE = re.compile(
    rf"""
    (?<![\w.])
    (?P<type>
        decreto\s+legislativo | d\.\s*lgs\.? | dlgs |
        decreto[-\s]legge | d\.\s*l\. |
        d\.\s*p\.\s*r\.? | dpr |
        regio\s+decreto | r\.\s*d\. |
        legge | l\.
    )
    \s*
    (?:(?P<day>\d{{1,2}})°?\s+(?P<month>{_MONTHS_ALT})\s+(?P<dyear>\d{{4}})\s*,?\s*)?
    (?:n\.?\s*)?
    (?P<number>\d+)
    (?:\s*/\s*(?P<yslash>\d{{4}})|\s+del\s+(?P<ydel>\d{{4}}))?
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Normalized coordinate type token -> it_resolve-compatible act_type.
_TYPE_MAP = {
    "legge": "legge", "l": "legge",
    "decretolegislativo": "decreto.legislativo", "dlgs": "decreto.legislativo",
    "decretolegge": "decreto.legge", "dl": "decreto.legge",
    "dpr": "dpr",
    "regiodecreto": "regio.decreto", "rd": "regio.decreto",
}

# How far around the article number we look for the act reference.
_AFTER_WINDOW = 90
_AFTER_MAX_START = 45   # the act ref must begin close to the article number
_BEFORE_WINDOW = 100
_BEFORE_MIN_START = 40  # ... or end close before it

# Claimed description: "(risarcimento per fatto illecito)" right after the
# citation. Rejected when it looks like a date, an amendment note, another
# citation, or carries no letters.
_CLAIM_RE = re.compile(r"^\s*[(«]([^)»]{3,120})[)»]")
_CLAIM_REJECT = re.compile(
    r"^\s*(?:\d|art\b|artt\b|comma\b|legge\b|l\.|d\.|come\s+modificat|abrogat|introdott)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedCitation:
    """One citation extracted from free text, before verification."""

    raw: str                       # the citation as it appears in the text
    kind: str                      # "statute" | "ecli"
    article: str | None = None     # normalized article key, e.g. "2043", "21-septies"
    comma: str | None = None       # e.g. "2", "1-bis"
    code_key: str | None = None    # urn.CODES key when a code abbreviation matched
    act_type: str | None = None    # it_resolve act_type when coordinates matched
    act_number: str | None = None
    act_year: int | None = None
    act_month: int | None = None
    act_day: int | None = None
    ecli: str | None = None        # normalized ECLI when kind == "ecli"
    ecli_court: str | None = None  # "COST", "CASS", "CDS", ...
    claim: str | None = None       # claimed description for the content check


def _match_code(window: str) -> tuple[str, re.Match[str]] | None:
    """First code-abbreviation match in ``window``, longest patterns first."""
    best: tuple[str, re.Match[str]] | None = None
    for pattern, key in _CODE_PATTERNS:
        m = pattern.search(window)
        if m and (best is None or m.start() < best[1].start()):
            best = (key, m)
    return best


def _coord_fields(m: re.Match[str]) -> dict[str, object] | None:
    """Coordinate regex match -> act fields, or None when the year is missing."""
    year_s = m.group("dyear") or m.group("yslash") or m.group("ydel")
    if not year_s:
        return None
    token = re.sub(r"[^a-z]", "", m.group("type").lower())
    act_type = _TYPE_MAP.get(token)
    if act_type is None:
        return None
    fields: dict[str, object] = {
        "act_type": act_type,
        "act_number": m.group("number"),
        "act_year": int(year_s),
    }
    if m.group("dyear"):
        fields["act_month"] = _MONTHS_IT[m.group("month").lower()]
        fields["act_day"] = int(m.group("day"))
    return fields


def _act_from_after(window: str) -> tuple[dict[str, object], int] | None:
    """Act reference in the text AFTER the article number (usual Italian order)."""
    code = _match_code(window)
    coord = _COORD_RE.search(window)
    code_pos = code[1].start() if code else None
    coord_pos = coord.start() if coord else None
    # Prefer whichever reference starts first; both must start near the article.
    code_first = code_pos is not None and (coord_pos is None or code_pos <= coord_pos)
    if code is not None and code_first and code[1].start() <= _AFTER_MAX_START:
        return {"code_key": code[0]}, code[1].end()
    if coord is not None and coord.start() <= _AFTER_MAX_START:
        fields = _coord_fields(coord)
        if fields is not None:
            return fields, coord.end()
    return None


def _act_from_before(window: str) -> dict[str, object] | None:
    """Act reference BEFORE the article number ("la legge 241/1990, all'art. 5")."""
    last_fields: dict[str, object] | None = None
    last_end = -1
    for m in _COORD_RE.finditer(window):
        fields = _coord_fields(m)
        if fields is not None and m.end() > last_end:
            last_fields, last_end = fields, m.end()
    code = None
    for pattern, key in _CODE_PATTERNS:
        for m in pattern.finditer(window):
            if code is None or m.end() > code[1]:
                code = ({"code_key": key}, m.end())
    if code is not None and code[1] > last_end:
        last_fields, last_end = code[0], code[1]
    if last_fields is not None and last_end >= len(window) - _BEFORE_MIN_START:
        return last_fields
    return None


def _extract_claim(after: str) -> str | None:
    m = _CLAIM_RE.match(after)
    if not m:
        return None
    claim = m.group(1).strip()
    if not re.search(r"[a-zà-ÿ]", claim, re.IGNORECASE):
        return None
    if _CLAIM_REJECT.match(claim):
        return None
    return claim


def _article_key(num: str, suffix: str | None) -> str:
    return f"{num}-{suffix.lower()}" if suffix else num


def parse_citations(text: str, max_citations: int = 15) -> list[ParsedCitation]:
    """Extract statute and ECLI citations from ``text``, deduplicated, in order."""
    citations: list[ParsedCitation] = []
    seen: set[tuple[object, ...]] = set()

    for m in _ART_RE.finditer(text):
        if len(citations) >= max_citations:
            break
        articles = [_article_key(m.group(1), m.group(2))]
        end = m.end()
        while True:
            cont = _ART_CONT_RE.match(text, end)
            if cont is None:
                break
            articles.append(_article_key(cont.group(1), cont.group(2)))
            end = cont.end()

        comma: str | None = None
        cm = _COMMA_RE.match(text[end:end + 30])
        if cm is not None:
            comma = re.sub(r"\s+", "", cm.group(1)).lower()
            end += cm.end()

        after = text[end:end + _AFTER_WINDOW]
        act: dict[str, object] = {}
        claim_start = end
        found_after = _act_from_after(after)
        if found_after is not None:
            act, ref_end = found_after
            claim_start = end + ref_end
        else:
            before = text[max(0, m.start() - _BEFORE_WINDOW):m.start()]
            found_before = _act_from_before(before)
            if found_before is not None:
                act = found_before

        claim = _extract_claim(text[claim_start:claim_start + 140])
        raw_end = claim_start if found_after is not None else end
        raw = re.sub(r"\s+", " ", text[m.start():raw_end]).strip().rstrip(",;")

        for i, article in enumerate(articles):
            if len(citations) >= max_citations:
                break
            key = (
                act.get("code_key"), act.get("act_type"), act.get("act_number"),
                act.get("act_year"), article, comma if i == len(articles) - 1 else None,
            )
            if key in seen:
                continue
            seen.add(key)
            citations.append(ParsedCitation(
                raw=raw if len(articles) == 1 else f"art. {article} ({raw})",
                kind="statute",
                article=article,
                comma=comma if i == len(articles) - 1 else None,
                claim=claim if i == 0 else None,
                code_key=act.get("code_key"),          # type: ignore[arg-type]
                act_type=act.get("act_type"),          # type: ignore[arg-type]
                act_number=act.get("act_number"),      # type: ignore[arg-type]
                act_year=act.get("act_year"),          # type: ignore[arg-type]
                act_month=act.get("act_month"),        # type: ignore[arg-type]
                act_day=act.get("act_day"),            # type: ignore[arg-type]
            ))

    for m in _ECLI_RE.finditer(text):
        if len(citations) >= max_citations:
            break
        ecli = m.group(0).upper()
        key = ("ecli", ecli)
        if key in seen:
            continue
        seen.add(key)
        citations.append(ParsedCitation(
            raw=m.group(0), kind="ecli", ecli=ecli, ecli_court=m.group(1).upper(),
        ))

    return citations


# ---------------------------------------------------------------------------
# Content matching (trigram)
# ---------------------------------------------------------------------------

# Warning threshold for the trigram scores. Below it the claimed description is
# flagged as a content mismatch - a signal for review, never a hard block
# (measured for Latin-script legal text in citation-grounding-pl v2.3; the
# Korean original uses bigrams at 0.25 for an agglutinative script).
CONTENT_WARN_THRESHOLD = 0.2


def normalize_text(s: str) -> str:
    """Lowercase, strip accents, drop punctuation, collapse whitespace."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^0-9a-z]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _trigrams(s: str) -> set[str]:
    compact = normalize_text(s).replace(" ", "")
    if len(compact) < 3:
        return {compact} if compact else set()
    return {compact[i:i + 3] for i in range(len(compact) - 2)}


def trigram_jaccard(a: str, b: str) -> float:
    """Symmetric trigram Jaccard - for claim vs heading (comparable lengths)."""
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def trigram_overlap(claim: str, body: str) -> float:
    """Asymmetric overlap - share of claim trigrams found in the (longer) body."""
    tc, tb = _trigrams(claim), _trigrams(body)
    if not tc or not tb:
        return 0.0
    return len(tc & tb) / len(tc)


def match_claim(claim: str, heading: str | None, body: str) -> tuple[bool, str, float]:
    """Score a claimed description against the real provision.

    Returns ``(matched, method, score)``. Layers:
    L1 exact - the normalized claim is a substring of heading+body;
    L2 trigram Jaccard vs the heading (symmetric, comparable lengths);
    L3 trigram overlap vs the body (asymmetric - claim is much shorter).
    """
    reference = f"{heading or ''} {body}".strip()
    c = normalize_text(claim)
    if c and c in normalize_text(reference):
        return True, "exact", 1.0

    score_heading = trigram_jaccard(claim, heading) if heading else 0.0
    score_body = trigram_overlap(claim, body[:1500]) if body else 0.0
    if score_heading >= score_body:
        method, score = "trigram-jaccard", score_heading
    else:
        method, score = "trigram-overlap", score_body
    return score >= CONTENT_WARN_THRESHOLD, method, round(score, 3)


# ---------------------------------------------------------------------------
# Range hint and comma detection
# ---------------------------------------------------------------------------

_NUM_IN_LABEL_RE = re.compile(r"(\d+)")
_COMMA_MARK_RE = re.compile(r"(?:^|[\s(])(\d{1,3})\.\s")


def article_numbers(labels: list[str]) -> list[int]:
    """Leading integers of article labels ('Art. 2043.' -> 2043), sorted, unique."""
    nums: set[int] = set()
    for label in labels:
        m = _NUM_IN_LABEL_RE.search(label)
        if m:
            nums.add(int(m.group(1)))
    return sorted(nums)


def range_hint(labels: list[str], wanted: str) -> str:
    """'art. 9999 does not exist; the act has N articles, numbered art. 1-372'."""
    nums = article_numbers(labels)
    if not nums:
        return f"art. {wanted} not found; the act exposes no numbered articles."
    return (
        f"art. {wanted} does not exist in this act; "
        f"the act has {len(labels)} articles, numbered art. {nums[0]}-{nums[-1]}."
    )


def detect_commi(article_text: str) -> list[int]:
    """Comma (paragraph) numbers detectable in flattened article text.

    Normattiva's consolidated text numbers commi as '1. ...', '2. ...'. The
    flattening is lossy, so callers must treat a miss as a warning, never as
    proof of absence. An empty or implausible sequence returns [] (not checkable).
    """
    nums = sorted({
        int(m.group(1)) for m in _COMMA_MARK_RE.finditer(article_text)
        if 1 <= int(m.group(1)) <= 200
    })
    if len(nums) < 2 or 1 not in nums:
        return []
    return nums
