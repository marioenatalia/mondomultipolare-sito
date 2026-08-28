#!/usr/bin/env python3
"""
Automazione canale Telegram -> sito di informazione.

Comandi:
  python run.py ingest            importa i post dal canale (storico + nuovi)
  python run.py ingest --giorni 2 importa solo i post di ieri e oggi
  python run.py traduci           traduce gli articoli nelle lingue attive (--simulato per provare senza chiave)
  python run.py prova-traduzione  verifica la chiave traducendo una frase di prova
  python run.py build             rigenera il sito statico (tutte le lingue)
  python run.py pubblica          carica il sito sullo spazio web via FTP (--tutto = ricarica tutto)
  python run.py aggiorna          ingest + build (è il comando da schedulare)
  python run.py watch             resta in ascolto e pubblica in tempo reale
  python run.py serve             anteprima locale su http://localhost:8000
  python run.py demo              crea post di esempio per vedere subito la grafica
  python run.py sessione          genera la sessione portabile per il cloud
  python run.py logo              scarica l'immagine del canale e la usa come logo e icone
  python run.py migra [file]      copia l'archivio SQLite nel database configurato (Neon)
  python run.py stato             mostra quanti post ci sono e in che stato
  python run.py approva 123 456   pubblica i post rimasti in bozza (modo 'draft')
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

from tgsite import store
from tgsite.build import build_site
from tgsite.config import load_config


def cmd_ingest(cfg, args):
    from tgsite.ingest import ingest

    giorni = None
    numeri = [a for a in args if a.isdigit()]
    for a in args:
        if a.startswith("--giorni"):
            # accetta sia "--giorni 2" sia "--giorni=2"
            if "=" in a:
                giorni = int(a.split("=", 1)[1])
            elif numeri:
                giorni = int(numeri[0])
                numeri = numeri[1:]
            else:
                giorni = 2
    limit = int(numeri[0]) if numeri and giorni is None else None
    ingest(cfg, watch=False, limit=limit, giorni=giorni)


def cmd_watch(cfg, args):
    from tgsite.ingest import ingest

    ingest(cfg, watch=True)


def cmd_build(cfg, args):
    info = build_site(cfg)
    dettaglio = ", ".join(f"{lang} {n}" for lang, n in info["lingue"].items())
    print(f"Sito generato: {info['posts']} articoli ({dettaglio}) su {info['pagine']} pagine → {info['output']}")


def cmd_traduci(cfg, args):
    from tgsite.translate import traduci_articoli

    lingue = [a for a in args if not a.startswith("--")] or None
    traduci_articoli(cfg, simulato="--simulato" in args, solo=lingue)


def cmd_prova_traduzione(cfg, args):
    """Traduce una frase di prova: verifica chiave e modello senza toccare il sito."""
    from tgsite.translate import traduci

    lingua = args[0] if args else "en"
    esito = traduci(
        "Vertice a Bruxelles sul nuovo pacchetto di sanzioni",
        "<p>I ministri degli Esteri si riuniscono oggi. Sul tavolo il <strong>tetto al prezzo "
        "del greggio</strong> e nuove restrizioni all'export.</p>",
        lingua,
        cfg["lingue"].get("modello") or "claude-sonnet-4-5",
    )
    print(f"\nModello usato: {esito.get('modello')}")
    print(f"Titolo:  {esito.get('titolo')}")
    print(f"Corpo:   {esito.get('html')}\n")


def cmd_logo(cfg, args):
    """Prende l'immagine del canale Telegram e la usa come logo e favicon."""
    from tgsite.ingest import scarica_logo

    if scarica_logo(cfg):
        print("Ricordati di mettere  logo: true  nella sezione site di config.yaml.")
        cmd_build(cfg, [])


def cmd_migra(cfg, args):
    """Copia l'archivio SQLite dentro il database configurato (es. Neon)."""
    from tgsite import store as archivio

    sorgente = args[0] if args else str(cfg.db_path)
    destinazione_tipo = (cfg.get("database") or {}).get("tipo", "sqlite")
    if destinazione_tipo == "sqlite":
        print("La destinazione è ancora SQLite: imposta database.tipo: postgres in config.yaml.")
        return

    origine = archivio.connect(sorgente)
    destinazione = archivio.connect(cfg)
    print(f"Migrazione da {sorgente} verso {destinazione.dialetto}…")
    esito = archivio.migra(origine, destinazione)
    origine.close()
    destinazione.close()
    print("Copiati: " + ", ".join(f"{n} {nome}" for nome, n in esito.items()))


