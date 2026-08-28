"""Pubblicazione del sito generato.

Quattro modi, scelti con 'deploy.tipo' in config.yaml:
  nessuno  il sito resta in public/ e lo serve direttamente il tuo web server
  locale   copia in una cartella dello stesso computer o NAS (nginx, Web Station)
  rsync    sincronizza via SSH su un tuo server
  ftp/ftps carica su uno spazio web di terzi, solo i file cambiati
"""
from __future__ import annotations

import ftplib
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from . import store
from .config import ROOT, Config, env


def _firma(percorso: Path) -> str:
    return hashlib.sha1(percorso.read_bytes()).hexdigest()


def _connetti(cfg: Config):
    dep = cfg.get("deploy") or {}
    tipo = (dep.get("tipo") or "nessuno").lower()
    host = dep.get("host", "")
    utente = env("FTP_USER")
    password = env("FTP_PASSWORD")
    porta = int(dep.get("porta") or 21)

    if not host or not utente or not password:
        raise SystemExit(
            "Configurazione FTP incompleta.\n"
            "Serve 'deploy.host' in config.yaml e FTP_USER / FTP_PASSWORD nel file .env"
        )

    if tipo == "ftps":
        ftp = ftplib.FTP_TLS()
        ftp.connect(host, porta, timeout=30)
        ftp.login(utente, password)
        ftp.prot_p()  # cifra anche il canale dati
    else:
        ftp = ftplib.FTP()
        ftp.connect(host, porta, timeout=30)
        ftp.login(utente, password)
    ftp.set_pasv(True)
    return ftp


def _radice_effettiva(ftp, radice: str, cfg: Config) -> str:
    """Trova la cartella del sito sullo spazio web.

    Su molti hosting (Aruba compreso) l'accesso FTP non atterra nella cartella
    pubblicata ma un livello sopra, dove c'è una cartella con il nome del
    dominio: scrivere nella radice dà "550 Permission denied".
    """
    if radice not in ("", "/"):
        return radice
    try:
        voci = [v.strip("/").split("/")[-1] for v in ftp.nlst()]
    except Exception:
        return radice
    dominio = (urlparse(cfg["site"]["base_url"]).netloc or "").replace("www.", "")
    candidati = [v for v in voci if dominio and dominio in v]
    candidati += [v for v in voci if v in ("www", "htdocs", "httpdocs", "public_html", "web")]
    if candidati:
        scelta = "/" + candidati[0]
        print(f"Cartella del sito rilevata: {scelta}")
        return scelta
    return radice


def _assicura_cartella(ftp, percorso: str, create: set) -> None:
    """Crea la catena di cartelle remote, una sola volta per esecuzione."""
    parti = [p for p in percorso.split("/") if p]
    corrente = ""
    for parte in parti:
        corrente = f"{corrente}/{parte}"
        if corrente in create:
            continue
        try:
            ftp.mkd(corrente)
        except ftplib.error_perm as exc:
            if not str(exc).startswith("550"):  # 550 = esiste già
                raise
        create.add(corrente)


def _pubblica_locale(cfg: Config, dep: dict) -> dict:
    """Copia il sito in una cartella servita da un web server tuo (NAS, VPS)."""
    destinazione = Path(dep.get("cartella_remota") or "")
    if not destinazione:
        raise SystemExit("Imposta 'deploy.cartella_remota' con il percorso servito dal web server")
    destinazione.mkdir(parents=True, exist_ok=True)
    locale = cfg.output_dir
    copiati = 0
    for percorso in locale.rglob("*"):
        if not percorso.is_file():
            continue
        obiettivo = destinazione / percorso.relative_to(locale)
        obiettivo.parent.mkdir(parents=True, exist_ok=True)
        if obiettivo.exists() and obiettivo.stat().st_size == percorso.stat().st_size \
           and obiettivo.stat().st_mtime >= percorso.stat().st_mtime:
            continue
        shutil.copy2(percorso, obiettivo)
        copiati += 1
    print(f"Copiati {copiati} file in {destinazione}")
    return {"caricati": copiati, "destinazione": str(destinazione)}


