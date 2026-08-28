"""Archivio dei post: funziona su SQLite (locale) o su PostgreSQL (Neon).

La scelta si fa in config.yaml, sezione `database`:
    tipo: sqlite     -> file locale, nessuna dipendenza
    tipo: postgres   -> stringa di connessione in .env (DATABASE_URL)

Le due varianti espongono le stesse funzioni: il resto del programma non sa
quale delle due sta usando.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

from .config import env

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS posts (
    message_id   INTEGER PRIMARY KEY,
    grouped_id   INTEGER,
    date_utc     TEXT NOT NULL,
    edit_date    TEXT,
    text         TEXT NOT NULL DEFAULT '',
    entities     TEXT NOT NULL DEFAULT '[]',
    media        TEXT NOT NULL DEFAULT '[]',
    views        INTEGER DEFAULT 0,
    forward_from TEXT,
    forward_json TEXT,
    link         TEXT,
    status       TEXT NOT NULL DEFAULT 'published',
    fetched_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(date_utc DESC);
CREATE INDEX IF NOT EXISTS idx_posts_group ON posts(grouped_id);

CREATE TABLE IF NOT EXISTS translations (
    message_id  INTEGER NOT NULL,
    lang        TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    title       TEXT NOT NULL,
    html        TEXT NOT NULL,
    excerpt     TEXT NOT NULL DEFAULT '',
    engine      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    PRIMARY KEY (message_id, lang)
);

CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS pubblicati (
    percorso TEXT PRIMARY KEY,
    firma    TEXT NOT NULL
);
"""

SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS posts (
    message_id   BIGINT PRIMARY KEY,
    grouped_id   BIGINT,
    date_utc     TEXT NOT NULL,
    edit_date    TEXT,
    text         TEXT NOT NULL DEFAULT '',
    entities     TEXT NOT NULL DEFAULT '[]',
    media        TEXT NOT NULL DEFAULT '[]',
    views        BIGINT DEFAULT 0,
    forward_from TEXT,
    forward_json TEXT,
    link         TEXT,
    status       TEXT NOT NULL DEFAULT 'published',
    fetched_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(date_utc DESC);
CREATE INDEX IF NOT EXISTS idx_posts_group ON posts(grouped_id);

CREATE TABLE IF NOT EXISTS translations (
    message_id  BIGINT NOT NULL,
    lang        TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    title       TEXT NOT NULL,
    html        TEXT NOT NULL,
    excerpt     TEXT NOT NULL DEFAULT '',
    engine      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    PRIMARY KEY (message_id, lang)
);

CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS pubblicati (
    percorso TEXT PRIMARY KEY,
    firma    TEXT NOT NULL
);
"""


class Archivio:
    """Connessione all'archivio, indipendente dal motore usato."""

    def __init__(self, conn, dialetto: str):
        self.conn = conn
        self.dialetto = dialetto

    # ---- traduzione dei segnaposto ----------------------------------------
    def _sql(self, sql: str) -> str:
        if self.dialetto != "postgres":
            return sql
        sql = re.sub(r":(\w+)", r"%(\1)s", sql)
        fuori = []
        dentro_stringa = False
        for ch in sql:
            if ch == "'":
                dentro_stringa = not dentro_stringa
            if ch == "?" and not dentro_stringa:
                fuori.append("%s")
            else:
                fuori.append(ch)
        return "".join(fuori)

    def execute(self, sql: str, params=()):
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), params)
        return cur

    def query(self, sql: str, params=()) -> list:
        cur = self.execute(sql, params)
        righe = cur.fetchall()
        cur.close()
        return righe

    def uno(self, sql: str, params=()):
        cur = self.execute(sql, params)
        riga = cur.fetchone()
        cur.close()
        return riga

    def commit(self):
        self.conn.commit()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


def connect(cfg_o_percorso) -> Archivio:
    """Apre l'archivio. Accetta la configurazione oppure un percorso SQLite."""
    if isinstance(cfg_o_percorso, (str, Path)):
        return _apri_sqlite(Path(cfg_o_percorso))

    cfg = cfg_o_percorso
    sezione = cfg.get("database") or {}
    tipo = (sezione.get("tipo") or "sqlite").lower()
    if tipo in ("postgres", "postgresql", "neon"):
        return _apri_postgres(env("DATABASE_URL") or sezione.get("url", ""))
    return _apri_sqlite(cfg.db_path)


