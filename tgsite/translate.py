"""Traduzione automatica degli articoli con l'API di Claude.

Il testo viene tradotto in HTML: grassetti, corsivi e link restano dove sono.
Ogni traduzione viene salvata nel database e rifatta solo se il post italiano
cambia, quindi non si paga due volte lo stesso articolo.
"""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from . import store
from .config import Config
from .i18n import LINGUE, NOMI_IT

API_URL = "https://api.anthropic.com/v1/messages"
VERSIONE_API = "2023-06-01"

# se il modello indicato in config.yaml non esiste più, si prova questi in ordine
MODELLI_RIPIEGO = [
    "claude-sonnet-4-5",
    "claude-sonnet-4-0",
    "claude-3-7-sonnet-latest",
    "claude-3-5-sonnet-latest",
]

ISTRUZIONI = """Sei un traduttore professionista di una testata giornalistica internazionale \
specializzata in geopolitica. Traduci dall'italiano verso {lingua} ({codice}).

Regole tassative:
- Rendi il testo come lo scriverebbe un giornalista madrelingua: registro sobrio, \
asciutto, da agenzia di stampa. Non aggiungere, non togliere, non commentare.
- Conserva ESATTAMENTE i tag HTML presenti (<p>, <strong>, <em>, <a href="...">, <blockquote>, \
<br>, <u>, <s>, <code>): stessa struttura, stessi attributi, stessi URL. Traduci solo il testo \
tra i tag.
- Nomi propri di persone, istituzioni, testate e canali restano nella forma corrente nella \
lingua di destinazione (per il cinese e il russo usa la traslitterazione consolidata).
- Numeri, date, valute, unità di misura e sigle restano fedeli all'originale.
- Non tradurre il nome della testata "Mondo Multipolare".
- Se il testo contiene una citazione di fonte (per esempio "Fonte: ..."), traduci l'etichetta \
ma lascia intatto il nome della fonte.

Rispondi SOLO con un oggetto JSON valido, senza testo prima o dopo:
{{"titolo": "...", "html": "..."}}
dove "titolo" è il titolo tradotto e "html" è il corpo tradotto con i suoi tag."""


def _chiave() -> str:
    chiave = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not chiave:
        raise SystemExit(
            "Manca la chiave per la traduzione.\n"
            "Aggiungi ANTHROPIC_API_KEY nel file .env (la ottieni su console.anthropic.com)."
        )
    return chiave


def _firma(titolo: str, html: str) -> str:
    return hashlib.sha1((titolo + "\x00" + html).encode("utf-8")).hexdigest()


def _chiama_api(modello: str, sistema: str, contenuto: str, max_token: int) -> str:
    corpo = json.dumps(
        {
            "model": modello,
            "max_tokens": max_token,
            "system": sistema,
            "messages": [{"role": "user", "content": contenuto}],
        }
    ).encode("utf-8")
    richiesta = urllib.request.Request(
        API_URL,
        data=corpo,
        headers={
            "content-type": "application/json",
            "x-api-key": _chiave(),
            "anthropic-version": VERSIONE_API,
        },
    )
    with urllib.request.urlopen(richiesta, timeout=180) as risposta:
        dati = json.loads(risposta.read().decode("utf-8"))
    parti = [b.get("text", "") for b in dati.get("content", []) if b.get("type") == "text"]
    return "".join(parti).strip()


def _estrai_json(testo: str) -> dict:
    """Il modello risponde in JSON; questa funzione tollera eventuali fronzoli."""
    testo = testo.strip()
    if testo.startswith("```"):
        testo = re.sub(r"^```[a-z]*\n?", "", testo)
        testo = re.sub(r"\n?```$", "", testo).strip()
    try:
        return json.loads(testo)
    except json.JSONDecodeError:
        inizio, fine = testo.find("{"), testo.rfind("}")
        if inizio >= 0 and fine > inizio:
            return json.loads(testo[inizio : fine + 1])
        raise


