"""Conversione fedele del testo Telegram (con entità) in HTML.

Telegram esprime gli offset delle entità in unità UTF-16: qui vengono
riconvertiti in indici Python, così emoji e caratteri fuori dal BMP non
sfasano la formattazione.
"""
from __future__ import annotations

import html
import re
from collections import defaultdict

# tipo entità Telegram -> (tag apertura, tag chiusura)
SIMPLE_TAGS = {
    "bold": ("<strong>", "</strong>"),
    "italic": ("<em>", "</em>"),
    "underline": ("<u>", "</u>"),
    "strike": ("<s>", "</s>"),
    "code": ("<code>", "</code>"),
    "pre": ("<pre><code>", "</code></pre>"),
    "blockquote": ("<blockquote>", "</blockquote>"),
    "spoiler": ('<span class="spoiler">', "</span>"),
}

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)


def utf16_to_python_offsets(text: str) -> list[int]:
    """Mappa offset UTF-16 -> indice Python (lunghezza = len(utf16)+1)."""
    mapping = []
    for i, ch in enumerate(text):
        mapping.append(i)
        if ord(ch) > 0xFFFF:  # coppia surrogata: occupa 2 unità UTF-16
            mapping.append(i)
    mapping.append(len(text))
    return mapping


def _open_close(ent: dict) -> tuple[str, str]:
    etype = ent.get("type", "")
    if etype in SIMPLE_TAGS:
        return SIMPLE_TAGS[etype]
    if etype == "text_link":
        url = html.escape(ent.get("url", ""), quote=True)
        return (f'<a href="{url}" rel="noopener nofollow" target="_blank">', "</a>")
    if etype == "url":
        return ("", "")  # gestito dopo, con il testo stesso come href
    if etype == "mention":
        return ("", "")
    return ("", "")


def to_html(text: str, entities: list[dict] | None) -> str:
    """Restituisce l'HTML del messaggio: entità + paragrafi + link nudi."""
    if not text:
        return ""
    entities = entities or []
    mapping = utf16_to_python_offsets(text)
    max_u16 = len(mapping) - 1

    ordered = []
    for ent in entities:
        start = ent.get("offset", 0)
        length = ent.get("length", 0)
        end = start + length
        if length <= 0 or start < 0 or end > max_u16:
            continue
        # ordina per inizio crescente e, a parità, per lunghezza decrescente
        # (le entità più esterne devono aprirsi per prime)
        ordered.append((start, -length, end, ent))
    ordered.sort(key=lambda item: (item[0], item[1]))

    stack: list[tuple[int, str]] = []  # (fine_py, tag_chiusura)
    out: list[str] = []
    by_start: dict[int, list[tuple[int, dict]]] = defaultdict(list)
    for start, _neg_len, end, ent in ordered:
        by_start[mapping[start]].append((mapping[end], ent))

    i = 0
    n = len(text)
    while i <= n:
        while stack and stack[-1][0] <= i:
            out.append(stack.pop()[1])
        jumped = False
        for end_py, ent in by_start.get(i, []):
            etype = ent.get("type")
            if etype in ("url", "mention"):
                raw = text[i:end_py]
                if etype == "url":
                    href = raw if raw.lower().startswith(("http://", "https://")) else "https://" + raw
                else:
                    href = "https://t.me/" + raw.lstrip("@")
                out.append(
                    f'<a href="{html.escape(href, quote=True)}" rel="noopener nofollow" '
                    f'target="_blank">{html.escape(raw)}</a>'
                )
                i = end_py  # il testo del link è già stato emesso
                jumped = True
                break
            open_tag, close_tag = _open_close(ent)
            if open_tag:
                out.append(open_tag)
                stack.append((end_py, close_tag))
        if jumped:
            continue
        if i < n:
            out.append(html.escape(text[i]))
        i += 1
    while stack:
        out.append(stack.pop()[1])

    body = "".join(out)
    return _paragraphs(body)


def _paragraphs(escaped_html: str) -> str:
    """Righe vuote -> paragrafi, singolo a capo -> <br>."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", escaped_html) if b.strip()]
    paragraphs = []
    for block in blocks:
        if block.startswith(("<blockquote", "<pre")):
            paragraphs.append(block.replace("\n", "<br>"))
        else:
            paragraphs.append("<p>" + block.replace("\n", "<br>") + "</p>")
    return "\n".join(paragraphs)


def plain_excerpt(text: str, limit: int = 220) -> str:
    """Estratto testuale pulito per meta description e anteprime."""
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if len(clean) <= limit:
        return clean
    cut = clean[:limit]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut + "…"


def make_title(text: str, fallback: str) -> str:
    """Titolo dell'articolo: prima riga significativa del post."""
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        line = re.sub(r"^[\W_]+", "", line).strip()
        if len(line) >= 3:
            if len(line) > 110:
                cut = line[:110]
                line = cut[: cut.rfind(" ")] if " " in cut else cut
                line += "…"
            return line
    return fallback


_SLUG_RE = re.compile(r"[^a-z0-9]+")
_TRANSLIT = str.maketrans("àáâäãèéêëìíîïòóôöõùúûüçñ", "aaaaaeeeeiiiiooooouuuucn")


def slugify(value: str, max_len: int = 70) -> str:
    value = (value or "").lower().translate(_TRANSLIT)
    value = _SLUG_RE.sub("-", value).strip("-")
    if len(value) > max_len:
        value = value[:max_len].rsplit("-", 1)[0]
    return value or "post"
