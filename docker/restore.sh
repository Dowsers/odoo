#!/bin/bash
# Charge une sauvegarde Odoo (fichier .zip de DB_RECOVERY) dans la pile Docker.
#
# Usage : docker/restore.sh [-n] [-f] <sauvegarde.zip> [base]
#   -n  copie de test neutralisée : nouvel identifiant de base, pas d'e-mails envoyés, actions
#       planifiées désactivées
#   -f  remplace la base si elle existe déjà (elle est alors supprimée, avec son filestore)
# Sans -n, la base est restaurée à l'identique (identifiant, clé secrète, adresse) : c'est le mode de
# la migration et de la reprise après sinistre. La base s'appelle « database » par défaut.
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")/.."
options=()
while [ "${1:-}" = "-n" ] || [ "${1:-}" = "-f" ]; do
    if [ "$1" = "-n" ]; then options+=(--neutralize); else options+=(--force); fi
    shift
done
archive="${1:-}"
database="${2:-database}"
[ -n "$archive" ] && [ -f "$archive" ] || { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 1; }
[[ "$database" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "Nom de base invalide : $database" >&2; exit 1; }
[ -r "$archive" ] || { echo "Archive illisible : $archive" >&2; exit 1; }

docker compose up -d --wait db
# Odoo ne doit pas utiliser la base pendant le chargement.
docker compose stop odoo
# L'archive est envoyée au conteneur par l'entrée standard : un fichier réservé à root sur la machine
# hôte ne serait pas lisible par l'utilisateur odoo du conteneur.
docker compose run --rm --no-deps -T odoo sh -c \
    'cat > /tmp/backup.zip && exec python3 /opt/odoo/docker/restore_db.py "$@" /tmp/backup.zip' \
    restore "${options[@]}" "$database" < "$archive"
echo "Base « $database » restaurée. Démarrer Odoo : docker compose up -d"
