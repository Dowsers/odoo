# Congés - Jours fériés français officiels

Module Odoo personnalisé qui récupère automatiquement les jours fériés sur le site du gouvernement et les enregistre
dans les jours fériés d'Odoo (Congés > Configuration > Jours fériés).

## Version
- **Version** : 19.0.1.0.0
- **Catégorie** : Ressources humaines/Congés
- **Licence** : LGPL-3

## Source

L'API « Jours fériés » de l'État, référencée sur api.gouv.fr :
`https://calendrier.api.gouv.fr/jours-feries/<zone>.json`. Elle publie les jours fériés de chaque zone pour vingt ans
en arrière et cinq ans à venir, sans clé d'accès. Seule la zone fait partie de la requête : aucune donnée d'Odoo n'est
envoyée.

## Import

| Quand | Comment |
|---|---|
| Chaque semaine | Action planifiée « Congés : import des jours fériés officiels français » |
| À la demande | Bouton « Importer les jours fériés officiels » de la liste des jours fériés, bouton « Importer maintenant » des paramètres et de la liste des jours fériés officiels |
| Après un changement de paramètre | La zone ou le lundi de Pentecôte modifiés déclenchent l'action planifiée |

Chaque import couvre **l'année en cours et l'année suivante**, pour chaque société qui a une zone :

- **Création** : un jour férié officiel devient un jour férié Odoo de la société, pour tous ses horaires de travail,
  du jour à 0 h à 23 h 59 dans le fuseau horaire de l'horaire de travail de la société. Il porte le libellé officiel,
  par exemple « Lundi de Pâques » ou « 8 mai ».
- **Jours déjà enregistrés** : un jour que chevauche déjà un jour férié de la société, saisi à la main par exemple, est
  laissé tel quel. L'import ne modifie et ne supprime jamais un jour férié saisi à la main. Si ce jour férié ne couvre
  qu'une partie de la journée ou qu'un seul horaire de travail, complétez-le à la main. S'il est supprimé à la main,
  l'import suivant crée le jour férié officiel à sa place.
- **Lundi de Pentecôte** : il n'est pas importé tant qu'il est travaillé (journée de solidarité, case « Lundi de
  Pentecôte travaillé » des paramètres). Changer ce réglage ne concerne que les lundis de Pentecôte **à venir** :
  l'import crée le prochain s'il devient férié, ou retire celui qu'il avait créé s'il redevient travaillé. Un lundi de
  Pentecôte passé garde ce qu'il était ; pour le corriger, ajoutez-le ou supprimez-le à la main dans les jours fériés.
- **Suppression dans Odoo** : un jour férié importé puis supprimé dans Odoo n'est jamais réimporté.
- **Jour férié retiré par le gouvernement** : s'il est à venir, le jour férié importé est supprimé ; s'il est passé, il
  est conservé.
- **Réponse anormale** : si la réponse de l'API ne contient pas entre 8 et 20 jours fériés pour chacune des deux
  années, rien n'est modifié et l'erreur est signalée.

**Le passé n'est jamais réécrit** : l'import ne supprime aucun jour férié passé et ne génère aucune ligne de temps
pour un jour passé.

La liste Congés > Configuration > Jours fériés officiels montre chaque jour publié et ce que l'import en a fait :
importé, déjà enregistré, jour travaillé, supprimé dans Odoo ou plus officiel.

## Effets dans Odoo

Ce sont ceux d'un jour férié saisi à la main :

- **Feuilles de temps** : Odoo génère une ligne « Time Off » pour chaque employé de la société un jour ouvré.
  L'import n'en génère **aucune pour les jours déjà passés** : les employés ont déjà rempli ces journées. C'est aussi
  la règle d'Odoo pour un nouvel employé, qui ne reçoit que les jours fériés à venir.
- **Congés** : Odoo recalcule la durée des demandes de congé qui chevauchent le jour férié, qui n'est plus décompté.
  Quand un jour férié à venir est retiré, les demandes concernées reprennent un jour et Odoo en avertit les
  employés.
- **Lignes de temps des congés** : Odoo ne génère des lignes de temps que pour les congés validés. Sans ce module,
  supprimer un jour férié en générait aussi pour les demandes en attente ou refusées qui le chevauchent : le module
  corrige ce comportement, pour l'import comme pour une suppression à la main.
- **Contrôles et export CIR** : pour les années importées, les modules `hr_timesheet_consistency` et
  `hr_timesheet_cir_export` suivent exactement les jours fériés d'Odoo, y compris un jour ajouté ou supprimé à la
  main. La source affichée est « calendrier.api.gouv.fr » pour un jour importé et « Odoo » pour un jour saisi à la
  main. Pour les autres années, ils gardent le calcul des jours fériés légaux.

## Paramètres

Paramètres > Employés > Jours fériés français :

- **Jours fériés officiels** : la zone de la société. Elle est déduite du pays de la société : France
  métropolitaine pour la France, ou le territoire d'outre-mer. L'Alsace-Moselle se choisit à la main. Laisser vide
  arrête l'import. La date du dernier import et sa dernière erreur s'affichent dessous.
- **Lundi de Pentecôte travaillé** : partagé avec `hr_timesheet_consistency`, paramètre système
  `hr_timesheet_consistency.whit_monday_worked`. Cochée par défaut. Modifiez-la ici plutôt que dans les paramètres
  système : l'import est alors relancé aussitôt.

## Erreurs

Si l'API est injoignable ou répond de façon inattendue, rien n'est modifié. L'erreur est inscrite dans le journal
d'Odoo et affichée dans les paramètres. L'action planifiée n'échoue pas, pour qu'Odoo ne la désactive pas, et réessaie
la semaine suivante. Les boutons affichent l'erreur directement. La réponse est limitée à 1 Mo et 60 secondes. Deux
imports simultanés d'une même société ne créent pas de doublon : le second est rejoué après le premier.

## Droits

Les boutons d'import sont réservés aux administrateurs des congés et aux administrateurs d'Odoo. La liste des jours
fériés officiels est en lecture seule et visible des responsables des congés.

## Dépendances

- `hr_holidays` (Congés)
- `project_timesheet_holidays` (feuilles de temps des congés)
- `hr_timesheet_consistency` (règles des jours fériés et paramètre du lundi de Pentecôte)
- Bibliothèque Python `requests`, fournie avec Odoo

## Installation

1. Copiez le module dans le répertoire `addons` de votre installation Odoo
2. Mettez à jour la liste des modules dans Odoo
3. Installez le module "Time Off - French Public Holidays"
4. Lancez un premier import avec le bouton « Importer les jours fériés officiels » de Congés > Configuration > Jours
   fériés, ou attendez l'action planifiée, qui passe quelques minutes après l'installation

## Auteur

Custom Development
