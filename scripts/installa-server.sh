#!/usr/bin/env bash
# ==============================================================
#  Mondo Multipolare — installazione su un server Debian/Ubuntu
#
#  Prepara tutto: dipendenze, cartelle, servizio in tempo reale,
#  aggiornamento periodico di riserva, nginx, backup dell'archivio.
#
#  Uso (come root, sul server appena creato):
#     bash installa-server.sh
#
#  Dopo l'installazione restano due passaggi manuali, indicati
#  in fondo: il primo login Telegram e il certificato HTTPS.
# ==============================================================
set -euo pipefail

DOMINIO="${DOMINIO:-mondomultipolare.it}"
UTENTE="${UTENTE:-multipolare}"
CARTELLA="${CARTELLA:-/opt/mondomultipolare}"

blu()  { printf "\n\033[1;34m▸ %s\033[0m\n" "$1"; }
info() { printf "  %s\n" "$1"; }

[ "$(id -u)" -eq 0 ] || { echo "Esegui come root: sudo bash $0"; exit 1; }

blu "Pacchetti di sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx sqlite3 rsync \
                      certbot python3-certbot-nginx ca-certificates curl
info "installati"

blu "Utente di servizio e cartelle"
id -u "$UTENTE" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$UTENTE"
mkdir -p "$CARTELLA"
# se lo script è stato lanciato dentro la cartella del progetto, la copia al suo posto
if [ -f "$(dirname "$0")/../run.py" ] && [ ! -f "$CARTELLA/run.py" ]; then
  cp -r "$(dirname "$0")/../." "$CARTELLA/"
  info "progetto copiato in $CARTELLA"
fi
mkdir -p "$CARTELLA/data" "$CARTELLA/public" /var/backups/mondomultipolare
chown -R "$UTENTE":"$UTENTE" "$CARTELLA" /var/backups/mondomultipolare

blu "Ambiente Python"
sudo -u "$UTENTE" python3 -m venv "$CARTELLA/.venv"
sudo -u "$UTENTE" "$CARTELLA/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "$UTENTE" "$CARTELLA/.venv/bin/pip" install --quiet -r "$CARTELLA/requirements.txt"
info "dipendenze installate"

blu "Servizio in tempo reale"
cat > /etc/systemd/system/multipolare.service <<SERVIZIO
[Unit]
Description=Mondo Multipolare - dal canale Telegram al sito
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$UTENTE
WorkingDirectory=$CARTELLA
ExecStart=$CARTELLA/.venv/bin/python run.py watch
Restart=always
RestartSec=30
# irrobustimento
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$CARTELLA

[Install]
WantedBy=multi-user.target
SERVIZIO

blu "Aggiornamento periodico di riserva"
cat > /etc/systemd/system/multipolare-aggiorna.service <<SERVIZIO
[Unit]
Description=Mondo Multipolare - importazione e rigenerazione

[Service]
Type=oneshot
User=$UTENTE
WorkingDirectory=$CARTELLA
ExecStart=$CARTELLA/.venv/bin/python run.py aggiorna
SERVIZIO

cat > /etc/systemd/system/multipolare-aggiorna.timer <<TIMER
[Unit]
Description=Mondo Multipolare - ogni 15 minuti

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min
Persistent=true

[Install]
WantedBy=timers.target
TIMER

blu "Backup dell'archivio"
cat > /etc/cron.daily/multipolare-backup <<'BACKUP'
#!/bin/sh
# copia coerente del database (funziona anche mentre il servizio scrive)
CARTELLA="/opt/mondomultipolare"
DESTINAZIONE="/var/backups/mondomultipolare"
DATA=$(date +%Y-%m-%d)
sqlite3 "$CARTELLA/data/canale.sqlite3" ".backup '$DESTINAZIONE/canale-$DATA.sqlite3'"
gzip -f "$DESTINAZIONE/canale-$DATA.sqlite3"
# conserva 30 giorni
find "$DESTINAZIONE" -name 'canale-*.sqlite3.gz' -mtime +30 -delete
BACKUP
chmod +x /etc/cron.daily/multipolare-backup
info "backup giornaliero in /var/backups/mondomultipolare (30 giorni)"

blu "nginx"
cat > /etc/nginx/sites-available/multipolare <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name $DOMINIO www.$DOMINIO;

    root $CARTELLA/public;
    index index.html;
    charset utf-8;

    # indirizzi puliti: /post/... e /en/... sono cartelle con index.html
    location / {
        try_files \$uri \$uri/ \$uri.html =404;
    }

    # l'HTML cambia a ogni post: cache breve
    location ~* \\.html\$ {
        add_header Cache-Control "public, max-age=300";
    }
    # immagini, video e asset non cambiano mai: cache lunga
    location ~* \\.(jpg|jpeg|png|webp|gif|mp4|webm|mp3|ogg|css|js|woff2)\$ {
        add_header Cache-Control "public, max-age=2592000, immutable";
        access_log off;
    }
    location = /feed.xml { add_header Cache-Control "public, max-age=600"; }

    gzip on;
    gzip_types text/html text/css application/javascript application/json application/rss+xml image/svg+xml;
    gzip_min_length 1024;

    add_header X-Content-Type-Options nosniff;
    add_header Referrer-Policy strict-origin-when-cross-origin;

    error_page 404 /404.html;
}
NGINX
ln -sf /etc/nginx/sites-available/multipolare /etc/nginx/sites-enabled/multipolare
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
info "sito servito da $CARTELLA/public"

blu "Attivazione dei servizi"
systemctl daemon-reload
systemctl enable --now multipolare-aggiorna.timer
info "timer attivo (il servizio in tempo reale si avvia dopo il primo login Telegram)"

cat <<FINE

────────────────────────────────────────────────────────────
 Restano due passaggi, da fare a mano una volta sola:

 1) Login Telegram (chiede il codice che arriva sull'app):
      cd $CARTELLA
      sudo -u $UTENTE .venv/bin/python run.py aggiorna

 2) Certificato HTTPS (il dominio deve già puntare a questo server):
      certbot --nginx -d $DOMINIO -d www.$DOMINIO

 Poi, per la pubblicazione in tempo reale:
      systemctl enable --now multipolare.service

 Comandi utili:
   systemctl status multipolare            stato del servizio
   journalctl -u multipolare -f            log in tempo reale
   systemctl list-timers multipolare*      prossimo aggiornamento
────────────────────────────────────────────────────────────
FINE
