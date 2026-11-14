#!/bin/bash
# HTTPS pour un Odoo installé directement sur la machine, sans Docker : installe le service de
# redirection HTTP vers HTTPS puis configure Tailscale Serve (voir ../tailscale_https.sh).
#
# Usage : install_https.sh [https://machine.tailnet.ts.net]
# Sans argument, l'adresse est le nom Tailscale de la machine.
#
# Il reste ensuite à régler Odoo (voir ../README.md) : proxy_mode = True et http_interface = 127.0.0.1
# dans odoo.conf, puis les paramètres système web.base.url, web.base.url.freeze et report.url.
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
[ "$(id -u)" = 0 ] || { echo "À lancer en root." >&2; exit 1; }
URL="${1:-}"
if [ -z "$URL" ]; then
    name="$(tailscale status --json | python3 -c 'import json, sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
    URL="https://$name"
fi
[[ "$URL" =~ ^https://[A-Za-z0-9.-]+$ ]] || { echo "Adresse invalide : $URL" >&2; exit 1; }

install -d -m 755 /usr/local/lib/odoo-https
install -m 644 "$HERE/../redirect_https.py" /usr/local/lib/odoo-https/redirect_https.py
printf 'HTTPS_URL=%s\nREDIRECT_PORT=%s\n' "$URL" "${REDIRECT_PORT:-8068}" > /etc/odoo-https-redirect.env
install -m 644 "$HERE/odoo-https-redirect.service" /etc/systemd/system/odoo-https-redirect.service
systemctl daemon-reload
systemctl enable --now odoo-https-redirect.service
systemctl restart odoo-https-redirect.service
"$HERE/../tailscale_https.sh"
echo "Odoo est publié sur $URL"