def cmd_pubblica(cfg, args):
    from tgsite.deploy import pubblica

    esito = pubblica(cfg, forza="--tutto" in args)
    if esito.get("saltato"):
        print("Pubblicazione FTP non configurata (deploy.tipo: nessuno in config.yaml).")


def cmd_aggiorna(cfg, args):
    cmd_ingest(cfg, [a for a in args if not a.startswith("--")])
    altre = [l for l in cfg["lingue"]["attive"] if l != cfg["lingue"]["sorgente"]]
    if altre and "--senza-traduzioni" not in args:
        print("Traduzioni…")
        cmd_traduci(cfg, [a for a in args if a.startswith("--")])
    cmd_build(cfg, args)
    if (cfg.get("deploy") or {}).get("tipo", "nessuno") != "nessuno":
        cmd_pubblica(cfg, args)


def cmd_serve(cfg, args):
    import http.server
    import socketserver

    porta = int(args[0]) if args else 8000
    directory = str(cfg.output_dir)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=directory, **kw)

        def log_message(self, *a):
            pass

    with socketserver.TCPServer(("", porta), Handler) as httpd:
        print(f"Anteprima su http://localhost:{porta}  (Ctrl+C per fermare)")
        httpd.serve_forever()


def cmd_stato(cfg, args):
    db = store.connect(cfg)
    tot = store.counts(db)
    print(f"Archivio: {db.dialetto}")
    print("Post:")
    for stato, n in sorted(tot.items()):
        print(f"  {stato:<10} {n}")
    lingue = [l for l in cfg["lingue"]["attive"] if l != cfg["lingue"]["sorgente"]]
    for lang in lingue:
        n = len(store.traduzioni_per_lingua(db, lang))
        print(f"  traduzioni {lang}: {n}")
    print(f"Ultimo messaggio importato: #{store.get_state(db, 'last_message_id', '—')}")
    print(f"Ultima esecuzione: {store.get_state(db, 'last_run', 'mai')}")
    db.close()


def cmd_approva(cfg, args):
    db = store.connect(cfg)
    if not args:
        righe = store.bozze(db)
        if not righe:
            print("Nessun post in bozza.")
        for riga in righe:
            print(f"#{riga['message_id']}  {riga['date_utc'][:16]}  {riga['anteprima']}…")
        db.close()
        return
    for mid in args:
        store.pubblica_bozza(db, mid)
    db.commit()
    db.close()
    print(f"{len(args)} post pubblicati. Rigenero il sito…")
    cmd_build(cfg, [])


