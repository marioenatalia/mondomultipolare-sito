"""Generazione del sito statico multilingua a partire dai post archiviati."""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import store
from .config import ROOT, Config
from .entities import make_title, plain_excerpt, slugify, to_html
from .i18n import LINGUE, etichette, formatta_data, formatta_mese, prefisso

TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"

# tag tematici riconosciuti nel testo italiano (l'etichetta è tradotta in i18n)
TEMI = {
    "Medio Oriente": ["israele", "gaza", "iran", "libano", "siria", "yemen", "hamas", "hezbollah"],
    "Ucraina": ["ucraina", "kiev", "kyiv", "zelensky", "donbass", "kherson"],
    "Russia": ["russia", "mosca", "putin", "cremlino"],
    "Cina": ["cina", "pechino", "taiwan", "xi jinping"],
    "USA": ["stati uniti", "washington", "casa bianca", "pentagono", "usa "],
    "Europa": ["ue ", "unione europea", "bruxelles", "nato", "germania", "francia"],
    "Africa": ["africa", "sahel", "niger", "sudan", "libia", "etiopia"],
    "Economia": ["mercati", "petrolio", "gas", "inflazione", "dazi", "sanzioni", "pil"],
}

TEMI_TRADOTTI = {
    "Medio Oriente": {"en": "Middle East", "ru": "Ближний Восток", "zh": "中东",
                      "es": "Oriente Medio", "fr": "Moyen-Orient", "de": "Naher Osten"},
    "Ucraina": {"en": "Ukraine", "ru": "Украина", "zh": "乌克兰",
                "es": "Ucrania", "fr": "Ukraine", "de": "Ukraine"},
    "Russia": {"en": "Russia", "ru": "Россия", "zh": "俄罗斯",
               "es": "Rusia", "fr": "Russie", "de": "Russland"},
    "Cina": {"en": "China", "ru": "Китай", "zh": "中国",
             "es": "China", "fr": "Chine", "de": "China"},
    "USA": {"en": "USA", "ru": "США", "zh": "美国", "es": "EE. UU.", "fr": "États-Unis", "de": "USA"},
    "Europa": {"en": "Europe", "ru": "Европа", "zh": "欧洲",
               "es": "Europa", "fr": "Europe", "de": "Europa"},
    "Africa": {"en": "Africa", "ru": "Африка", "zh": "非洲",
               "es": "África", "fr": "Afrique", "de": "Afrika"},
    "Economia": {"en": "Economy", "ru": "Экономика", "zh": "经济",
                 "es": "Economía", "fr": "Économie", "de": "Wirtschaft"},
}


def _reading_time(text: str) -> int:
    words = len(re.findall(r"\w+", text or ""))
    return max(1, round(words / 200))


def _temi(text: str) -> list[str]:
    low = (text or "").lower()
    return [nome for nome, chiavi in TEMI.items() if any(k in low for k in chiavi)][:3]


def tema_tradotto(tema: str, lang: str) -> str:
    if lang == "it":
        return tema
    return TEMI_TRADOTTI.get(tema, {}).get(lang, tema)


def _group_rows(rows: list[sqlite3.Row]) -> list[list[sqlite3.Row]]:
    """Unisce gli album (più media, un solo post) in un unico articolo."""
    groups: list[list[sqlite3.Row]] = []
    index: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        gid = row["grouped_id"]
        if gid and gid in index:
            index[gid].append(row)
            continue
        bucket = [row]
        groups.append(bucket)
        if gid:
            index[gid] = bucket
    return groups


def _fonti_dal_testo(entities: list[dict], text: str, canale_proprio: str) -> list[dict]:
    """Link esterni citati nel post: diventano l'elenco delle fonti."""
    fonti, visti = [], set()
    unita = _utf16_units(text)
    for ent in entities:
        url = ""
        if ent.get("type") == "text_link":
            url = ent.get("url", "")
        elif ent.get("type") == "url":
            inizio, fine = ent.get("offset", 0), ent.get("offset", 0) + ent.get("length", 0)
            url = "".join(unita[inizio:fine])
            if not url.lower().startswith("http"):
                url = "https://" + url
        if not url:
            continue
        dominio = (urlparse(url).netloc or "").replace("www.", "")
        if not dominio or dominio in visti:
            continue
        # i link al proprio canale non sono una fonte esterna
        if canale_proprio and canale_proprio.lower().lstrip("@") in url.lower():
            continue
        visti.add(dominio)
        fonti.append({"url": url, "dominio": dominio})
    return fonti


