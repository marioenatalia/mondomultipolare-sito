"""Lettura dei post dal canale Telegram (Telethon) e salvataggio in SQLite."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl import types

from . import store
from .media import ottimizza
from .config import Config, telegram_credentials

# classe entità Telethon -> nome usato nel database
ENTITY_TYPES = {
    types.MessageEntityBold: "bold",
    types.MessageEntityItalic: "italic",
    types.MessageEntityUnderline: "underline",
    types.MessageEntityStrike: "strike",
    types.MessageEntityCode: "code",
    types.MessageEntityPre: "pre",
    types.MessageEntityBlockquote: "blockquote",
    types.MessageEntitySpoiler: "spoiler",
    types.MessageEntityTextUrl: "text_link",
    types.MessageEntityUrl: "url",
    types.MessageEntityMention: "mention",
    types.MessageEntityHashtag: "hashtag",
}


def _parametri_avvio(creds: dict) -> dict:
    """Parametri per client.start(): la password si passa solo se configurata,
    altrimenti Telethon la chiede a video (passarla vuota disattiva la richiesta)."""
    avvio = {"phone": creds["phone"]}
    if creds.get("password"):
        avvio["password"] = creds["password"]
    return avvio


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def serialize_entities(entities) -> list[dict]:
    out = []
    for ent in entities or []:
        name = ENTITY_TYPES.get(type(ent))
        if not name:
            continue
        item = {"type": name, "offset": ent.offset, "length": ent.length}
        if name == "text_link":
            item["url"] = getattr(ent, "url", "")
        out.append(item)
    return out


def _media_kind(message) -> str | None:
    if message.photo:
        return "photo"
    if message.video or message.video_note:
        return "video"
    if message.audio or message.voice:
        return "audio"
    if message.document:
        return "document"
    return None


async def _save_media(client, message, cfg: Config) -> list[dict]:
    """Scarica il media del messaggio e ritorna i metadati per il sito."""
    kind = _media_kind(message)
    if not kind or not cfg["telegram"]["download_media"]:
        return []

    max_mb = cfg["telegram"].get("max_media_mb") or 0
    size = getattr(getattr(message, "file", None), "size", 0) or 0
    if max_mb and size > max_mb * 1024 * 1024:
        return [{"kind": kind, "skipped": True, "reason": f"file > {max_mb} MB"}]

    ext = (getattr(getattr(message, "file", None), "ext", None) or "").lstrip(".")
    if not ext:
        ext = {"photo": "jpg", "video": "mp4", "audio": "ogg"}.get(kind, "bin")
    folder = cfg.media_dir / message.date.strftime("%Y/%m")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{message.id}.{ext}"

    if not target.exists():
        try:
            await client.download_media(message, file=str(target))
        except Exception as exc:  # un media rotto non deve fermare l'ingest
            print(f"  ! media non scaricato per il post {message.id}: {exc}")
            return [{"kind": kind, "skipped": True, "reason": str(exc)}]

    def relativo(percorso) -> str:
        rel = percorso.relative_to(cfg.output_dir) if cfg.media_dir.is_relative_to(cfg.output_dir) else percorso
        return str(rel).replace("\\", "/")

    voce = {
        "kind": kind,
        "path": relativo(target),
        "mime": getattr(getattr(message, "file", None), "mime_type", "") or "",
        "size": size,
    }
    if kind == "video":
        # Telegram fornisce una miniatura del video: diventa il poster del lettore
        # e l'immagine dell'articolo nelle liste
        poster = folder / f"{message.id}-poster.jpg"
        if not poster.exists():
            try:
                await client.download_media(message, file=str(poster), thumb=-1)
            except Exception:
                pass
        if poster.exists():
            esito = ottimizza(poster, cfg.get("media") or {})
            voce["poster"] = relativo(poster)
            if esito:
                voce["poster_min"] = relativo(esito["miniatura"])

    if kind == "photo":
        esito = ottimizza(target, cfg.get("media") or {})
        if esito:
            voce["path"] = relativo(target)
            voce["thumb"] = relativo(esito["miniatura"])
            voce["larghezza"] = esito.get("larghezza")
            voce["altezza"] = esito.get("altezza")
            voce["size"] = esito.get("peso", size)
    return [voce]


def _provenienza(message) -> dict | None:
    """Da dove arriva un repost: canale, autore, link al messaggio originale."""
    fwd = getattr(message, "forward", None)
    if not fwd:
        return None

    nome = username = None
    chat = getattr(fwd, "chat", None)
    if chat is not None:
        nome = getattr(chat, "title", None)
        username = getattr(chat, "username", None)
    if not nome:
        mittente = getattr(fwd, "sender", None)
        if mittente is not None:
            nome = " ".join(
                p for p in [getattr(mittente, "first_name", None), getattr(mittente, "last_name", None)] if p
            ) or getattr(mittente, "username", None)
            username = username or getattr(mittente, "username", None)
    nome = nome or getattr(fwd, "from_name", None)
    if not nome:
        return None

    dati: dict = {"nome": nome}
    post_id = getattr(fwd, "channel_post", None)
    if username:
        dati["canale_url"] = f"https://t.me/{username}"
        if post_id:
            dati["post_url"] = f"https://t.me/{username}/{post_id}"
    autore = getattr(fwd, "post_author", None)
    if autore:
        dati["autore"] = autore
    quando = getattr(fwd, "date", None)
    if quando:
        dati["data"] = quando.astimezone(timezone.utc).isoformat(timespec="seconds")
    return dati


def _post_link(channel_username: str | None, chat_id: int, message_id: int) -> str:
    if channel_username:
        return f"https://t.me/{channel_username}/{message_id}"
    short = str(chat_id).replace("-100", "", 1)
    return f"https://t.me/c/{short}/{message_id}"


def _decide_status(text: str, cfg: Config) -> str | None:
    """None = il post viene ignorato del tutto."""
    pub = cfg["publishing"]
    lowered = (text or "").lower()
    if pub.get("min_length") and len(lowered.strip()) < int(pub["min_length"]):
        return None
    block = [w.lower() for w in (pub.get("blocklist") or [])]
    if any(word in lowered for word in block):
        return None
    allow = [w.lower() for w in (pub.get("allowlist") or [])]
    if allow and not any(word in lowered for word in allow):
        return None
    return "draft" if pub.get("mode") == "draft" else "published"


async def _store_message(client, conn, message, cfg: Config, username: str | None) -> str | None:
    text = message.message or ""
    status = _decide_status(text, cfg)
    if status is None and not message.media:
        return None
    if status is None:
        return None

    media = await _save_media(client, message, cfg)
    provenienza = _provenienza(message)

    post = {
        "message_id": message.id,
        "grouped_id": message.grouped_id,
        "date_utc": message.date.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "edit_date": message.edit_date.astimezone(timezone.utc).isoformat(timespec="seconds")
        if message.edit_date
        else None,
        "text": text,
        "entities": serialize_entities(message.entities),
        "media": media,
        "views": message.views or 0,
        "forward_from": (provenienza or {}).get("nome"),
        "provenienza": provenienza,
        "link": _post_link(username, message.chat_id, message.id),
        "status": status,
        "fetched_at": _now(),
    }
    return store.upsert_post(conn, post)


async def run_ingest(cfg: Config, watch: bool = False, limit: int | None = None,
                     giorni: int | None = None) -> dict:
    creds = telegram_credentials()
    channel = cfg["telegram"]["channel"]
    if not channel:
        raise SystemExit("Imposta 'telegram.channel' in config.yaml")

    conn = store.connect(cfg)
    stats = {"new": 0, "updated": 0, "unchanged": 0}

    # in cloud (es. GitHub Actions) si usa una sessione "stringa" salvata nei segreti
    sessione = StringSession(creds["session_string"]) if creds["session_string"] else creds["session"]
    client = TelegramClient(sessione, creds["api_id"], creds["api_hash"])
    await client.start(**_parametri_avvio(creds))
    entity = await client.get_entity(channel)
    username = getattr(entity, "username", None)
    print(f"Canale collegato: {getattr(entity, 'title', channel)}")

    from datetime import timedelta

    limite_data = None
    if giorni:
        # "ieri e oggi" = giorni 2: si parte da mezzanotte di N-1 giorni fa
        oggi = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        limite_data = oggi - timedelta(days=max(0, giorni - 1))
        kwargs = {"limit": None}
        print(f"Recupero i post pubblicati dal {limite_data.strftime('%d/%m/%Y')} in poi…")

    last_id = int(store.get_state(conn, "last_message_id", 0) or 0)
    if limite_data is not None:
        pass
    elif last_id:
        kwargs = {"min_id": last_id, "reverse": True}
        print(f"Recupero i post successivi al #{last_id}…")
    else:
        take = limit if limit is not None else int(cfg["telegram"]["backfill_limit"] or 0)
        kwargs = {"limit": take or None} if take else {"limit": 0}
        print(f"Primo avvio: recupero fino a {take} post storici…")

    max_seen = last_id
    async for message in client.iter_messages(entity, **kwargs):
        if limite_data is not None and message.date.astimezone(timezone.utc) < limite_data:
            break  # i messaggi arrivano dal più recente: qui siamo già oltre
        result = await _store_message(client, conn, message, cfg, username)
        if result:
            stats[result] = stats.get(result, 0) + 1
        max_seen = max(max_seen, message.id)
        if stats["new"] and stats["new"] % 25 == 0:
            conn.commit()

    if max_seen:
        store.set_state(conn, "last_message_id", max_seen)
    store.set_state(conn, "last_run", _now())
    conn.commit()
    print(f"Ingest completato: {stats['new']} nuovi, {stats['updated']} aggiornati.")

    if watch:
        print("In ascolto sui nuovi post del canale (Ctrl+C per fermare)…")
        from .build import build_site

        @client.on(events.NewMessage(chats=entity))
        @client.on(events.MessageEdited(chats=entity))
        async def _handler(event):
            result = await _store_message(client, conn, event.message, cfg, username)
            if result in ("new", "updated"):
                store.set_state(conn, "last_message_id", max(event.message.id, int(store.get_state(conn, "last_message_id", 0) or 0)))
                conn.commit()
                build_site(cfg, conn=conn)
                print(f"  → post #{event.message.id} {result}, sito rigenerato")

        await client.run_until_disconnected()

    await client.disconnect()
    conn.close()
    return stats


def ingest(cfg: Config, watch: bool = False, limit: int | None = None,
           giorni: int | None = None) -> dict:
    return asyncio.run(run_ingest(cfg, watch=watch, limit=limit, giorni=giorni))


async def _esporta_sessione() -> str:
    """Login interattivo che restituisce una sessione portabile (per il cloud)."""
    creds = telegram_credentials()
    async with TelegramClient(StringSession(), creds["api_id"], creds["api_hash"]) as client:
        await client.start(**_parametri_avvio(creds))
        return client.session.save()


def esporta_sessione() -> str:
    return asyncio.run(_esporta_sessione())


async def _scarica_logo(cfg: Config) -> str | None:
    """Scarica l'immagine del canale e ne ricava logo e icone del sito."""
    from PIL import Image, ImageOps

    creds = telegram_credentials()
    sessione = StringSession(creds["session_string"]) if creds["session_string"] else creds["session"]
    client = TelegramClient(sessione, creds["api_id"], creds["api_hash"])
    await client.start(**_parametri_avvio(creds))
    entity = await client.get_entity(cfg["telegram"]["channel"])

    cartella = cfg.output_dir / "assets"
    cartella.mkdir(parents=True, exist_ok=True)
    grezza = cartella / "canale.jpg"
    percorso = await client.download_profile_photo(entity, file=str(grezza))
    await client.disconnect()
    if not percorso:
        print("Il canale non ha un'immagine del profilo visibile.")
        return None

    with Image.open(grezza) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        lato = min(img.size)
        quadrata = ImageOps.fit(img, (lato, lato), Image.LANCZOS)
        quadrata.resize((512, 512), Image.LANCZOS).save(cartella / "logo.jpg", quality=88, optimize=True)
        quadrata.resize((180, 180), Image.LANCZOS).save(cartella / "apple-touch-icon.png")
        quadrata.resize((32, 32), Image.LANCZOS).save(cartella / "favicon-32.png")
        quadrata.resize((16, 16), Image.LANCZOS).save(cartella / "favicon-16.png")
    grezza.unlink(missing_ok=True)
    print(f"Logo del canale salvato in {cartella / 'logo.jpg'} (con icone del sito)")
    return "assets/logo.jpg"


def scarica_logo(cfg: Config) -> str | None:
    return asyncio.run(_scarica_logo(cfg))
