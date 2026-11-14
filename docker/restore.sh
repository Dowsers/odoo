#!/bin/bash
# Charge une sauvegarde Odoo (fichier .zip de DB_RECOVERY) dans la pile Docker.
#
# Usage : docker/restore.sh [-n] [-f] <sauvegarde.zip> [base]
#   -n  copie de test neutralisée : pas d'e-mails envoyés, actions planifiées désactivées
#   -f  remplace la base si elle existe déjà (elle est alors supprimée, avec son filestore)
# La base s'appelle « database » par défaut. Sert à la migration et à la reprise après sinistre.
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")/.."
options=()
while [ "${1:-}" = "-n" ] || [ "${1:-}" = "-f" ]; do
    options+=("$1")
    shift
done
archive="${1:-}"
database="${2:-database}"
[ -n "$archive" ] && [ -f "$archive" ] || { sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 1; }
[[ "$database" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "Nom de base invalide : $database" >&2; exit 1; }
archive="$(readlink -f "$archive")"

docker compose up -d --wait db
# Odoo ne doit pas utiliser la base pendant le chargement.
docker compose stop odoo
docker compose run --rm --no-deps -T -v "$archive:/restore/backup.zip:ro" odoo \
    odoo db load "${options[@]}" "$database" /restore/backup.zip
echo "Base « $database » restaurée. Démarrer Odoo : docker compose up -d"