DEMO = [
    (
        "Vertice straordinario a Bruxelles sul nuovo pacchetto di sanzioni\n\n"
        "I ministri degli Esteri dell'Unione europea si riuniscono oggi per discutere "
        "il quindicesimo pacchetto di misure restrittive. Sul tavolo il tetto al prezzo "
        "del greggio e nuove restrizioni all'export di componentistica dual use.\n\n"
        "Fonti diplomatiche riferiscono che tre Paesi mantengono una riserva formale.",
        [{"type": "bold", "offset": 0, "length": 63}],
    ),
    (
        "Washington rivede la postura militare nell'Indo-Pacifico\n\n"
        "Il Pentagono ha annunciato la riallocazione di due gruppi portaerei. "
        "La mossa arriva a poche settimane dalle esercitazioni congiunte nel Mar Cinese Meridionale.",
        [{"type": "bold", "offset": 0, "length": 55}],
    ),
    (
        "Il corridoio energetico del Caspio entra nella fase operativa\n\n"
        "Firmato l'accordo trilaterale che collega i giacimenti dell'Asia centrale ai terminal "
        "sul Mar Nero. L'intesa modifica gli equilibri del mercato del gas in Europa orientale.",
        [{"type": "bold", "offset": 0, "length": 60}, {"type": "italic", "offset": 62, "length": 24}],
    ),
    (
        "Sahel, la giunta militare sospende gli accordi di cooperazione\n\n"
        "Terza rottura diplomatica in sei mesi nella regione. Gli osservatori parlano di un "
        "riallineamento profondo delle alleanze africane.",
        [{"type": "bold", "offset": 0, "length": 61}],
    ),
    (
        "Mercati: il petrolio sopra i 90 dollari dopo le tensioni nel Golfo\n\n"
        "Il Brent guadagna il 3,4% in apertura. Gli analisti segnalano che l'inflazione "
        "energetica potrebbe tornare a pesare sulle economie importatrici.",
        [{"type": "bold", "offset": 0, "length": 65}],
    ),
    (
        "Cina e Taiwan, nuova fase negoziale sui collegamenti commerciali\n\n"
        "Pechino annuncia la riapertura di due rotte marittime. Taipei risponde con cautela, "
        "in attesa di garanzie sulla libertà di navigazione.",
        [{"type": "bold", "offset": 0, "length": 63}],
    ),
    (
        "Ucraina, ricostruzione: la conferenza dei donatori fissa la cifra\n\n"
        "Sul tavolo un piano decennale. La Banca Mondiale stima il fabbisogno complessivo "
        "in una cifra superiore ai 480 miliardi di dollari.",
        [{"type": "bold", "offset": 0, "length": 64}],
    ),
    (
        "Israele e Libano, riprende il negoziato sui confini marittimi\n\n"
        "La mediazione internazionale punta a un'intesa entro fine mese. In gioco le concessioni "
        "per l'esplorazione dei giacimenti offshore.",
        [{"type": "bold", "offset": 0, "length": 60}],
    ),
    (
        "Russia, la banca centrale alza i tassi al 21%\n\n"
        "Manovra difensiva contro la pressione sul rublo. L'istituto segnala che l'inflazione "
        "resta sopra l'obiettivo del 4%.",
        [{"type": "bold", "offset": 0, "length": 44}],
    ),
    (
        "Germania e Francia divise sul bilancio comune europeo\n\n"
        "Il negoziato entra nella fase decisiva. Berlino chiede tetti di spesa più rigidi, "
        "Parigi difende gli investimenti nella difesa comune.",
        [{"type": "bold", "offset": 0, "length": 52}],
    ),
    (
        "Sudan, l'ONU chiede un corridoio umanitario\n\n"
        "Le agenzie stimano oltre nove milioni di sfollati interni. La richiesta di accesso "
        "riguarda tre regioni finora inaccessibili agli aiuti.",
        [{"type": "bold", "offset": 0, "length": 42}],
    ),
    (
        "Iran, ripresa dei colloqui tecnici sul programma nucleare\n\n"
        "Delegazioni a Vienna per la prima volta dopo diciotto mesi. Nessuna delle parti "
        "ha diffuso dichiarazioni ufficiali al termine della sessione.",
        [{"type": "bold", "offset": 0, "length": 56}],
    ),
]


def cmd_sessione(cfg, args):
    """Genera una sessione portabile da incollare nei segreti del cloud."""
    from tgsite.ingest import esporta_sessione

    valore = esporta_sessione()
    print("\nCopia questa stringa nel segreto TG_SESSION_STRING (trattala come una password):\n")
    print(valore)


def cmd_demo(cfg, args):
    """Riempie il database con post di esempio, per valutare la grafica."""
    conn = store.connect(cfg)
    adesso = datetime.now(timezone.utc)
    for i, (testo, entita) in enumerate(DEMO):
        quando = adesso - timedelta(hours=5 * i + 1)
        store.upsert_post(
            conn,
            {
                "message_id": 900000 + i,
                "grouped_id": None,
                "date_utc": quando.isoformat(timespec="seconds"),
                "text": testo,
                "entities": entita,
                "media": [],
                "views": 1200 - i * 37,
                "link": "https://t.me/esempio/" + str(900000 + i),
                "status": "published",
                "fetched_at": adesso.isoformat(timespec="seconds"),
            },
        )
    conn.commit()
    conn.close()
    print(f"{len(DEMO)} post di esempio inseriti.")
    cmd_build(cfg, [])


COMANDI = {
    "ingest": cmd_ingest,
    "build": cmd_build,
    "pubblica": cmd_pubblica,
    "traduci": cmd_traduci,
    "migra": cmd_migra,
    "logo": cmd_logo,
    "prova-traduzione": cmd_prova_traduzione,
    "aggiorna": cmd_aggiorna,
    "watch": cmd_watch,
    "serve": cmd_serve,
    "stato": cmd_stato,
    "approva": cmd_approva,
    "demo": cmd_demo,
    "sessione": cmd_sessione,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return
    comando = sys.argv[1]
    if comando not in COMANDI:
        print(f"Comando sconosciuto: {comando}\n")
        print(__doc__)
        sys.exit(1)
    cfg = load_config()
    COMANDI[comando](cfg, sys.argv[2:])


if __name__ == "__main__":
    main()
