#!/bin/bash
# Point d'entrée de l'image Odoo : écrit la configuration à partir de l'environnement, attend
# PostgreSQL, puis lance la commande demandée (par défaut « odoo server »).
#
# Variables : DB_HOST (db), DB_PORT (5432), DB_USER (odoo), DB_PASSWORD, DB_NAME (database),
# ODOO_ADMIN_PASSWD. DB_PASSWORD_FILE et ODOO_ADMIN_PASSWD_FILE lisent la valeur dans un fichier
# (secrets Docker). ODOO_SKIP_DB_WAIT=1 n'attend pas PostgreSQL.
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
export ODOO_RC="${ODOO_RC:-/etc/odoo/odoo.conf}"
export DB_HOST="${DB_HOST:-db}" DB_PORT="${DB_PORT:-5432}" DB_USER="${DB_USER:-odoo}" DB_NAME="${DB_NAME:-database}"

# VAR ou VAR_FILE, jamais les deux
read_secret() {
    local name="$1" file_var="$1_FILE"
    if [ -n "${!file_var:-}" ]; then
        [ -z "${!name:-}" ] || { echo "$name et $file_var sont tous deux définis." >&2; exit 1; }
        [ -r "${!file_var}" ] || { echo "$file_var : fichier illisible." >&2; exit 1; }
        export "$name=$(< "${!file_var}")"
    fi
    [ -n "${!name:-}" ] || { echo "Variable $name manquante (voir .env.example)." >&2; exit 1; }
    case "${!name}" in *$'\n'*) echo "$name ne doit pas contenir de saut de ligne." >&2; exit 1 ;; esac
}
read_secret DB_PASSWORD
read_secret ODOO_ADMIN_PASSWD

# Le fichier contient des mots de passe : lisible par l'utilisateur du conteneur seulement.
umask 077
python3 - "$HERE/odoo.conf.template" "$ODOO_RC" <<'PY'
import os
import string
import sys

template, target = sys.argv[1:3]
names = ('DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME', 'ODOO_ADMIN_PASSWD')
with open(template, encoding='utf-8') as source:
    content = string.Template(source.read()).substitute({name: os.environ[name] for name in names})
with open(target, 'w', encoding='utf-8') as output:
    output.write(content)
PY

if [ "${ODOO_SKIP_DB_WAIT:-0}" != 1 ]; then
    python3 "$HERE/wait-for-psql.py"
fi

exec "$@"