def _apri_sqlite(percorso: Path) -> Archivio:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(percorso))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQLITE)
    _migra_sqlite(conn)
    conn.commit()
    return Archivio(conn, "sqlite")


def _apri_postgres(url: str) -> Archivio:
    if not url:
        raise SystemExit(
            "Manca la stringa di connessione al database.\n"
            "Aggiungi DATABASE_URL nel file .env (la trovi nella dashboard di Neon)."
        )
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        raise SystemExit(
            "Manca il driver PostgreSQL.\n"
            "Installalo con:  pip install \"psycopg[binary]\""
        )
    conn = psycopg.connect(url, row_factory=dict_row, autocommit=False)
    with conn.cursor() as cur:
        cur.execute(SCHEMA_POSTGRES)
    conn.commit()
    return Archivio(conn, "postgres")


def _migra_sqlite(conn: sqlite3.Connection) -> None:
    """Colonne aggiunte dopo la prima versione del database."""
    colonne = {r["name"] for r in conn.execute("PRAGMA table_info(posts)")}
    if "forward_json" not in colonne:
        conn.execute("ALTER TABLE posts ADD COLUMN forward_json TEXT")


# ---------------------------------------------------------------------------
#  Post
# ---------------------------------------------------------------------------

def upsert_post(db: Archivio, post: dict) -> str:
    """Inserisce o aggiorna un post. Ritorna 'new', 'updated' o 'unchanged'."""
    riga = db.uno(
        "SELECT text, entities, media, edit_date FROM posts WHERE message_id = ?",
        (post["message_id"],),
    )
    entities = json.dumps(post.get("entities", []), ensure_ascii=False)
    media = json.dumps(post.get("media", []), ensure_ascii=False)
    provenienza = json.dumps(post.get("provenienza"), ensure_ascii=False) if post.get("provenienza") else None

    if riga is None:
        db.execute(
            """INSERT INTO posts (message_id, grouped_id, date_utc, edit_date, text, entities, media,
                                  views, forward_from, forward_json, link, status, fetched_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                post["message_id"], post.get("grouped_id"), post["date_utc"], post.get("edit_date"),
                post.get("text", ""), entities, media, post.get("views", 0),
                (post.get("provenienza") or {}).get("nome") or post.get("forward_from"),
                provenienza, post.get("link"), post.get("status", "published"),
                post["fetched_at"], post["fetched_at"],
            ),
        )
        return "new"

    uguale = (
        riga["text"] == post.get("text", "")
        and riga["entities"] == entities
        and riga["media"] == media
        and (riga["edit_date"] or "") == (post.get("edit_date") or "")
    )
    if uguale:
        db.execute(
            "UPDATE posts SET views = ?, updated_at = ? WHERE message_id = ?",
            (post.get("views", 0), post["fetched_at"], post["message_id"]),
        )
        return "unchanged"

    # aggiornamento: non tocca lo stato editoriale già deciso dall'utente
    db.execute(
        """UPDATE posts SET grouped_id=?, date_utc=?, edit_date=?, text=?, entities=?, media=?,
                            views=?, forward_from=?, forward_json=?, link=?, updated_at=?
           WHERE message_id=?""",
        (
            post.get("grouped_id"), post["date_utc"], post.get("edit_date"), post.get("text", ""),
            entities, media, post.get("views", 0),
            (post.get("provenienza") or {}).get("nome") or post.get("forward_from"),
            provenienza, post.get("link"), post["fetched_at"], post["message_id"],
        ),
    )
    return "updated"


def published_posts(db: Archivio) -> list:
    return db.query(
        "SELECT * FROM posts WHERE status = 'published' ORDER BY date_utc DESC, message_id DESC"
    )


def counts(db: Archivio) -> dict:
    righe = db.query("SELECT status, COUNT(*) AS n FROM posts GROUP BY status")
    return {r["status"]: r["n"] for r in righe}


def bozze(db: Archivio) -> list:
    return db.query(
        "SELECT message_id, date_utc, substr(text, 1, 70) AS anteprima "
        "FROM posts WHERE status = 'draft' ORDER BY date_utc DESC"
    )


def pubblica_bozza(db: Archivio, message_id: int) -> None:
    db.execute("UPDATE posts SET status = 'published' WHERE message_id = ?", (int(message_id),))


# ---------------------------------------------------------------------------
#  Stato
# ---------------------------------------------------------------------------

def get_state(db: Archivio, key: str, default=None):
    riga = db.uno("SELECT value FROM state WHERE key = ?", (key,))
    return riga["value"] if riga else default


def set_state(db: Archivio, key: str, value) -> None:
    db.execute(
        "INSERT INTO state (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


# ---------------------------------------------------------------------------
#  Traduzioni
# ---------------------------------------------------------------------------

def traduzione(db: Archivio, message_id: int, lang: str):
    return db.uno(
        "SELECT * FROM translations WHERE message_id = ? AND lang = ?", (message_id, lang)
    )


def salva_traduzione(db: Archivio, dati: dict) -> None:
    db.execute(
        """INSERT INTO translations (message_id, lang, source_hash, title, html, excerpt, engine, created_at)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT (message_id, lang) DO UPDATE SET
             source_hash = excluded.source_hash, title = excluded.title, html = excluded.html,
             excerpt = excluded.excerpt, engine = excluded.engine, created_at = excluded.created_at""",
        (
            dati["message_id"], dati["lang"], dati["source_hash"], dati["title"],
            dati["html"], dati["excerpt"], dati["engine"], dati["created_at"],
        ),
    )


def traduzioni_per_lingua(db: Archivio, lang: str) -> dict:
    righe = db.query("SELECT * FROM translations WHERE lang = ?", (lang,))
    return {r["message_id"]: r for r in righe}


def svuota_traduzioni(db: Archivio, lang: str | None = None) -> None:
    if lang:
        db.execute("DELETE FROM translations WHERE lang = ?", (lang,))
    else:
        db.execute("DELETE FROM translations")


# ---------------------------------------------------------------------------
#  Registro delle pubblicazioni (quali file sono già online)
# ---------------------------------------------------------------------------

def registro_pubblicazioni(db: Archivio) -> dict:
    return {r["percorso"]: r["firma"] for r in db.query("SELECT percorso, firma FROM pubblicati")}


def segna_pubblicato(db: Archivio, percorso: str, firma: str) -> None:
    db.execute(
        "INSERT INTO pubblicati (percorso, firma) VALUES (?, ?) "
        "ON CONFLICT (percorso) DO UPDATE SET firma = excluded.firma",
        (percorso, firma),
    )


def svuota_registro(db: Archivio) -> None:
    db.execute("DELETE FROM pubblicati")


# ---------------------------------------------------------------------------
#  Migrazione fra due archivi (es. da SQLite a Neon)
# ---------------------------------------------------------------------------

def migra(origine: Archivio, destinazione: Archivio) -> dict:
    """Copia post, traduzioni, stato e registro da un archivio all'altro."""
    conteggi = {"posts": 0, "translations": 0, "state": 0, "pubblicati": 0}

    for riga in origine.query("SELECT * FROM posts"):
        destinazione.execute(
            """INSERT INTO posts (message_id, grouped_id, date_utc, edit_date, text, entities, media,
                                  views, forward_from, forward_json, link, status, fetched_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT (message_id) DO UPDATE SET
                 grouped_id=excluded.grouped_id, date_utc=excluded.date_utc, edit_date=excluded.edit_date,
                 text=excluded.text, entities=excluded.entities, media=excluded.media, views=excluded.views,
                 forward_from=excluded.forward_from, forward_json=excluded.forward_json, link=excluded.link,
                 status=excluded.status, fetched_at=excluded.fetched_at, updated_at=excluded.updated_at""",
            (
                riga["message_id"], riga["grouped_id"], riga["date_utc"], riga["edit_date"],
                riga["text"], riga["entities"], riga["media"], riga["views"],
                riga["forward_from"], riga["forward_json"], riga["link"], riga["status"],
                riga["fetched_at"], riga["updated_at"],
            ),
        )
        conteggi["posts"] += 1

    for riga in origine.query("SELECT * FROM translations"):
        salva_traduzione(destinazione, dict(riga))
        conteggi["translations"] += 1

    for riga in origine.query("SELECT * FROM state"):
        set_state(destinazione, riga["key"], riga["value"])
        conteggi["state"] += 1

    for riga in origine.query("SELECT * FROM pubblicati"):
        segna_pubblicato(destinazione, riga["percorso"], riga["firma"])
        conteggi["pubblicati"] += 1

    destinazione.commit()
    return conteggi
