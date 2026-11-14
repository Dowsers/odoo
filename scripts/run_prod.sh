#!/bin/bash
# Lance Odoo en production sous Docker.
#
# Usage : scripts/run_prod.sh [commande]
#   start    (défaut) construit l'image si elle manque, démarre PostgreSQL, Odoo et la redirection,
#            attend qu'Odoo réponde, puis publie l'adresse HTTPS par Tailscale
#   stop     arrête les conteneurs ; les données restent dans les volumes
#   restart  redémarre Odoo
#   update   reconstruit l'image à partir des sources puis relance Odoo
#   status   état des conteneurs et de la publication HTTPS
#   logs     journal d'Odoo en continu (Ctrl+C pour quitter)
#
# Réglages et mots de passe : fichier .env à la racine du dépôt (voir .env.example).
# Après un redémarrage de la machine, Docker relance seul les conteneurs.
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")/.."

die() { echo "ERREUR : $*" >&2; exit 1; }
command -v docker > /dev/null || die "Docker n'est pas installé."
docker compose version > /dev/null 2>&1 || die "Le plugin « docker compose » n'est pas installé."
[ -f .env ] || die "Fichier .env absent : copier .env.example vers .env et remplacer les valeurs."

https_url() { sed -n 's/^HTTPS_URL=//p' .env | tail -1 | tr -d "\"'"; }

publish_https() {
    if command -v tailscale > /dev/null; then
        docker/tailscale_https.sh > /dev/null
        echo "Odoo est publié sur $(https_url)"
    else
        echo "Tailscale n'est pas installé : Odoo répond seulement sur http://127.0.0.1:8069 de cette machine."
    fi
}

start() {
    docker compose config -q
    if [ "${1:-}" = build ] || ! docker image inspect odoowsers/odoo:19.0 > /dev/null 2>&1; then
        docker compose build
    fi
    if ! docker compose up -d --wait; then
        docker compose ps
        docker compose logs --tail 30 odoo
        die "Odoo n'a pas démarré correctement : voir le journal ci-dessus."
    fi
    publish_https
    docker compose ps --format 'table {{.Service}}\t{{.Status}}'
}

case "${1:-start}" in
    start) start ;;
    update) start build ;;
    stop) docker compose stop ;;
    restart) docker compose restart odoo && docker compose up -d --wait odoo ;;
    status)
        docker compose ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}'
        if command -v tailscale > /dev/null; then tailscale serve status; fi
        ;;
    logs) docker compose logs -f --tail 100 odoo ;;
    -h|--help|help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//' ;;
    *) die "commande inconnue : $1 (start, stop, restart, update, status, logs)" ;;
esac
