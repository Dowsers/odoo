# Feuilles de temps - Vue calendrier par défaut

Module Odoo personnalisé qui ouvre « Mes feuilles de temps » en vue calendrier.

## Version
- **Version**: 19.0.1.0.0
- **Catégorie**: Services/Feuilles de temps
- **Licence**: LGPL-3

## Description

Par défaut, l'action « My Timesheets » (`/odoo/timesheets`, ouverte par l'icône de l'application
Feuilles de temps et par les menus « Mes feuilles de temps ») s'ouvre en vue liste.
Ce module fait de la vue calendrier la vue par défaut sur ordinateur.

Les vues liste, formulaire, kanban, pivot et graphique restent accessibles via le sélecteur de vues
(la liste devient `/odoo/timesheets?view_type=list`). Les autres actions (« All Timesheets »,
rapports, feuilles de temps d'un projet ou d'une tâche) ne sont pas modifiées.

Sur mobile (écran de moins de 768 px), Odoo ouvre la vue indiquée par `mobile_view_mode`
(kanban) : ce comportement est conservé, le calendrier mensuel étant peu pratique pour saisir
des temps sur un téléphone.

## Fonctionnement

Le module modifie un enregistrement du module `hr_timesheet` :

| Enregistrement | Champ | Valeur d'origine | Nouvelle valeur |
|---|---|---|---|
| `hr_timesheet.act_hr_timesheet_line_view_calendar` | `sequence` | `5` | `1` |

La vue calendrier passe ainsi avant la liste (séquence `4`) et devient la première vue de l'action.
La valeur est réappliquée automatiquement lors d'une mise à jour de `hr_timesheet`
(les modules dépendants sont mis à jour en même temps). La désinstallation du module
restaure la valeur d'origine.

## Utilisation du calendrier

- Pour saisir des temps, sélectionnez un ou plusieurs jours puis cliquez sur « Ajouter »
  (projet, tâche, temps passé, description).
- La saisie sur plusieurs jours ignore les jours non travaillés (week-ends, congés, jours fériés) :
  pour ces jours, utilisez la vue liste.
- Les totaux d'heures sont affichés dans la vue liste.

## Dépendances

- `hr_timesheet` (Feuilles de temps)

## Installation

1. Copiez le module dans le répertoire `addons` de votre installation Odoo
2. Mettez à jour la liste des modules dans Odoo
3. Installez le module "Timesheets - Calendar Default View"

Dans un onglet déjà ouvert sur « Mes feuilles de temps » au moment de l'installation, cliquez une fois
sur le menu Feuilles de temps (ou ouvrez un nouvel onglet) : un simple F5 sur cette page réutilise
l'action mémorisée par l'onglet. Inutile de vider le cache du navigateur.

## Auteur

Custom Development
