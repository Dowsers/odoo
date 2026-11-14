#!/bin/bash
# Publie Odoo en HTTPS sur le nom Tailscale de cette machine (https://<machine>.<tailnet>.ts.net).
#
# Tailscale Serve termine le HTTPS : il obtient et renouvelle seul le certificat. Les ports HTTP
# indiqués (80 et l'ancien port 8069 par défaut) sont envoyés au service de redirection, qui renvoie
# vers l'adresse HTTPS. La configuration est conservée par Tailscale après un redémarrage.
# Le script peut être relancé sans risque. Pour tout annuler : tailscale serve reset
#
# Variables : ODOO_PORT (8069), REDIRECT_PORT (8068), HTTP_PORTS ("80 8069").
set -euo pipefail

ODOO_PORT="${ODOO_PORT:-8069}"
REDIRECT_PORT="${REDIRECT_PORT:-8068}"
HTTP_PORTS="${HTTP_PORTS:-80 8069}"

command -v tailscale > /dev/null || { echo "Tailscale n'est pas installé sur cette machine." >&2; exit 1; }
tailscale serve --bg --yes --https=443 "http://127.0.0.1:${ODOO_PORT}"
for port in $HTTP_PORTS; do
    tailscale serve --bg --yes --http="$port" "http://127.0.0.1:${REDIRECT_PORT}"
done
tailscale serve status
