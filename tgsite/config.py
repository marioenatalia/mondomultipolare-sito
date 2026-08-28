"""Caricamento della configurazione (config.yaml + .env)."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv è opzionale
    def load_dotenv(*_a, **_k):
        return False

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "telegram": {
        "channel": "",
        "backfill_limit": 300,
        "download_media": True,
        "max_media_mb": 50,
    },
    "site": {
        "title": "Sito di informazione",
        "tagline": "",
        "base_url": "http://localhost:8000",
        "language": "it",
        "footer": "",
        "telegram_url": "",
        "logo": False,
        "posts_per_page": 12,
        "show_source_link": True,
    },
    "database": {
        "tipo": "sqlite",
        "url": "",
    },
    "media": {
        "ottimizza": True,
        "larghezza_massima": 1600,
        "larghezza_miniatura": 800,
        "qualita": 82,
    },
    "lingue": {
        "sorgente": "it",
        "attive": ["it"],
        "modello": "claude-sonnet-4-5",
    },
    "fonti": {
        "etichetta_predefinita": "ripreso_da",
        "partner": [],
    },
    "publishing": {
        "mode": "auto",
        "blocklist": [],
        "allowlist": [],
        "min_length": 0,
    },
    "deploy": {
        "tipo": "nessuno",
        "host": "",
        "utente": "",
        "porta": 21,
        "porta_ssh": 22,
        "chiave_ssh": "",
        "cartella_remota": "/",
    },
    "paths": {
        "database": "data/canale.sqlite3",
        "media": "public/media",
        "output": "public",
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


class Config(dict):
    """Configurazione con i percorsi già risolti in assoluto."""

    @property
    def db_path(self) -> Path:
        return self._abs(self["paths"]["database"])

    @property
    def media_dir(self) -> Path:
        return self._abs(self["paths"]["media"])

    @property
    def output_dir(self) -> Path:
        return self._abs(self["paths"]["output"])

    @staticmethod
    def _abs(value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else ROOT / path


def load_config(path: str | os.PathLike | None = None) -> Config:
    load_dotenv(ROOT / ".env")
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    if not cfg_path.exists():
        example = ROOT / "config.example.yaml"
        raise SystemExit(
            f"Manca il file di configurazione {cfg_path.name}.\n"
            f"Copialo dall'esempio:  cp {example.name} {cfg_path.name}"
        )
    with open(cfg_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return Config(_merge(DEFAULTS, data))


def telegram_credentials() -> dict:
    load_dotenv(ROOT / ".env")
    api_id = os.getenv("TG_API_ID", "").strip()
    api_hash = os.getenv("TG_API_HASH", "").strip()
    if not api_id or not api_hash:
        raise SystemExit(
            "Credenziali Telegram mancanti.\n"
            "Crea il file .env partendo da .env.example e inserisci "
            "TG_API_ID e TG_API_HASH ottenuti su https://my.telegram.org"
        )
    session = os.getenv("TG_SESSION", "data/sessione")
    session_path = Path(session)
    if not session_path.is_absolute():
        session_path = ROOT / session_path
    session_path.parent.mkdir(parents=True, exist_ok=True)
    return {
        "session_string": os.getenv("TG_SESSION_STRING", "").strip() or None,
        "api_id": int(api_id),
        "api_hash": api_hash,
        "phone": os.getenv("TG_PHONE", "").strip() or None,
        # password della verifica in due passaggi: se non c'è, viene chiesta a video
        "password": os.getenv("TG_PASSWORD", "").strip() or None,
        "session": str(session_path),
    }
