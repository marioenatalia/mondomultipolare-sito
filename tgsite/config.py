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


def env(nome: str, predefinito: str = "") -> str:
    """Valore di una variabile d'ambiente, tollerante agli errori di copia.

    Se per sbaglio si incolla l'intera riga del file .env (per esempio
    "DATABASE_URL=postgresql://...") il prefisso "NOME=" viene rimosso.
    Toglie anche eventuali virgolette attorno al valore.
    """
    valore = os.getenv(nome, predefinito) or ""
    valore = valore.strip()
    prefisso = nome + "="
    if valore.startswith(prefisso):
        valore = valore[len(prefisso):].strip()
    if len(valore) >= 2 and valore[0] == valore[-1] and valore[0] in "\"'":
        valore = valore[1:-1].strip()
    return valore


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
    api_id = env("TG_API_ID")
    api_hash = env("TG_API_HASH")
    if not api_id or not api_hash:
        raise SystemExit(
            "Credenziali Telegram mancanti.\n"
            "Crea il file .env partendo da .env.example e inserisci "
            "TG_API_ID e TG_API_HASH ottenuti su https://my.telegram.org"
        )
    session = env("TG_SESSION", "data/sessione") or "data/sessione"
    session_path = Path(session)
    if not session_path.is_absolute():
        session_path = ROOT / session_path
    session_path.parent.mkdir(parents=True, exist_ok=True)
    return {
        "session_string": env("TG_SESSION_STRING") or None,
        "api_id": int(api_id),
        "api_hash": api_hash,
        "phone": env("TG_PHONE") or None,
        # password della verifica in due passaggi: se non c'è, viene chiesta a video
        "password": env("TG_PASSWORD") or None,
        "session": str(session_path),
    }