def traduci(titolo: str, html: str, lang: str, modello: str, tentativi: int = 3) -> dict:
    sistema = ISTRUZIONI.format(lingua=LINGUE[lang]["nome"], codice=lang)
    contenuto = json.dumps({"titolo": titolo, "html": html}, ensure_ascii=False)
    max_token = min(8000, 1200 + len(html) // 2)

    modelli = [modello] + [m for m in MODELLI_RIPIEGO if m != modello]
    ultimo_errore: Exception | None = None

    for candidato in modelli:
        for tentativo in range(tentativi):
            try:
                risposta = _chiama_api(candidato, sistema, contenuto, max_token)
                dati = _estrai_json(risposta)
                if not dati.get("html"):
                    raise ValueError("risposta senza corpo tradotto")
                dati["modello"] = candidato
                return dati
            except urllib.error.HTTPError as exc:
                corpo = exc.read().decode("utf-8", "ignore")[:300]
                ultimo_errore = RuntimeError(f"HTTP {exc.code}: {corpo}")
                if exc.code in (404, 400) and "model" in corpo.lower():
                    break  # modello inesistente: passa al successivo
                if exc.code in (429, 500, 502, 503, 529):
                    time.sleep(2 ** tentativo * 3)
                    continue
                raise SystemExit(f"Errore dall'API di traduzione: {ultimo_errore}")
            except Exception as exc:  # rete instabile, JSON malformato
                ultimo_errore = exc
                time.sleep(2 ** tentativo)
    raise SystemExit(f"Traduzione non riuscita: {ultimo_errore}")


def _traduzione_simulata(titolo: str, html: str, lang: str) -> dict:
    """Solo per le prove senza chiave API: marca il testo con la lingua."""
    sigla = lang.upper()
    return {
        "titolo": f"[{sigla}] {titolo}",
        "html": re.sub(r"<p>", f"<p>[{sigla}] ", html, count=1),
        "modello": "simulato",
    }


def traduci_articoli(cfg: Config, conn=None, simulato: bool = False, solo: list[str] | None = None) -> dict:
    """Traduce tutti gli articoli pubblicati non ancora tradotti (o cambiati)."""
    from .build import build_posts  # import qui per evitare cicli

    proprio = conn is None
    conn = conn or store.connect(cfg)
    lingue = solo or [l for l in (cfg["lingue"]["attive"] or []) if l != cfg["lingue"]["sorgente"]]
    modello = cfg["lingue"].get("modello") or MODELLI_RIPIEGO[0]

    if not simulato and not os.getenv("ANTHROPIC_API_KEY", "").strip():
        print("  traduzioni saltate: manca ANTHROPIC_API_KEY nel file .env")
        if proprio:
            conn.close()
        return {"tradotte": 0, "saltate": 0, "errori": 0, "senza_chiave": True}

    posts = build_posts(store.published_posts(conn), cfg)
    fatte, saltate, errori = 0, 0, 0

    for lang in lingue:
        if lang not in LINGUE:
            print(f"  ! lingua sconosciuta, la salto: {lang}")
            continue
        da_fare = []
        for post in posts:
            firma = _firma(post["title"], post["html"])
            esistente = store.traduzione(conn, post["id"], lang)
            if esistente and esistente["source_hash"] == firma:
                saltate += 1
                continue
            da_fare.append((post, firma))

        if not da_fare:
            print(f"  {NOMI_IT.get(lang, lang)}: già aggiornato")
            continue

        print(f"  {NOMI_IT.get(lang, lang)}: {len(da_fare)} articoli da tradurre…")
        for post, firma in da_fare:
            try:
                if simulato:
                    esito = _traduzione_simulata(post["title"], post["html"], lang)
                else:
                    esito = traduci(post["title"], post["html"], lang, modello)
            except SystemExit:
                raise
            except Exception as exc:
                print(f"    ! articolo #{post['id']} non tradotto: {exc}")
                errori += 1
                continue

            testo_semplice = re.sub(r"<[^>]+>", " ", esito["html"])
            testo_semplice = html_lib.unescape(testo_semplice)
            testo_semplice = re.sub(r"\s+", " ", testo_semplice).strip()
            store.salva_traduzione(
                conn,
                {
                    "message_id": post["id"],
                    "lang": lang,
                    "source_hash": firma,
                    "title": esito.get("titolo") or post["title"],
                    "html": esito["html"],
                    "excerpt": testo_semplice[:220],
                    "engine": f"claude:{esito.get('modello','')}",
                    "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                },
            )
            fatte += 1
            if fatte % 10 == 0:
                conn.commit()
        conn.commit()

    conn.commit()
    if proprio:
        conn.close()
    print(f"Traduzioni: {fatte} nuove, {saltate} già presenti, {errori} errori.")
    return {"tradotte": fatte, "saltate": saltate, "errori": errori}