def _utf16_units(text: str) -> list[str]:
    unita = []
    for ch in text:
        if ord(ch) > 0xFFFF:
            grezzo = ch.encode("utf-16-le")
            unita.append(grezzo[:2].decode("utf-16-le", "surrogatepass"))
            unita.append(grezzo[2:].decode("utf-16-le", "surrogatepass"))
        else:
            unita.append(ch)
    return unita


def _riconosci_fonte(provenienza: dict | None, fonti: list[dict], cfg: Config) -> tuple[dict | None, list[dict]]:
    """Abbina la provenienza a una testata partner e sceglie l'etichetta del credito.

    Ritorna (credito, fonti ripulite): la testata accreditata non viene ripetuta
    nell'elenco delle fonti citate.
    """
    sezione = cfg.get("fonti") or {}
    partner = sezione.get("partner") or []
    predefinita = sezione.get("etichetta_predefinita") or "ripreso_da"

    def componi(p: dict, base: dict | None, articolo_url: str | None = None) -> dict:
        credito = dict(base or {})
        credito["nome"] = p.get("nome") or credito.get("nome")
        if p.get("sito"):
            credito["sito_url"] = p["sito"]
        if articolo_url:
            credito["articolo_url"] = articolo_url
        credito["etichetta"] = p.get("etichetta") or predefinita
        return credito

    # 1) repost da un canale Telegram riconosciuto
    if provenienza:
        canale = (provenienza.get("canale_url") or "").lower()
        nome_prov = (provenienza.get("nome") or "").strip().lower()
        for p in partner:
            tg = (p.get("telegram") or "").lstrip("@").lower()
            nome = (p.get("nome") or "").strip().lower()
            if (tg and tg in canale) or (nome and nome == nome_prov):
                return componi(p, provenienza), fonti

    # 2) nessun repost, ma il testo linka il sito della testata
    for p in partner:
        dominio = (urlparse(p.get("sito") or "").netloc or "").replace("www.", "").lower()
        if not dominio:
            continue
        corrispondenti = [f for f in fonti if f["dominio"].lower() == dominio]
        if corrispondenti:
            restanti = [f for f in fonti if f["dominio"].lower() != dominio]
            return componi(p, provenienza, corrispondenti[0]["url"]), restanti

    if provenienza:
        credito = dict(provenienza)
        credito.setdefault("etichetta", predefinita)
        return credito, fonti
    return None, fonti


def _apertura(media: list[dict]) -> dict | None:
    """Immagine di apertura: la prima foto oppure l'anteprima del primo video."""
    foto = next((m for m in media if m["kind"] == "photo"), None)
    if foto:
        return foto
    video = next((m for m in media if m["kind"] == "video" and m.get("poster")), None)
    if video:
        return {
            "kind": "poster",
            "path": video["poster"],
            "thumb": video.get("poster_min") or video["poster"],
            "video": video["path"],
        }
    return None


def _slug_articolo(titolo: str, mid: int, lang: str) -> str:
    base = slugify(titolo)
    if lang == "zh" or not base or base == "post":
        base = f"articolo-{mid}" if lang != "zh" else f"wenzhang-{mid}"
    return base


