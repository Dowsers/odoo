# Odoo sous Docker (branche `odoowsers`)

Cette branche contient le code exact du serveur Odoo d'origine. Les fichiers ci-dessous permettent de le faire tourner
sous Docker, sur une autre machine, avec les mêmes versions.

| Fichier | Rôle |
|---|---|
| `Dockerfile`, `.dockerignore` | Image Odoo construite à partir de cette branche |
| `docker-compose.yml` | Odoo, PostgreSQL 18 et la redirection HTTP vers HTTPS |
| `.env.example` | Modèle du fichier `.env` (mots de passe, adresse HTTPS), jamais commité |
| `docker/entrypoint.sh`, `docker/odoo.conf.template`, `docker/wait-for-psql.py` | Démarrage du conteneur : configuration écrite à partir de l'environnement, attente de PostgreSQL |
| `docker/restore.sh` | Chargement d'une sauvegarde dans la pile Docker |
| `docker/tailscale_https.sh` | Publication en HTTPS par Tailscale |
| `docker/redirect_https.py` | Redirection des anciennes adresses HTTP vers HTTPS |
| `docker/host/` | HTTPS pour un Odoo installé sans Docker (serveur d'origine) |

## Ce que l'image reproduit

| Élément | Serveur d'origine | Image |
|---|---|---|
| Système, Python | Debian 12, Python 3.11 | `debian:bookworm-slim`, Python 3.11 |
| Bibliothèques Python | Paquets `python3-*` de Debian 12, `python3-psycopg2` du dépôt PGDG | Les mêmes paquets |
| PostgreSQL | 18.7, base `database`, collation C | `postgres:18`, base recréée à l'identique par la restauration |
| wkhtmltopdf | 0.12.6 de Debian | Le même paquet |
| Code Odoo et modules | Paquet Debian 19.0.20260128 modifié à la main | Cette branche, qui en est la copie |
| Configuration | `db_name = database`, sans workers | Identique, plus `proxy_mode` |

Différences voulues : nouveaux mots de passe PostgreSQL et maître (fichier `.env`) ; filestore dans le volume
`odoo-data` ; le paquet `python3-lxml-html-clean`, installé à la main sur le serveur d'origine pour satisfaire le
paquet Debian d'Odoo, est inutile sous Debian 12 et n'est pas repris.

## Prérequis sur la machine cible

- Docker Engine et le plugin `docker compose`.
- Tailscale, connecté au même réseau que les utilisateurs.
- 2 Go de RAM et 10 Go de disque au minimum.

## Installation

```
git clone --depth 1 --branch odoowsers https://github.com/Dowsers/odoo.git
cd odoo
cp .env.example .env        # puis remplacer les trois valeurs
chmod 600 .env
docker compose config -q    # vérifie docker-compose.yml et .env
docker compose build
```

`--depth 1` évite de télécharger les 4,8 Go d'historique du dépôt.

## Migration depuis le serveur d'origine

Les sauvegardes sont celles du dépôt privé des sauvegardes, dossier `DB_RECOVERY` (script
`backup/odoo_backup.sh` de ce dépôt). Elles contiennent la base et les pièces jointes.

### 1. Répétition, sans effet sur la production

```
docker/restore.sh -n /chemin/DB_RECOVERY/database_AAAA-MM-JJ_HH-MM-SS.zip
docker compose up -d
docker compose ps           # les trois services doivent être « running », odoo « healthy »
```

`-n` neutralise la copie : elle n'envoie pas d'e-mails et ses actions planifiées sont désactivées. Pour la consulter
depuis un poste : `ssh -L 8069:127.0.0.1:8069 <machine>`, puis `http://localhost:8069`.

### 2. Bascule

1. Sur le serveur d'origine : arrêter Odoo, faire la sauvegarde finale, arrêter la sauvegarde automatique.
   ```
   systemctl stop odoo
   <dépôt des sauvegardes>/backup/odoo_backup.sh --no-push
   systemctl disable --now odoo-backup.timer
   ```
   Copier vers la machine cible le dernier fichier de `DB_RECOVERY/daily/`.
2. Sur la machine cible : charger la sauvegarde, sans `-n`, puis démarrer.
   ```
   docker/restore.sh -f /chemin/database_AAAA-MM-JJ_HH-MM-SS.zip
   docker compose up -d
   ```
   `-f` remplace la base de la répétition.
3. Reprendre le nom Tailscale `odoo`, pour que l'adresse des utilisateurs ne change pas.
   ```
   # serveur d'origine
   tailscale serve reset
   tailscale set --hostname=odoo-ancien
   # machine cible
   tailscale set --hostname=odoo
   docker/tailscale_https.sh
   ```
   Tailscale obtient le certificat à la première connexion, en une trentaine de secondes.
4. Réactiver la sauvegarde automatique sur la machine cible : cloner le dépôt des sauvegardes, écrire
   `COMPOSE_DIR=/chemin/vers/odoo` dans `/etc/odoo-backup.conf`, lancer `backup/install.sh`.

### 3. Contrôles après la bascule

- `https://<machine>.<tailnet>.ts.net/web/login` répond, avec un certificat valide.
- Une ancienne adresse en `http://…:8069/…` est renvoyée vers HTTPS.
- Connexion d'un utilisateur, ouverture d'une pièce jointe, génération d'un PDF.
- `docker compose logs odoo` sans erreur ; Paramètres > Technique > Actions planifiées : dates d'exécution récentes.
- `docker compose exec odoo odoo db dump database - | wc -c` renvoie une taille de l'ordre de 10 Mo.

### 4. Retour arrière

Le serveur d'origine reste intact. Pour y revenir : arrêter la pile (`docker compose down`), rendre son nom au
serveur d'origine (`tailscale set --hostname=odoo`), y relancer `docker/host/install_https.sh` puis
`systemctl start odoo` et `systemctl enable --now odoo-backup.timer`. Les saisies faites entre-temps sous Docker
sont à reporter par une sauvegarde puis une restauration dans l'autre sens.

## HTTPS

Aucun port n'est ouvert vers l'extérieur. Docker publie Odoo sur `127.0.0.1:8069` et la redirection sur
`127.0.0.1:8068`. `docker/tailscale_https.sh` configure Tailscale Serve sur la machine hôte :

| Adresse | Destination |
|---|---|
| `https://<machine>.<tailnet>.ts.net` | Odoo. Tailscale obtient et renouvelle seul le certificat. |
| `http://<machine>…` (port 80) et `http://<machine>…:8069` | Redirection 308 vers l'adresse HTTPS, chemin conservé |

Odoo fonctionne avec `proxy_mode = True`. Trois paramètres système, enregistrés dans la base donc repris par la
migration, complètent le réglage :

| Paramètre | Valeur | Rôle |
|---|---|---|
| `web.base.url` | l'adresse HTTPS | Liens des e-mails |
| `web.base.url.freeze` | `True` | Empêche Odoo de remplacer cette adresse à la connexion d'un administrateur |
| `report.url` | `http://127.0.0.1:8069` | La génération des PDF charge ses ressources en local |

Si l'adresse change, mettre à jour `web.base.url` (Paramètres > Technique > Paramètres système) et `HTTPS_URL`
dans `.env`.

Pour un Odoo installé sans Docker : `docker/host/install_https.sh`, puis `proxy_mode = True` et
`http_interface = 127.0.0.1` dans `odoo.conf`, et les trois paramètres ci-dessus.

## Exploitation

```
docker compose logs -f odoo                               # journal
docker compose exec odoo odoo shell --no-http             # console Odoo
docker compose exec odoo odoo db dump database - > sauvegarde.zip
docker compose down                                       # arrêt ; les volumes sont conservés
```

Mise à jour du code :

```
git pull
docker compose build
docker compose up -d
docker compose exec odoo odoo module upgrade <module>     # si un module a changé
docker compose restart odoo
```

Ne jamais mettre à jour `hr_appraisal_custom` sans vérification : sa mise à jour supprimerait des enregistrements
créés directement en base (menus, règles, droits d'accès, action planifiée).

## Limites connues

- L'image n'a pas été construite sur le serveur d'origine, où Docker n'est pas installé. Ont été vérifiés sans
  Docker : le démarrage d'Odoo à partir des seules sources de cette branche sur une sauvegarde restaurée (131 modules,
  tests des modules personnalisés), l'écriture de la configuration par `entrypoint.sh`, la présence de chaque paquet
  du `Dockerfile` dans Debian 12. La première construction et `docker compose config` restent à faire sur la machine
  cible.
- Le wkhtmltopdf de Debian n'a pas le Qt modifié : les PDF n'ont ni en-tête ni pied de page répétés. C'est déjà le
  cas sur le serveur d'origine.
- Douze images de badges et de rangs (module Gamification) manquent dans le filestore du serveur d'origine, donc
  dans les sauvegardes.
- La seconde base `odoo` du serveur d'origine, jamais utilisée, n'est pas migrée.
