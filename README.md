# Mondo Multipolare — dal canale Telegram al sito

Automazione che legge i post del canale [@mondomultipolare](https://t.me/mondomultipolare) e li pubblica come articoli
su un sito di informazione statico, con grafica editoriale (homepage con apertura,
pagine articolo, archivio, ricerca, feed RSS, tema chiaro/scuro).

**Copia fedele:** il testo italiano viene trasferito così com'è, con grassetti, corsivi,
link, citazioni e media. Nessuna riscrittura.

**Sette lingue:** italiano (originale) più inglese, russo, cinese, spagnolo, francese e tedesco,
tradotti automaticamente con l'API di Claude e pubblicati in sottocartella (`/en/`, `/ru/`, `/zh/`…).

**Attribuzione:** le testate accreditate (a partire da L'AntiDiplomatico) vengono riconosciute
in automatico e l'articolo si apre con "Pubblicato in origine su…" e il link al pezzo originale;
gli altri repost portano il canale di provenienza, e ogni link esterno finisce nell'elenco delle
fonti citate. Sulle versioni tradotte compare l'avviso di traduzione automatica con il rimando
all'originale italiano.

---

## 1. Come funziona

```
canale Telegram ──▶ ingest ──▶ archivio ──▶ traduci ──▶ build ──▶ pubblica ──▶ sito online
   (italiano)     (Telethon)  (Neon/SQLite) (Claude)   (Jinja2)     (FTP)      7 lingue
```

* **ingest** — si collega a Telegram, scarica i post nuovi (e, al primo avvio, lo storico),
  salva testo, formattazione, media e link originale. Riconosce le modifiche ai post già
  pubblicati e gli album di più foto.
* **traduci** — traduce titolo e corpo di ogni articolo nelle lingue attive, conservando
  grassetti, corsivi e link. Ogni traduzione è salvata: si paga una volta sola, e si rifà
  solo se il post italiano viene modificato.
* **build** — genera un sito statico completo: HTML, immagini, feed RSS, sitemap, robots.txt.
  Nessun database da amministrare, nessun WordPress da aggiornare, nessuna superficie di attacco.
* **pubblica** — carica sullo spazio web solo i file cambiati; il registro di ciò che è già
  online sta nell'archivio, quindi l'automazione può girare su una macchina diversa ogni volta.
* **public/** — è il sito. Lo puoi caricare ovunque: spazio Aruba, un server tuo, Netlify.

---

## 2. Installazione (10 minuti)

### 2.1 Requisiti

Python 3.10 o superiore.

**Windows (PowerShell)** — c'è uno script che fa tutto:

```powershell
cd C:\percorso\mondomultipolare-sito
powershell -ExecutionPolicy Bypass -File .\scripts\installa-windows.ps1
```

Controlla Python, crea l'ambiente virtuale, installa le dipendenze, prepara `config.yaml` e
`.env` e genera un sito di esempio. Poi ogni comando si lancia così, senza attivare nulla:

```powershell
.\.venv\Scripts\python.exe run.py serve
.\.venv\Scripts\python.exe run.py ingest --giorni 2
.\.venv\Scripts\python.exe run.py aggiorna
```

Se preferisci fare a mano:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config.example.yaml config.yaml
Copy-Item .env.example .env
notepad .env
```

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml && cp .env.example .env
```

### 2.2 Credenziali Telegram

1. Vai su **https://my.telegram.org** → *API development tools*.
2. Crea un'applicazione (nome e piattaforma qualsiasi).
3. Annota **api_id** e **api_hash**.

Copia `.env.example` in `.env` e compilalo:

```
TG_API_ID=1234567
TG_API_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TG_PHONE=+39...
```

> Si usa il tuo account Telegram (non un bot): è l'unico modo per leggere anche lo
> **storico** del canale. Il file `.env` e il file di sessione non vanno mai condivisi
> né caricati su un repository pubblico.

### 2.3 Configurazione del sito

`config.example.yaml` è già compilato per Mondo Multipolare (canale `@mondomultipolare`,
dominio `www.mondomultipolare.it`). Copialo in `config.yaml` e ritocca solo quello che vuoi
cambiare — per esempio il sottotitolo della testata:

```yaml
site:
  tagline: "Notizie e analisi da un mondo che cambia equilibri"
```

### 2.3-bis Il database

In locale conviene lavorare su file:

```yaml
database:
  tipo: "sqlite"
```

In produzione si passa a Neon mettendo `tipo: "postgres"` e la connection string in `.env`
(`DATABASE_URL`). Il passaggio da uno all'altro è `python run.py migra`.

### 2.4 Primo avvio

```bash
python run.py demo       # crea 12 articoli finti: serve solo a vedere la grafica
python run.py serve      # anteprima su http://localhost:8000
```

Quando la grafica ti convince, cancella `data/canale.sqlite3` e `public/`, poi:

```bash
python run.py aggiorna   # primo login Telegram (codice via app) + generazione del sito
python run.py serve
```

Al primo avvio Telegram invia un codice di verifica; se hai la verifica in due passaggi,
chiede anche la password. Succede **una volta sola**: la sessione resta salvata in `data/`.

---

## 3. Uso quotidiano

| Comando | Cosa fa |
|---|---|
| `python run.py aggiorna` | importa i nuovi post e rigenera il sito — **è il comando da schedulare** |
| `python run.py ingest --giorni 2` | importa solo i post di ieri e oggi (utile al primo avvio o per recuperare una finestra) |
| `python run.py watch` | resta in ascolto: ogni post pubblicato sul canale compare sul sito in pochi secondi |
| `python run.py build` | rigenera solo il sito (dopo aver cambiato grafica o configurazione) |
| `python run.py pubblica` | carica su www.mondomultipolare.it via FTP solo i file cambiati (`--tutto` ricarica tutto) |
| `python run.py stato` | quanti articoli ci sono, ultimo post importato, ultima esecuzione |
| `python run.py approva` | elenca i post in bozza; `approva 123 456` li pubblica |
| `python run.py serve` | anteprima locale |
| `python run.py traduci` | traduce gli articoli non ancora tradotti (`--simulato` prova senza chiave) |
| `python run.py prova-traduzione en` | verifica chiave e modello traducendo una frase |
| `python run.py sessione` | genera la sessione portabile per l'esecuzione nel cloud |
| `python run.py migra` | copia l'archivio locale SQLite dentro il database configurato (Neon) |

### Controllo editoriale

In `config.yaml`, sezione `publishing`:

* `mode: auto` — tutto ciò che pubblichi sul canale finisce online (default).
* `mode: draft` — i post arrivano in bozza e vanno approvati con `run.py approva`.
* `blocklist` — parole che escludono un post (es. avvisi di servizio, promozioni).
* `allowlist` — se valorizzata, pubblica **solo** i post che contengono quelle parole.
* `min_length` — scarta i messaggi troppo brevi.

I temi geopolitici (Medio Oriente, Ucraina, Russia, Cina, USA, Europa, Africa, Economia)
vengono riconosciuti dalle parole nel testo e diventano etichette e filtri in homepage.
L'elenco si modifica in `tgsite/build.py`, dizionario `TEMI`.

---

## 3.bis Le sette lingue

`config.yaml`:

```yaml
lingue:
  sorgente: "it"
  attive: ["it", "en", "ru", "zh", "es", "fr", "de"]
  modello: "claude-sonnet-4-5"
```

`.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

L'italiano resta nella radice del sito; ogni altra lingua vive in sottocartella
(`/en/`, `/ru/`, `/zh/`, `/es/`, `/fr/`, `/de/`) con la propria homepage, il proprio archivio,
il proprio feed RSS e la propria ricerca. Nella testata compare il selettore di lingua: dentro
un articolo porta allo stesso articolo nell'altra lingua, non alla homepage.

Ogni pagina dichiara ai motori di ricerca le versioni parallele (`hreflang`), e la sitemap le
elenca tutte: Google mostra la versione giusta a seconda del Paese di chi cerca.

**Costi.** Si paga solo la prima traduzione di ogni articolo: un post medio costa qualche
centesimo per tutte e sei le lingue. Un post modificato sul canale viene ritradotto, un post
invariato mai. Per una prova a vuoto: `python run.py traduci --simulato` (nessuna chiamata,
nessun costo), e per verificare la chiave: `python run.py prova-traduzione ru`.

**Aggiungere o togliere una lingua** significa cambiare l'elenco `attive` e rilanciare
`python run.py aggiorna`. Le lingue disponibili nel sistema sono it, en, ru, zh, es, fr, de.

---

## 3.ter Fonti e attribuzione

Il sistema tratta la provenienza come parte del contenuto, non come un dettaglio.

### Testate accreditate

In `config.yaml` si dichiarano le testate da cui riprendi materiale:

```yaml
fonti:
  etichetta_predefinita: "ripreso_da"
  partner:
    - nome: "L'AntiDiplomatico"
      sito: "https://www.lantidiplomatico.it"
      telegram: "lantidiplomatico"
      etichetta: "pubblicato_in_origine"
```

Il riconoscimento avviene in due modi, entrambi automatici:

1. **Repost Telegram** — se inoltri un messaggio dal canale della testata, l'articolo apre con
   *"Pubblicato in origine su L'AntiDiplomatico"*, il nome porta al sito e a fianco compare il
   link al messaggio originale.
2. **Link nel testo** — se il post contiene un link a `lantidiplomatico.it`, il credito compare
   lo stesso e il link diventa *"leggi sulla testata"*, che porta all'articolo preciso. Il
   dominio della testata accreditata non viene ripetuto tra le fonti citate.

Le etichette disponibili sono `pubblicato_in_origine`, `in_collaborazione` e `ripreso_da`: si
sceglie per singola testata, e vale in tutte e sette le lingue (*Originally published on*,
*Первоначально опубликовано в*, *原载于*, *Publicado originalmente en*, *Publié à l'origine sur*,
*Ursprünglich veröffentlicht bei*).

Le fonti non dichiarate come partner mantengono l'etichetta predefinita: un repost da un canale
qualsiasi resta *"Ripreso da <nome del canale>"*, con il link se il canale è pubblico.

### Le altre attribuzioni

* **Fonti citate** — ogni altro link esterno del post diventa una voce dell'elenco in fondo
  all'articolo, con il nome del dominio.
* **Rimando al canale** — sotto ogni articolo resta il link al post originale su Telegram.
* **Versioni tradotte** — in testa compare "Traduzione automatica dall'italiano" con il link
  all'originale, così il lettore sa sempre che sta leggendo una traduzione di macchina.
* **Feed RSS** — il tag `<source>` di ogni articolo riporta la testata di provenienza.

### Due accortezze pratiche

Il consenso della testata copre la ripubblicazione, comprese le traduzioni: vale la pena
metterlo per iscritto (anche solo una mail) e conservarlo, indicando se copre anche le versioni
in altre lingue — è la domanda che tornerà se un domani un pezzo viene ripreso da terzi.

Se un articolo esce prima sulla testata partner e poi qui, l'indirizzo canonico che dichiari a
Google resta quello di questo sito. Se preferisci attribuire il peso SEO all'originale, si può
aggiungere un `canonical` verso l'articolo della testata: chiedimelo e lo abilito per le sole
fonti che vuoi.

---

## 4. Architettura e messa online

Il sistema è pensato per lo stesso schema che usate per gli altri siti: **dominio su Aruba,
database gestito su Neon, nessun server da amministrare.**

```
     Telegram
        │
        ▼
   run.py aggiorna ──▶ Neon (PostgreSQL)      ← archivio: post, traduzioni, registro
        │                    ▲
        │  legge e scrive ───┘
        ▼
    public/ (sito statico, 7 lingue) ──FTP──▶ spazio web Aruba ──▶ mondomultipolare.it
```

L'automazione non conserva niente in locale: tutto lo stato (ultimo messaggio importato,
traduzioni già fatte, file già caricati) sta su Neon. Può quindi girare ovunque — GitHub
Actions, un cron su Render, il vostro computer — e cambiare macchina senza perdere il filo.

Il sito resta **statico**: nessun PHP e nessuna connessione al database dal web server, quindi
niente da attaccare e niente da aggiornare sullo spazio Aruba. Il database serve alla
redazione (l'archivio dei contenuti, le traduzioni, la memoria del sistema), non alla
consegna delle pagine.

### 4.1 Configurazione

`config.yaml`:

```yaml
database:
  tipo: "postgres"      # sqlite per lavorare in locale

deploy:
  tipo: "ftps"
  host: "ftp.mondomultipolare.it"
  cartella_remota: "/www"
```

`.env` (o i segreti del runner):

```
DATABASE_URL=postgresql://…@ep-xxx.eu-central-1.aws.neon.tech/mondomultipolare?sslmode=require
ANTHROPIC_API_KEY=sk-ant-…
TG_API_ID=…
TG_API_HASH=…
FTP_USER=…
FTP_PASSWORD=…
```

Su Neon basta creare il progetto e copiare la *connection string* (con `sslmode=require`):
le tabelle vengono create da sole al primo avvio. Il piano gratuito è ampiamente sufficiente —
l'archivio di un anno di pubblicazione sta in poche decine di MB, e le immagini non stanno nel
database ma sul sito.

### 4.2 Dove gira l'automazione

**GitHub Actions (consigliato)** — `.github/workflows/aggiorna-sito.yml` è già pronto: parte
ogni 15 minuti, importa, traduce, genera e pubblica, e scrive un riepilogo nella scheda Actions.
Nessuna macchina da tenere accesa. Servono sei segreti nel repository
(*Settings → Secrets and variables → Actions*): `TG_API_ID`, `TG_API_HASH`, `TG_SESSION_STRING`,
`DATABASE_URL`, `ANTHROPIC_API_KEY`, `FTP_USER`, `FTP_PASSWORD`.

La sessione Telegram portabile si genera una volta sola, in locale:

```bash
python run.py sessione     # chiede il codice via app, stampa la stringa da incollare nel segreto
```

**Render** — se preferite restare dove già siete: un Cron Job con lo stesso comando
`python run.py aggiorna` e le stesse variabili d'ambiente.

**In locale** — durante le prove conviene `database.tipo: sqlite`: si lavora su un file, senza
toccare l'archivio di produzione. Quando il risultato convince:

```bash
python run.py migra        # copia l'archivio locale dentro Neon
```

### 4.3 Primo avvio, nell'ordine

```bash
pip install -r requirements.txt
python run.py prova-traduzione en    # verifica la chiave di traduzione
python run.py aggiorna               # login Telegram, importa, traduce, genera, pubblica
```

Poi su Aruba: il dominio deve puntare allo spazio web (già così), e la cartella `/www` deve
essere quella servita. Se c'è una pagina di cortesia o un vecchio `index.php`, va rimosso,
altrimenti ha la precedenza sul nuovo `index.html`.

### 4.4 L'archivio su Neon

Tre tabelle, leggibili con qualsiasi client SQL o dalla console di Neon:

| tabella | contenuto |
|---|---|
| `posts` | i post del canale: testo, formattazione, media, provenienza, stato editoriale |
| `translations` | le versioni tradotte, una riga per articolo e lingua |
| `state`, `pubblicati` | memoria di servizio: ultimo messaggio importato, file già online |

Neon fa da sé i backup e permette di tornare indietro nel tempo (branching e point-in-time
recovery). Per una copia locale: `python run.py migra` funziona anche al contrario, indicando
il file di destinazione.

### 4.5 Altre configurazioni possibili

In `config.yaml`, sezione `deploy`, quattro possibilità:

| `tipo` | Quando usarlo |
|---|---|
| `nessuno` | il web server punta direttamente alla cartella `public/` del progetto: non serve copiare nulla |
| `locale` | il sito viene copiato in un'altra cartella dello stesso computer o NAS (es. `/volume1/web/mondomultipolare`), servita da nginx o Web Station |
| `rsync` | l'automazione gira su una macchina e il sito vive su un'altra: sincronizzazione via SSH, solo le differenze |
| `ftp` / `ftps` | spazio web di terzi, con credenziali in `.env` |

Esempio per un NAS o un VPS che serve il sito da sé:

```yaml
deploy:
  tipo: "locale"
  cartella_remota: "/volume1/web/mondomultipolare"
```

Esempio con automazione in casa e server altrove:

```yaml
deploy:
  tipo: "rsync"
  host: "185.x.x.x"
  utente: "mario"
  chiave_ssh: "~/.ssh/id_ed25519"
  cartella_remota: "/var/www/mondomultipolare"
```

### 4.6 Se un domani volete un server vostro

* **NAS Synology** — Web Station, host virtuale sul dominio, cartella radice `public/`
  (o quella di `cartella_remota`), certificato HTTPS Let's Encrypt dal pannello DSM.
* **VPS Linux** — nginx con un blocco `server` minimo:

```nginx
server {
    server_name mondomultipolare.it www.mondomultipolare.it;
    root /var/www/mondomultipolare;
    index index.html;
    location / { try_files $uri $uri/ $uri.html =404; }
    # cache lunga per immagini e asset, breve per l'HTML
    location ~* \.(jpg|jpeg|png|webp|mp4|css|js)$ { expires 30d; }
}
```

  Poi `certbot --nginx` per l'HTTPS. Il DNS del dominio va puntato all'IP del server.

### 4.7 Schedulazione su una macchina propria

* **Linux / NAS** — `crontab -e` e una riga: `*/15 * * * * /percorso/scripts/aggiorna.sh`
* **Windows** — `scripts/aggiorna.bat` nell'Utilità di pianificazione
* **Tempo reale** — in alternativa `python run.py watch` come servizio systemd: ogni post
  pubblicato sul canale compare online in pochi secondi, senza aspettare il quarto d'ora.

Esempio di servizio systemd:

```ini
[Unit]
Description=Mondo Multipolare — dal canale Telegram al sito
After=network-online.target

[Service]
WorkingDirectory=/opt/mondomultipolare
ExecStart=/opt/mondomultipolare/.venv/bin/python run.py watch
Restart=always
User=mario

[Install]
WantedBy=multi-user.target
```

### 4.8 Note sull'archivio locale

`data/canale.sqlite3` è la memoria del sistema: testi, formattazione, traduzioni, provenienza.
Sta su una macchina tua, si copia con un backup di file e si legge con qualsiasi client SQLite.
Le tabelle sono tre: `posts` (i post del canale), `translations` (le versioni tradotte),
`state` (l'ultimo messaggio importato). Se un domani vorrai un sito dinamico con un database
SQL, quell'archivio è già la fonte da cui migrare.

## 5. Foto, video e ricerca

### Le fotografie e i video

Vengono presi in automatico, non resta solo il testo. Per ogni post il sistema scarica foto,
video, audio e documenti allegati e li ripubblica sul sito: la prima foto diventa l'immagine di
apertura dell'articolo e l'anteprima nelle liste, le altre formano la galleria in fondo al pezzo.
Un album di più foto pubblicato su Telegram resta un unico articolo con tutte le immagini.

* **Ottimizzazione** — le foto vengono ridimensionate (lato lungo 1600 px), ricompresse e
  affiancate da una miniatura da 800 px usata nelle anteprime: una foto da 4 MB scende
  tipicamente sotto i 300 KB. I metadati EXIF vengono rimossi. Serve Pillow
  (`pip install Pillow`), già incluso in `requirements.txt`; senza, le immagini restano
  all'originale e il sistema continua a funzionare.
* **Ingrandimento** — un clic sulla foto la apre a tutto schermo, Esc per chiudere.
* **Video e audio** — vengono pubblicati con il lettore del browser. Sono i file che pesano:
  `telegram.max_media_mb` (50 MB di default) è il limite oltre il quale un allegato viene
  saltato; l'articolo esce comunque, con il testo e il rimando al canale.
* **Spazio** — regola pratica: un post con foto occupa 200-400 KB, uno con video da 20 MB
  occupa 20 MB. Con 10 post al giorno di solo testo e foto si sta sotto i 2 GB l'anno.

Le impostazioni stanno in `config.yaml`:

```yaml
media:
  ottimizza: true
  larghezza_massima: 1600
  larghezza_miniatura: 800
  qualita: 82
```

### La ricerca

Il sito ha una **pagina di ricerca** (`/cerca.html`, e `/en/cerca.html`, `/ru/cerca.html`… per
ogni lingua) raggiungibile dal menu, più una ricerca rapida che si apre dall'icona in alto o
premendo `/` da qualsiasi pagina.

Funziona senza database e senza servizi esterni: alla generazione del sito viene creato un
indice (`ricerca.json`) con titolo, estratto, data, temi e miniatura di ogni articolo, e la
ricerca avviene nel browser del lettore. Cerca più parole insieme (tutte devono comparire),
ignora accenti e maiuscole, evidenzia le parole trovate nei risultati e permette di filtrare
per tema. Ogni lingua ha il proprio indice, quindi chi legge in russo cerca fra i testi russi.

L'indirizzo porta con sé la ricerca (`/cerca.html?q=sanzioni`): è un link condivisibile.

---

## 5.bis Il logo della testata

Il logo del sito è l'immagine del canale Telegram: si scarica con

```bash
python run.py logo
```

Il comando prende l'avatar di @mondomultipolare, lo ritaglia quadrato e ne ricava il logo
tondo della testata (512 px), l'icona per iOS (180 px) e le favicon (32 e 16 px), poi rigenera
il sito. Se un giorno cambi l'immagine del canale, basta rilanciarlo.

Nella testata l'emblema sta sopra il logotipo tipografico, in tondo; nel piè di pagina appare
in piccolo accanto al nome. Per toglierlo: `logo: false` nella sezione `site` di `config.yaml`.

---

## 6. Personalizzare la grafica

* `static/style.css` — colori, font e spaziature sono tutti in cima, nel blocco `:root`
  (e nel blocco `[data-theme="dark"]` per il tema scuro). Cambiando `--accent` cambi
  l'identità cromatica di tutto il sito.
* `templates/` — struttura delle pagine: `base.html` (testata e piede), `index.html`
  (homepage), `post.html` (articolo), `archivio.html`.
* Il logo testuale è il `site.title` in `config.yaml`. Per un logo grafico, sostituisci
  il contenuto di `.wordmark` in `templates/base.html` con un `<img>`.

Dopo ogni modifica: `python run.py build`.

---

## 7. Aspetti legali (importante per una testata)

* Se ripubblichi contenuti di terzi presi dal canale, il diritto d'autore resta di chi li ha
  prodotti: il sito conserva il link al post originale e l'eventuale indicazione della fonte
  inoltrata, ma la responsabilità editoriale di ciò che pubblichi è tua.
* In Italia una testata giornalistica online periodica può richiedere registrazione al
  Tribunale e direttore responsabile: verifica la tua posizione con un legale prima di
  presentarti come testata.
* Servono privacy policy e cookie policy. Questo sito non usa cookie né tracciamenti:
  l'unico dato salvato nel browser è la preferenza di tema chiaro/scuro.

---

## 8. Struttura dei file

```
config.yaml            configurazione del sito, del canale e della pubblicazione FTP
.env                   credenziali Telegram (mai condividere)
run.py                 comandi: ingest, build, aggiorna, watch, serve, stato, approva
tgsite/
  config.py            caricamento configurazione
  ingest.py            lettura dal canale Telegram
  store.py             archivio dei post: SQLite in locale, PostgreSQL/Neon in produzione
  entities.py          conversione fedele del testo Telegram in HTML
  build.py             generazione del sito in tutte le lingue
  translate.py         traduzione automatica con l'API di Claude
  i18n.py              etichette dell'interfaccia e formati di data per lingua
  deploy.py            pubblicazione del sito (cartella locale, rsync/SSH, FTP)
scripts/installa-windows.ps1 installazione su Windows con PowerShell
scripts/installa-server.sh   installazione completa su un VPS Debian/Ubuntu
  media.py             ottimizzazione di foto, miniature e logo
templates/             pagine HTML
static/                foglio di stile e interazioni
data/canale.sqlite3    archivio dei post (la memoria del sistema)
public/                il sito generato, pronto da pubblicare
scripts/               script per la schedulazione (Windows e Linux/NAS)
```

---

## 9. Problemi frequenti

**"Manca il file di configurazione"** — copia `config.example.yaml` in `config.yaml`.

**Chiede di nuovo il codice Telegram** — il file di sessione in `data/` è stato cancellato o
spostato. Rifai il login una volta.

**Nessun post importato** — controlla che `telegram.channel` sia lo username giusto (con la @)
e che l'account usato veda quel canale.

**Le immagini non si vedono** — `public/media/` deve essere pubblicato insieme al resto del
sito: è una sottocartella di `public/`, quindi basta caricare tutta la cartella.

**L'FTP si ferma o dà errore di permessi** — verifica `cartella_remota` (su Aruba spesso `/www`)
e prova `tipo: "ftp"` se lo spazio non supporta FTPS. Per rispedire tutto: `python run.py pubblica --tutto`.

**La traduzione si ferma con un errore sul modello** — cambia `lingue.modello` in `config.yaml`;
il sistema prova comunque alcuni modelli di ripiego prima di arrendersi.

**Voglio ritradurre tutto da capo** — svuota la tabella delle traduzioni:
`sqlite3 data/canale.sqlite3 "DELETE FROM translations"` e rilancia `python run.py traduci`.

**Voglio ripartire da zero** — cancella `data/canale.sqlite3` e `public/`, poi `run.py aggiorna`.