def build_posts(rows: list[sqlite3.Row], cfg: Config) -> list[dict]:
    """Costruisce gli articoli in italiano (la lingua sorgente)."""
    canale = (cfg["telegram"].get("channel") or "").lstrip("@")
    posts = []
    for bucket in _group_rows(rows):
        main = max(bucket, key=lambda r: len(r["text"] or ""))
        media: list[dict] = []
        for row in sorted(bucket, key=lambda r: r["message_id"]):
            media.extend([m for m in json.loads(row["media"] or "[]") if not m.get("skipped")])

        dt = datetime.fromisoformat(main["date_utc"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        text = main["text"] or ""
        entities = json.loads(main["entities"] or "[]")
        titolo = make_title(text, f"Aggiornamento del {formatta_data(dt, 'it')}")

        body_html = to_html(text, entities)
        titolo_pulito = titolo.rstrip("…").strip()
        prima_riga = text.strip().splitlines()[0] if text.strip() else ""
        resto_testo = text.split("\n", 1)[1].strip() if "\n" in text else ""

        # la prima riga diventa il titolo solo se sotto resta un articolo:
        # i post brevi del canale restano interi nel corpo
        usa_come_titolo = (
            prima_riga
            and prima_riga.strip()[:50] == titolo_pulito[:50]
            and len(resto_testo) >= 120
        )
        if usa_come_titolo:
            first_par = re.match(r"<p>(.*?)</p>", body_html, re.S)
            if first_par and re.sub(r"<[^>]+>", "", first_par.group(1)).strip()[:50] == titolo_pulito[:50]:
                body_html = body_html[first_par.end() :].lstrip()
            corpo_testo = resto_testo
        else:
            corpo_testo = text

        try:
            provenienza = json.loads(main["forward_json"] or "null") if "forward_json" in main.keys() else None
        except (json.JSONDecodeError, TypeError):
            provenienza = None
        if not provenienza and main["forward_from"]:
            provenienza = {"nome": main["forward_from"]}

        fonti = _fonti_dal_testo(entities, text, canale)
        credito, fonti = _riconosci_fonte(provenienza, fonti, cfg)

        posts.append(
            {
                "id": main["message_id"],
                "title": titolo,
                "date": dt,
                "iso": dt.isoformat(),
                "rfc822": format_datetime(dt),
                "time_it": dt.strftime("%H:%M"),
                "html": body_html,
                "excerpt": plain_excerpt(corpo_testo or text),
                "occhiello": plain_excerpt(corpo_testo or text, 180)
                if len((corpo_testo or "").strip()) > 320
                else "",
                "text": text,
                "media": media,
                "cover": _apertura(media),
                "apertura_video": next(
                    (m for m in media if m["kind"] == "video" and m.get("poster")), None
                ) if not any(m["kind"] == "photo" for m in media) else None,
                "views": main["views"],
                "source": main["link"],
                "provenienza": credito,
                "fonti": fonti,
                "reading_time": _reading_time(text),
                "temi_it": _temi(text),
            }
        )
    posts.sort(key=lambda p: (p["date"], p["id"]), reverse=True)
    return posts


def _versione_lingua(post: dict, lang: str, traduzione: sqlite3.Row | None, base: str) -> dict | None:
    """Adatta un articolo a una lingua: testo tradotto, slug, indirizzi."""
    if lang != base and traduzione is None:
        return None

    titolo = post["title"] if lang == base else traduzione["title"]
    html = post["html"] if lang == base else traduzione["html"]
    estratto = post["excerpt"] if lang == base else (traduzione["excerpt"] or "")

    slug = f"{post['date'].strftime('%Y/%m/%d')}/{_slug_articolo(titolo, post['id'], lang)}-{post['id']}"
    pre = prefisso(lang, base)
    copia = dict(post)
    copia.update(
        {
            "title": titolo,
            "html": html,
            "excerpt": estratto,
            "occhiello": estratto if lang != base and len(estratto) > 150 else post["occhiello"] if lang == base else "",
            "slug": slug,
            "url": f"{pre}/post/{slug}/",
            "date_it": formatta_data(post["date"], lang),
            "mese_it": formatta_mese(post["date"], lang),
            "temi": [tema_tradotto(t, lang) for t in post["temi_it"]],
            "lang": lang,
        }
    )
    return copia


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


def build_site(cfg: Config, conn: sqlite3.Connection | None = None) -> dict:
    own_conn = conn is None
    conn = conn or store.connect(cfg)
    base = cfg["lingue"]["sorgente"]
    lingue = [l for l in cfg["lingue"]["attive"] if l in LINGUE]
    if base not in lingue:
        lingue.insert(0, base)

    posts_base = build_posts(store.published_posts(conn), cfg)

    # articoli per lingua + mappa degli equivalenti (per hreflang e selettore lingua)
    per_lingua: dict[str, list[dict]] = {}
    alternative: dict[int, dict[str, str]] = {}
    for lang in lingue:
        traduzioni = {} if lang == base else store.traduzioni_per_lingua(conn, lang)
        elenco = []
        for post in posts_base:
            versione = _versione_lingua(post, lang, traduzioni.get(post["id"]), base)
            if versione:
                elenco.append(versione)
                alternative.setdefault(post["id"], {})[lang] = versione["url"]
        per_lingua[lang] = elenco

    out = cfg.output_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "assets").mkdir(parents=True, exist_ok=True)
    for asset in STATIC.glob("*"):
        if asset.is_file():
            shutil.copy2(asset, out / "assets" / asset.name)

    env = _env()
    # la data mostrata in testata segue l'ultimo post, non l'orologio: così le
    # pagine non cambiano a ogni esecuzione e la pubblicazione resta leggera
    adesso = posts_base[0]["date"] if posts_base else datetime.now(timezone.utc)
    totale_pagine = 0

    for lang in lingue:
        posts = per_lingua[lang]
        for post in posts:
            post["alternative"] = alternative.get(post["id"], {})
            post["originale_url"] = alternative.get(post["id"], {}).get(base, "/")
        t = etichette(lang)
        pre = prefisso(lang, base)
        cartella = out if lang == base else out / lang
        cartella.mkdir(parents=True, exist_ok=True)

        site = dict(cfg["site"])
        site["base_url"] = site["base_url"].rstrip("/")
        site["lang"] = lang
        site["html_lang"] = t["html_lang"]
        site["prefisso"] = pre
        site["tagline"] = (cfg["site"].get("tagline_per_lingua") or {}).get(lang) or t["tagline"]
        site["footer"] = (cfg["site"].get("footer_per_lingua") or {}).get(lang) or t["footer"]
        site["updated_it"] = formatta_data(adesso, lang)
        site["updated_iso"] = adesso.isoformat(timespec="seconds")
        site["anno"] = adesso.year
        site["lingue"] = [
            {"codice": c, "nome": LINGUE[c]["nome"], "url": f"{prefisso(c, base)}/"} for c in lingue
        ]

        per_page = max(1, int(site.get("posts_per_page", 12)))
        pagine = [posts[i : i + per_page] for i in range(0, len(posts), per_page)] or [[]]
        totale_pagine += len(pagine)

        index_tpl = env.get_template("index.html")
        for numero, blocco in enumerate(pagine, start=1):
            html = index_tpl.render(
                site=site, t=t, posts=blocco, page=numero, pages=len(pagine),
                latest=posts[:8], temi=sorted({x for p in posts for x in p["temi"]}),
            )
            destinazione = cartella / "index.html" if numero == 1 else cartella / "pagina" / str(numero) / "index.html"
            destinazione.parent.mkdir(parents=True, exist_ok=True)
            destinazione.write_text(html, encoding="utf-8")

        post_tpl = env.get_template("post.html")
        for i, post in enumerate(posts):
            correlati = [p for p in posts if p["id"] != post["id"] and set(p["temi"]) & set(post["temi"])][:3]
            html = post_tpl.render(
                site=site, t=t, post=post,
                prev=posts[i + 1] if i + 1 < len(posts) else None,
                next=posts[i - 1] if i > 0 else None,
                correlati=correlati or [p for p in posts if p["id"] != post["id"]][:3],
            )
            destinazione = cartella / "post" / post["slug"] / "index.html"
            destinazione.parent.mkdir(parents=True, exist_ok=True)
            destinazione.write_text(html, encoding="utf-8")

        (cartella / "feed.xml").write_text(
            env.get_template("feed.xml").render(site=site, t=t, posts=posts[:40]), encoding="utf-8"
        )
        (cartella / "archivio.html").write_text(
            env.get_template("archivio.html").render(site=site, t=t, posts=posts), encoding="utf-8"
        )
        (cartella / "404.html").write_text(
            env.get_template("404.html").render(site=site, t=t), encoding="utf-8"
        )
        (cartella / "cerca.html").write_text(
            env.get_template("cerca.html").render(
                site=site, t=t, temi=sorted({x for p in posts for x in p["temi"]})
            ),
            encoding="utf-8",
        )
        (cartella / "ricerca.json").write_text(
            json.dumps(
                [{"t": p["title"], "u": p["url"], "d": p["date_it"], "x": p["excerpt"],
                  "g": p["temi"], "i": p["cover"]["thumb"] if p["cover"] and p["cover"].get("thumb")
                  else (p["cover"]["path"] if p["cover"] else "")}
                 for p in posts],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    site_radice = dict(cfg["site"])
    site_radice["base_url"] = site_radice["base_url"].rstrip("/")
    (out / "sitemap.xml").write_text(
        env.get_template("sitemap.xml").render(
            site=site_radice,
            lingue=lingue,
            pagine=[{"url": f"{prefisso(l, base)}/", "lastmod": adesso.isoformat(timespec="seconds")} for l in lingue],
            posts=[{"url": p["url"], "iso": p["iso"], "alternative": p.get("alternative", {})}
                   for lang in lingue for p in per_lingua[lang]],
        ),
        encoding="utf-8",
    )
    # configurazione del server web: precedenza a index.html, cache, 404
    (out / ".htaccess").write_text(
        (TEMPLATES / "htaccess.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (out / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {site_radice['base_url']}/sitemap.xml\n", encoding="utf-8"
    )

    if own_conn:
        conn.close()
    return {
        "posts": len(posts_base),
        "lingue": {l: len(per_lingua[l]) for l in lingue},
        "pagine": totale_pagine,
        "output": str(out),
    }
