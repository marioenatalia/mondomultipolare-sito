"""Collega il progetto a Neon: crea la base dati, la configura e migra l'archivio.

Chiede la stringa di connessione (quella del pulsante Connect nella console Neon),
crea il database `mondomultipolare` se non esiste, scrive DATABASE_URL nel file .env,
imposta config.yaml su postgres e copia dentro i post già importati.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

NOME_DB = "mondomultipolare"


def chiedi_stringa() -> str:
    print("Incolla qui la stringa di connessione di Neon e premi Invio.")
    print("(inizia con postgresql:// e finisce con sslmode=require)\n")
    valore = input("> ").strip().strip('"').strip("'")
    if not valore.startswith("postgres"):
        raise SystemExit("Non sembra una stringa di connessione: deve iniziare con postgresql://")
    return valore


def con_database(url: str, nome: str) -> str:
    parti = urlparse(url)
    return urlunparse(parti._replace(path="/" + nome))


def crea_database(url: str) -> None:
    import psycopg

    with psycopg.connect(url, autocommit=True) as conn:
        esiste = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (NOME_DB,)
        ).fetchone()
        if esiste:
            print(f"La base dati '{NOME_DB}' esiste già: la riuso.")
            return
        conn.execute(f'CREATE DATABASE "{NOME_DB}"')
        print(f"Base dati '{NOME_DB}' creata.")


def scrivi_env(url_finale: str) -> None:
    env = RADICE / ".env"
    testo = env.read_text(encoding="utf-8") if env.exists() else ""
    riga = f"DATABASE_URL={url_finale}"
    if re.search(r"(?m)^#?\s*DATABASE_URL=.*$", testo):
        testo = re.sub(r"(?m)^#?\s*DATABASE_URL=.*$", riga, testo, count=1)
    else:
        testo = testo.rstrip() + "\n\n# Archivio su Neon\n" + riga + "\n"
    env.write_text(testo, encoding="utf-8")
    print("Stringa salvata nel file .env")


def imposta_config() -> None:
    cfg = RADICE / "config.yaml"
    testo = cfg.read_text(encoding="utf-8")
    testo = re.sub(
        r'(\ndatabase:\s*\n(?:\s*#.*\n)*\s*tipo:\s*)"[^"]*"', r'\1"postgres"', testo, count=1
    )
    cfg.write_text(testo, encoding="utf-8")
    print("config.yaml impostato su postgres")


def main() -> None:
    url = chiedi_stringa()
    print("\nMi collego a Neon…")
    crea_database(url)
    url_finale = con_database(url, NOME_DB)
    scrivi_env(url_finale)
    imposta_config()

    print("\nTrasferisco l'archivio locale su Neon…")
    import os

    os.environ["DATABASE_URL"] = url_finale
    from tgsite import store
    from tgsite.config import load_config

    cfg = load_config()
    origine = store.connect(RADICE / "data" / "canale.sqlite3")
    destinazione = store.connect(cfg)
    esito = store.migra(origine, destinazione)
    print("Copiati: " + ", ".join(f"{n} {nome}" for nome, n in esito.items()))
    print("\nControllo finale:")
    print("  post pubblicati su Neon:", len(store.published_posts(destinazione)))
    origine.close()
    destinazione.close()
    print("\nFatto. Da adesso l'archivio vive su Neon.")


if __name__ == "__main__":
    main()
