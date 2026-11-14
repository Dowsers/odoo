# Odoo sous Docker (branche `odoowsers`)

Cette branche contient le code exact du serveur Odoo, qui tourne sous Docker depuis le 14/11/2026. Les fichiers
ci-dessous construisent l'image, lancent la production et permettent de la réinstaller sur une autre machine.

| Fichier | Rôle |
|---|---|
| `scripts/run_prod.sh` | Lance la production : construction de l'image si besoin, démarrage, publication HTTPS |
| `Dockerfile`, `.dockerignore` | Image Odoo construite à partir de cette branche |
| `docker-compose.yml` | Odoo, PostgreSQL 18 et la redirection HTTP vers HTTPS |
| `.env.example` | Modèle du fichier `.env` (mots de passe, adresse HTTPS), jamais commité |
| `docker/entrypoint.sh`, `docker/odoo.conf.template`, `docker/wait-for-psql.py` | Démarrage du conteneur : configuration écrite à partir de l'environnement, attente de PostgreSQL |
| `docker/restore.sh`, `docker/restore_db.py` | Chargement d'une sauvegarde dans la pile Docker |
| `docker/tailscale_https.sh` | Publication en HTTPS par Tailscale |
| `docker/redirect_https.py` | Redirection des anciennes adresses HTTP vers HTTPS |
| `docker/host/` | HTTPS pour un Odoo installé sans Docker |

## Lancer la production

```
scripts/run_prod.sh             # démarre tout et publie l'adresse HTTPS
scripts/run_prod.sh status      # état des conteneurs et de la publication HTTPS
scripts/run_prod.sh logs        # journal d'Odoo en continu
scripts/run_prod.sh restart     # redémarre Odoo
scripts/run_prod.sh update      # reconstruit l'image à partir des sources puis relance Odoo
scripts/run_prod.sh stop        # arrête les conteneurs ; les données restent dans les volumes
```

`run_prod.sh` vérifie `docker-compose.yml` et `.env`, construit l'image si elle manque, démarre PostgreSQL, Odoo et
la redirection, attend qu'Odoo réponde, puis configure Tailscale. Après un redémarrage de la machine, Docker relance
seul les conteneurs : aucune commande n'est nécessaire.

## Ce que l'image reproduit

| Élément | Installation d'origine (paquet Debian) | Image |
|---|---|---|
| Système, Python | Debian 12, Python 3.11 | `debian:bookworm-slim`, Python 3.11 |
| Bibliothèques Python | Paquets `python3-*` de Debian 12, `python3-psycopg2` du dépôt PGDG | Les mêmes paquets, aux mêmes versions |
| PostgreSQL | 18.7, base `database`, collation C | `postgres:18` (18.7), base restaurée à l'identique |
| wkhtmltopdf | 0.12.6 de Debian | Le même paquet |
| Code Odoo et modules | Paquet Debian 19.0.20260128 modifié à la main | Cette branche, qui en est la copie |
| Configuration | `db_name = database`, sans workers, `proxy_mode` | Identique |

Différences voulues : nouveaux mots de passe PostgreSQL et maître (fichier `.env`) ; filestore dans le volume
`odoo-data`, base dans le volume `db-data` ; le paquet `python3-lxml-html-clean`, installé à la main pour satisfaire
le paquet Debian d'Odoo, est inutile sous Debian 12 et n'est pas repris, pas plus que les outils de test et
d'administration du système.

## Installer sur une nouvelle machine

Prérequis : Docker Engine avec le plugin `docker compose`, Tailscale connecté au réseau des utilisateurs, 2 Go de RAM
et 10 Go de disque.

```
git clone --depth 1 --branch odoowsers https://github.com/Dowsers/odoo.git
cd odoo
cp .env.example .env        # puis remplacer les trois valeurs
chmod 600 .env
docker compose config -q    # vérifie docker-compose.yml et .env
docker compose build
```

`--depth 1` évite de télécharger les 4,8 Go d'historique du dépôt.

## Restaurer une sauvegarde

Les sauvegardes sont celles du dépôt privé des sauvegardes, dossier `DB_RECOVERY` (script
`backup/odoo_backup.sh` de ce dépôt). Elles contiennent la base et les pièces jointes.

```
docker/restore.sh /chemin/database_AAAA-MM-JJ_HH-MM-SS.zip          # à l'identique
docker/restore.sh -n /chemin/database_AAAA-MM-JJ_HH-MM-SS.zip       # copie de test neutralisée
docker/restore.sh -f /chemin/database_AAAA-MM-JJ_HH-MM-SS.zip       # remplace la base existante
```

- **Sans `-n`**, la base revient à l'identique : même identifiant, même clé secrète (les sessions et les liens signés
  restent valides), même adresse. C'est le mode de la migration et de la reprise après sinistre. La commande
  `odoo db load` d'Odoo ne convient pas : elle traite toujours la base comme une copie et change ces valeurs.
- **Avec `-n`**, la copie reçoit un nouvel identifiant, n'envoie pas d'e-mails et ses actions planifiées sont
  désactivées. Pour la lancer à côté de la production, utiliser un autre projet et d'autres ports :
  ```
  export COMPOSE_PROJECT_NAME=odoo-test COMPOSE_ENV_FILES=.env.test    # .env.test : ODOO_PORT=8070, REDIRECT_PORT=8067
  docker/restore.sh -n /chemin/sauvegarde.zip && docker compose up -d --wait
  docker compose down -v                                              # supprime la copie et ses volumes
  ```

