"""Ottimizzazione delle immagini scaricate da Telegram.

Le foto arrivano spesso a piena risoluzione: pesano sulla banda dello spazio
web e sul tempo di caricamento delle pagine. Qui vengono ridimensionate,
ricompresse e affiancate da una miniatura per le anteprime in homepage.

Richiede Pillow. Se non è installato il sistema continua a funzionare con
le immagini originali: nessun errore, solo file più pesanti.
"""
from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image, ImageOps

    DISPONIBILE = True
except ImportError:  # Pillow non installato
    DISPONIBILE = False

ESTENSIONI = {".jpg", ".jpeg", ".png", ".webp"}


def ottimizza(percorso: Path, cfg_media: dict) -> dict:
    """Ridimensiona l'immagine e crea la miniatura. Ritorna i percorsi utili."""
    if not DISPONIBILE or percorso.suffix.lower() not in ESTENSIONI:
        return {}
    if not cfg_media.get("ottimizza", True):
        return {}

    larghezza_max = int(cfg_media.get("larghezza_massima") or 1600)
    qualita = int(cfg_media.get("qualita") or 82)
    larghezza_miniatura = int(cfg_media.get("larghezza_miniatura") or 800)

    try:
        with Image.open(percorso) as img:
            # rispetta l'orientamento della fotocamera e toglie i metadati EXIF
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            originale = img.copy()
            if img.width > larghezza_max:
                altezza = round(img.height * larghezza_max / img.width)
                img = img.resize((larghezza_max, altezza), Image.LANCZOS)
            img.save(percorso, quality=qualita, optimize=True, progressive=True)

            miniatura = percorso.with_name(percorso.stem + "-min.jpg")
            piccola = originale
            if piccola.width > larghezza_miniatura:
                altezza = round(piccola.height * larghezza_miniatura / piccola.width)
                piccola = piccola.resize((larghezza_miniatura, altezza), Image.LANCZOS)
            if piccola.mode != "RGB":
                piccola = piccola.convert("RGB")
            piccola.save(miniatura, "JPEG", quality=78, optimize=True, progressive=True)

        return {
            "larghezza": img.width,
            "altezza": img.height,
            "miniatura": miniatura,
            "peso": percorso.stat().st_size,
        }
    except Exception as exc:  # un'immagine corrotta non deve fermare l'importazione
        print(f"  ! immagine non ottimizzata ({percorso.name}): {exc}")
        return {}


def avviso_pillow() -> str | None:
    if DISPONIBILE:
        return None
    return (
        "Pillow non è installato: le foto vengono pubblicate alla risoluzione originale.\n"
        "Per ottimizzarle:  pip install Pillow"
    )
