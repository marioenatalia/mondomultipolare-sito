# ==============================================================
#  Mondo Multipolare - installazione su Windows (PowerShell)
#
#  Uso: apri PowerShell nella cartella del progetto e lancia
#     .\scripts\installa-windows.ps1
#
#  Se PowerShell blocca lo script:
#     powershell -ExecutionPolicy Bypass -File .\scripts\installa-windows.ps1
# ==============================================================

$ErrorActionPreference = "Stop"

function Titolo($testo) { Write-Host "`n>> $testo" -ForegroundColor Cyan }
function Nota($testo)   { Write-Host "   $testo" -ForegroundColor DarkGray }

# la cartella del progetto e' quella che contiene questo script
$progetto = Split-Path -Parent $PSScriptRoot
Set-Location $progetto
Write-Host "Progetto: $progetto"

Titolo "Controllo di Python"
$python = $null
foreach ($candidato in @("py", "python", "python3")) {
    try {
        $versione = & $candidato --version 2>&1
        if ($versione -match "Python 3\.(\d+)") {
            if ([int]$Matches[1] -ge 10) { $python = $candidato; break }
            Nota "$candidato e' $versione (serve 3.10 o superiore)"
        }
    } catch { }
}
if (-not $python) {
    Write-Host "Python 3.10+ non trovato." -ForegroundColor Red
    Write-Host "Installalo da https://www.python.org/downloads/ (spunta 'Add python.exe to PATH') e rilancia."
    exit 1
}
Nota "uso $python ($(& $python --version 2>&1))"

Titolo "Ambiente virtuale"
if (-not (Test-Path ".venv")) { & $python -m venv .venv }
# si usa direttamente l'eseguibile: niente Activate.ps1, niente problemi di ExecutionPolicy
$py = Join-Path $progetto ".venv\Scripts\python.exe"
Nota "creato in .venv"

Titolo "Dipendenze"
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r requirements.txt
Nota "installate (Telethon, Jinja2, Pillow, psycopg)"

Titolo "File di configurazione"
if (-not (Test-Path "config.yaml")) {
    Copy-Item "config.example.yaml" "config.yaml"
    Nota "creato config.yaml"
} else { Nota "config.yaml gia' presente, lasciato com'e'" }

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Nota "creato .env"
    Write-Host ""
    Write-Host "Apri il file .env e inserisci:" -ForegroundColor Yellow
    Write-Host "   TG_API_ID e TG_API_HASH   (da https://my.telegram.org)"
    Write-Host "   TG_PHONE                  (il tuo numero, formato +39...)"
    Write-Host "   ANTHROPIC_API_KEY         (per le traduzioni, da console.anthropic.com)"
    Write-Host "   DATABASE_URL              (Neon; oppure metti database.tipo: sqlite in config.yaml)"
    Write-Host "   FTP_USER e FTP_PASSWORD   (spazio web Aruba, per la pubblicazione)"
    Write-Host ""
    $risposta = Read-Host "Vuoi aprire .env adesso in Blocco note? (s/n)"
    if ($risposta -eq "s") { notepad .env; Read-Host "Premi Invio quando hai salvato" }
} else { Nota ".env gia' presente, lasciato com'e'" }

Titolo "Prova senza toccare Telegram"
& $py run.py demo
Nota "sito di esempio generato nella cartella public"

Write-Host ""
Write-Host "----------------------------------------------------------" -ForegroundColor Green
Write-Host " Installazione completata. Comandi utili:" -ForegroundColor Green
Write-Host ""
Write-Host "   .\.venv\Scripts\python.exe run.py serve"
Write-Host "        anteprima su http://localhost:8000"
Write-Host ""
Write-Host "   .\.venv\Scripts\python.exe run.py ingest --giorni 2"
Write-Host "        importa i post di ieri e oggi (la prima volta chiede il codice Telegram)"
Write-Host ""
Write-Host "   .\.venv\Scripts\python.exe run.py aggiorna"
Write-Host "        importa, traduce, genera le sette lingue e pubblica"
Write-Host ""
Write-Host "   .\.venv\Scripts\python.exe run.py logo"
Write-Host "        prende l'immagine del canale e la usa come logo del sito"
Write-Host "----------------------------------------------------------" -ForegroundColor Green