def _pubblica_rsync(cfg: Config, dep: dict) -> dict:
    """Sincronizza il sito su un server via SSH. Richiede rsync e una chiave SSH."""
    host = dep.get("host") or ""
    utente = dep.get("utente") or os.getenv("SSH_USER", "")
    remota = (dep.get("cartella_remota") or "").rstrip("/")
    if not host or not remota:
        raise SystemExit("Per rsync servono 'deploy.host' e 'deploy.cartella_remota' in config.yaml")

    destinazione = f"{utente + '@' if utente else ''}{host}:{remota}/"
    comando = ["rsync", "-az", "--delete", "--partial"]
    porta = int(dep.get("porta_ssh") or 22)
    chiave = dep.get("chiave_ssh") or os.getenv("SSH_KEY", "")
    ssh = f"ssh -p {porta}" + (f" -i {chiave}" if chiave else "")
    comando += ["-e", ssh, f"{cfg.output_dir}/", destinazione]

    print(f"Sincronizzazione con {destinazione}…")
    esito = subprocess.run(comando, capture_output=True, text=True)
    if esito.returncode != 0:
        raise SystemExit(f"rsync non riuscito:\n{esito.stderr.strip()[:500]}")
    righe = [r for r in esito.stdout.splitlines() if r.strip()]
    print(f"Sincronizzazione completata ({len(righe)} voci aggiornate).")
    return {"caricati": len(righe), "destinazione": destinazione}


def pubblica(cfg: Config, forza: bool = False) -> dict:
    dep = cfg.get("deploy") or {}
    tipo = (dep.get("tipo") or "nessuno").lower()
    if tipo == "nessuno":
        return {"saltato": True}
    if tipo == "locale":
        return _pubblica_locale(cfg, dep)
    if tipo == "rsync":
        return _pubblica_rsync(cfg, dep)

    radice_remota = (dep.get("cartella_remota") or "/").rstrip("/")
    locale = cfg.output_dir
    if not locale.exists():
        raise SystemExit("La cartella public/ non esiste: esegui prima 'python run.py build'")

    # il registro di ciò che è già online sta nell'archivio: così l'automazione
    # può girare anche su una macchina diversa ogni volta (GitHub Actions, Render)
    db = store.connect(cfg)
    if forza:
        store.svuota_registro(db)
        db.commit()
    registro = {} if forza else store.registro_pubblicazioni(db)
    file_locali = [p for p in locale.rglob("*") if p.is_file()]

    da_caricare = []
    for percorso in file_locali:
        rel = str(percorso.relative_to(locale)).replace("\\", "/")
        firma = _firma(percorso)
        if registro.get(rel) != firma:
            da_caricare.append((percorso, rel, firma))

    if not da_caricare:
        db.close()
        print("Niente da pubblicare: il sito remoto è già aggiornato.")
        return {"caricati": 0, "totale": len(file_locali)}

    print(f"Pubblicazione su {dep.get('host')}: {len(da_caricare)} file da caricare…")
    ftp = _connetti(cfg)
    radice_remota = _radice_effettiva(ftp, radice_remota, cfg)
    create: set[str] = set()
    caricati = 0
    try:
        for percorso, rel, firma in da_caricare:
            remoto = f"{radice_remota}/{rel}"
            cartella = remoto.rsplit("/", 1)[0]
            if cartella:
                _assicura_cartella(ftp, cartella, create)
            try:
                with open(percorso, "rb") as fh:
                    ftp.storbinary(f"STOR {remoto}", fh)
            except ftplib.error_perm as exc:
                if str(exc).startswith("550"):
                    raise SystemExit(
                        f"Lo spazio web rifiuta la scrittura in {cartella or '/'} ({exc}).\n"
                        "Controlla 'deploy.cartella_remota' in config.yaml: su Aruba di solito è\n"
                        "la cartella con il nome del dominio, per esempio /www.mondomultipolare.it"
                    )
                raise
            store.segna_pubblicato(db, rel, firma)
            caricati += 1
            if caricati % 20 == 0:
                db.commit()
                print(f"  … {caricati}/{len(da_caricare)}")
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()

    db.commit()
    db.close()
    print(f"Pubblicati {caricati} file su {len(file_locali)} totali.")
    return {"caricati": caricati, "totale": len(file_locali)}
