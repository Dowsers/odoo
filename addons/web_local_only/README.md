# Instance locale - sans liens vers odoo.com

Module Odoo personnalisé pour une instance utilisée sur un réseau privé uniquement : il retire les liens vers
odoo.com et les appels aux services en ligne d'Odoo S.A.

## Version
- **Version** : 19.0.1.1.0
- **Catégorie** : Caché/Outils
- **Licence** : LGPL-3

## Ce que le module retire

| Où | Avant | Après |
|---|---|---|
| Menu utilisateur | « Mon compte Odoo.com », « Documentation », « Support » | Entrées supprimées ; l'adresse `/web/session/account` renvoie vers l'instance au lieu de accounts.odoo.com |
| Page de connexion, portail | Lien « Powered by Odoo » vers odoo.com | Logo sans lien |
| E-mails | Lien « Powered by Odoo » dans les mises en page de notification, le digest périodique, les modèles d'invitation et de badge, les e-mails de notes de frais | Texte sans lien ; bandeau « Odoo Mobile » du digest retiré |
| Paramètres | Options Enterprise avec fenêtre « Upgrade » vers odoo.com, bloc « Odoo IAP », icônes de documentation, lien du copyright | Masqués |
| Applications | Modules Enterprise « à acheter », menus « Applications tierces » et « Thèmes » (apps.odoo.com) | Masqués |
| Éditeur de texte | Bouton « Traduire » (ChatGPT via olg.api.odoo.com), onglet « Illustrations » (media-api.odoo.com) | Retirés ; les demandes d'IA de l'éditeur sont refusées côté serveur. Le module `local_ai` réactive le bouton en faisant répondre le serveur d'IA de l'entreprise, sans passer par odoo.com |
| Arrière-plan | Action planifiée « Publisher: Update Notification », qui envoie à Odoo S.A. l'identifiant de la base, le nombre d'utilisateurs et la liste des modules | Désactivée, et la méthode ne contacte plus rien même si elle est relancée |

Les modèles d'e-mail sont nettoyés une fois, à l'installation, dans toutes les langues : seul le lien est retiré, le
texte reste. Un modèle remis à zéro depuis Odoo (« Réinitialiser le modèle ») retrouve son lien ; il suffit alors de
mettre à jour ce module.

## Ce qui reste

- Les modules SMS et courrier postal (IAP) restent installés, car d'autres modules en dépendent ; ils n'appellent
  odoo.com que si un utilisateur envoie un SMS ou une lettre, ce qui demande des crédits.
- Les textes d'aide d'OdooBot citent la documentation d'Odoo.
- Les adresses odoo.com saisies dans des fiches (site web d'un contact, par exemple) ne sont pas touchées.

Les modules qui n'existent que pour appeler des services odoo.com (autocomplétion des sociétés, enrichissement et
génération de pistes CRM) se désinstallent depuis les paramètres ; ce module ne les désinstalle pas lui-même.

## Dépendances

`web`, `mail`, `base_setup`, `iap`, `html_editor`, `portal`, `digest`, `hr_expense`.

## Installation

1. Copiez le module dans le répertoire `addons` de votre installation Odoo
2. Mettez à jour la liste des modules dans Odoo
3. Installez le module "Local Instance - No Links to odoo.com"
4. Rechargez la page : les utilisateurs déjà connectés reçoivent la nouvelle interface au rechargement

## Auteur

Custom Development