## Migrer vers une autre machine

1. Répéter sur la machine cible avec une copie neutralisée (voir ci-dessus).
2. Sur la machine d'origine, hors des heures d'utilisation : couper l'accès des utilisateurs, faire la sauvegarde
   finale, puis tout arrêter.
   ```
   tailscale serve reset                                       # plus personne n'accède à Odoo
   <dépôt des sauvegardes>/backup/odoo_backup.sh --no-push     # sauvegarde finale
   scripts/run_prod.sh stop
   systemctl disable --now odoo-backup.timer
   ```
   Copier vers la machine cible le dernier fichier de `DB_RECOVERY/daily/`.
3. Sur la machine cible : `docker/restore.sh -f /chemin/sauvegarde.zip`, puis `scripts/run_prod.sh`.
4. Reprendre le nom Tailscale, pour que l'adresse des utilisateurs ne change pas : sur l'ancienne machine
   `tailscale serve reset` et `tailscale set --hostname=odoo-ancien` ; sur la nouvelle
   `tailscale set --hostname=odoo`, puis `scripts/run_prod.sh`. Tailscale obtient le certificat à la première
   connexion, en une trentaine de secondes.
5. Réactiver la sauvegarde automatique sur la machine cible : cloner le dépôt des sauvegardes, écrire
   `COMPOSE_DIR=/chemin/vers/odoo` dans `/etc/odoo-backup.conf`, lancer `backup/install.sh`.

Contrôles après une bascule :

- `https://<machine>.<tailnet>.ts.net/web/login` répond, avec un certificat valide.
- Une ancienne adresse en `http://…:8069/…` est renvoyée vers HTTPS.
- Connexion d'un utilisateur, ouverture d'une pièce jointe, génération d'un PDF.
- `scripts/run_prod.sh logs` sans erreur ; Paramètres > Technique > Actions planifiées : dates d'exécution récentes.

## HTTPS

Aucun port n'est ouvert vers l'extérieur. Docker publie Odoo sur `127.0.0.1:8069` et la redirection sur
`127.0.0.1:8068`. `docker/tailscale_https.sh`, appelé par `run_prod.sh`, configure Tailscale Serve sur la machine
hôte :

| Adresse | Destination |
|---|---|
| `https://<machine>.<tailnet>.ts.net` | Odoo. Tailscale obtient et renouvelle seul le certificat. |
| `http://<machine>…` (port 80) et `http://<machine>…:8069` | Redirection 308 vers l'adresse HTTPS, chemin conservé |

Odoo fonctionne avec `proxy_mode = True`. Trois paramètres système, enregistrés dans la base donc repris par une
restauration, complètent le réglage :

| Paramètre | Valeur | Rôle |
|---|---|---|
| `web.base.url` | l'adresse HTTPS | Liens des e-mails |
| `web.base.url.freeze` | `True` | Empêche Odoo de remplacer cette adresse à la connexion d'un administrateur |
| `report.url` | `http://127.0.0.1:8069` | La génération des PDF charge ses ressources en local |

Si l'adresse change, mettre à jour `web.base.url` (Paramètres > Technique > Paramètres système) et `HTTPS_URL`
dans `.env`.

## Exploitation

```
docker compose exec odoo odoo shell --no-http             # console Odoo
docker compose exec odoo odoo db dump database - > sauvegarde.zip
docker compose exec db psql -U odoo -d database           # console SQL
```

Mettre à jour le code ou un module :

```
git pull                                                  # ou modifier les sources de la branche
scripts/run_prod.sh update                                # reconstruit l'image et relance Odoo
docker compose exec odoo odoo module upgrade <module>     # si un module a changé
scripts/run_prod.sh restart
```

- Ne jamais mettre à jour `hr_appraisal_custom` sans vérification : sa mise à jour supprimerait des enregistrements
  créés directement en base (menus, règles, droits d'accès, action planifiée).
- Si PostgreSQL est redémarré seul, relancer Odoo (`scripts/run_prod.sh restart`) : les actions planifiées d'Odoo ne
  survivent pas à une coupure de la base. `docker compose` le fait de lui-même quand c'est lui qui relance `db`.
- Les journaux des conteneurs sont limités à 5 fichiers de 20 Mo.

## Installation d'origine, conservée pour un retour arrière

La machine d'origine garde l'ancienne installation, arrêtée et désactivée : paquet Debian `odoo` (service `odoo`),
PostgreSQL 18 local avec la base telle qu'elle était à la bascule (démarrage passé en manuel dans
`/etc/postgresql/18/main/start.conf`), service `odoo-https-redirect`. Pour y revenir :

```
scripts/run_prod.sh stop
systemctl start postgresql@18-main && systemctl start odoo-https-redirect odoo
rm /etc/odoo-backup.conf        # la sauvegarde automatique repasse en mode local
```

Les saisies faites sous Docker depuis la bascule seraient perdues : les reporter d'abord par une sauvegarde puis une
restauration dans l'ancienne base. Une fois la version Docker éprouvée, l'ancienne installation peut être supprimée
pour libérer plus de 1 Go.

## Limites connues

- Le wkhtmltopdf de Debian n'a pas le Qt modifié : les PDF n'ont ni en-tête ni pied de page répétés. C'était déjà le
  cas avant Docker.
- Douze images de badges et de rangs (module Gamification) manquaient dans le filestore d'origine, donc dans les
  sauvegardes.
- La seconde base `odoo` de l'installation d'origine, jamais utilisée, n'a pas été migrée.
