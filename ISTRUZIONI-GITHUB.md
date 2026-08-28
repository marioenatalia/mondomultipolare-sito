# Mettere Mondo Multipolare su GitHub

Tre cose da preparare, poi il sito si aggiorna da solo ogni 15 minuti
anche a computer spento.

---

## 1. Il database su Neon (5 minuti)

1. Vai su **neon.tech** e accedi (o crea l'account).
2. **Create project**: nome `mondomultipolare`, regione **Europe (Frankfurt)**.
3. A progetto creato copia la **Connection string** — la riga lunga che comincia
   con `postgresql://` e finisce con `?sslmode=require`.

Le tabelle si creano da sole al primo avvio: non devi fare altro.

---

## 2. Il repository su GitHub

1. Su **github.com** clicca **New repository**.
2. Nome: `mondomultipolare-sito` — imposta **Private**.
3. Non aggiungere README né .gitignore (ci sono già).
4. Nella pagina che compare, clicca **uploading an existing file**.
5. Trascina dentro **tutto il contenuto** di questa cartella
   (non la cartella: i file e le sottocartelle che ci sono dentro).
6. In fondo, **Commit changes**.

Nota: le cartelle `data/`, `public/`, il file `.env` e `.venv/` non vanno caricati —
sono esclusi apposta e contengono segreti o file rigenerabili.

---

## 3. I segreti del repository

Nel repository: **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**. Ne servono sei:

| Nome | Valore |
|---|---|
| `TG_API_ID` | il numero di my.telegram.org |
| `TG_API_HASH` | la stringa di my.telegram.org |
| `TG_SESSION_STRING` | vedi sotto |
| `DATABASE_URL` | la connection string di Neon |
| `ANTHROPIC_API_KEY` | la chiave per le traduzioni (console.anthropic.com) |
| `FTP_USER` | utente FTP dello spazio Aruba |
| `FTP_PASSWORD` | password FTP dello spazio Aruba |

**La sessione portabile** (`TG_SESSION_STRING`) serve perché GitHub possa collegarsi
a Telegram senza chiedere il codice ogni volta. Si genera una volta sola sul tuo
computer con il file **GENERA SESSIONE CLOUD.bat** sul Desktop: stampa una stringa
lunga da incollare nel segreto. Trattala come una password: chi ce l'ha entra
nel tuo Telegram.

---

## 4. Il primo trasloco dell'archivio

I 28 articoli già importati stanno nel file locale. Per portarli su Neon, dal
computer: apri `config.yaml`, metti `tipo: "postgres"` nella sezione `database`,
aggiungi `DATABASE_URL` nel file `.env`, poi lancia

```
.\.venv\Scripts\python.exe run.py migra
```

Da quel momento locale e cloud lavorano sullo stesso archivio.

---

## 5. Accensione

Nel repository, scheda **Actions** → il workflow *Aggiorna Mondo Multipolare* →
**Run workflow** per la prima esecuzione manuale. Da lì in poi parte da solo
ogni 15 minuti: importa i nuovi post, li traduce nelle sei lingue, rigenera le
sette versioni del sito e carica su mondomultipolare.it solo i file cambiati.

Se un'esecuzione fallisce, GitHub ti manda una mail e nella scheda Actions trovi
il registro completo.
