# Feuilles de temps - Contrôles de cohérence

Module Odoo personnalisé qui refuse les saisies de feuilles de temps incohérentes.

## Version
- **Version** : 19.0.1.1.0
- **Catégorie** : Services/Feuilles de temps
- **Licence** : LGPL-3

## Contrôles

Ils s'appliquent à chaque création ou modification d'une ligne de feuille de temps, quelle que soit la vue :
calendrier, liste, saisie sur plusieurs jours ou import.

| Contrôle | Règle | Exception |
|---|---|---|
| Une journée au plus par jour calendaire | Le total des lignes d'un collaborateur sur une date, absences comprises, ne peut pas dépasser une journée. | Seules les lignes qu'Odoo génère lui-même pour un congé ou un jour férié |
| Pas d'activité un jour férié | Une activité ne peut pas être saisie un jour férié. Les absences restent possibles, comme « Férié », « Congés » ou « RTT ». | Un administrateur des feuilles de temps peut saisir une activité exceptionnelle pour un autre collaborateur, pas pour lui-même. |

Précisions :

- **Une journée** vaut l'unité « Jours » de saisie des feuilles de temps (8 h), comme ce que saisissent les
  utilisateurs, ou la journée de l'horaire de travail si elle est plus longue. Si la société saisit en heures, c'est
  la durée d'une journée de l'horaire de travail.
- **Seul ce qui aggrave une journée est refusé.** Les lignes incohérentes déjà enregistrées peuvent être corrigées
  pas à pas : réduire un temps, changer de tâche ou supprimer une ligne reste possible. Déplacer une tâche vers un
  autre projet ne déclenche aucun contrôle.
- **Les lignes générées par Odoo ne sont jamais refusées** quand Odoo les crée ou les met à jour, qu'elles viennent
  d'un congé validé ou d'un jour férié enregistré dans Odoo. Un utilisateur qui modifie une de ces lignes est
  contrôlé comme pour toute autre ligne. Une absence saisie à la main et la ligne générée pour le même congé ne
  comptent qu'une fois.
- **Les montants négatifs** ne comptent pas dans le total.
- **Les saisies simultanées** d'un même collaborateur entrent en conflit : Odoo relance automatiquement la seconde,
  qui est alors contrôlée avec la première.

## Absences

Une case « Absence (feuilles de temps) » sur la tâche indique que ses temps sont des absences. Seuls les
administrateurs des feuilles de temps la voient et peuvent la modifier. Quand ils créent une tâche dont le nom
contient *congé*, *férié*, *time off*, *absence*, *RTT*, *maladie* ou *vacances*, elle est cochée d'office. Renommer
la tâche ne la modifie pas, et une copie de la tâche la conserve. La tâche des congés de la société est toujours une
absence.

## Jours fériés

- Les jours fériés légaux français sont calculés chaque année. Avec le module `hr_holidays_public_fr`, qui importe
  dans Odoo la liste officielle du gouvernement (calendrier.api.gouv.fr), seuls les jours fériés d'Odoo comptent pour
  les années importées.
- **Le lundi de Pentecôte est considéré comme travaillé** (journée de solidarité). Pour en faire un jour férié, passez
  le paramètre système `hr_timesheet_consistency.whit_monday_worked` à `False`. Si `hr_holidays_public_fr` est
  installé, décochez plutôt « Lundi de Pentecôte travaillé » dans les paramètres : le réglage vaut alors pour les
  lundis de Pentecôte à venir, voir ce module.
- Les jours fériés enregistrés dans Odoo (Congés > Configuration > Jours fériés) s'ajoutent à la liste, pour la
  société et l'horaire de travail du collaborateur. Ils comptent pour les jours dont ils couvrent toutes les heures
  de travail : une fermeture d'une demi-journée n'est pas un jour férié.

## Limites connues

- Dans l'onglet « Feuilles de temps » d'une tâche, les modifications sont enregistrées ligne par ligne. Augmenter une
  ligne d'une journée tout en réduisant, supprimant ou déplaçant une autre ligne du même jour peut être refusé : il
  suffit d'enregistrer d'abord la réduction, puis l'augmentation.
- Pour saisir une activité exceptionnelle un jour férié enregistré dans Odoo, un administrateur doit d'abord mettre
  à 0 la ligne « Time Off » générée ce jour-là.

## Règles partagées

Le modèle abstrait `hr.timesheet.day.rules` fournit ces règles à l'export CIR (`hr_timesheet_cir_export`) : jours
fériés, tâches d'absence et durée d'une journée. Deux méthodes peuvent être surchargées pour les jours fériés :
`_get_reference_public_holidays`, la liste de référence (les fériés calculés), et `_get_public_holiday_source`, la
source affichée pour un jour férié enregistré dans Odoo. `hr_holidays_public_fr` s'en sert pour les années importées.

## Dépendances

- `hr_timesheet` (Feuilles de temps)

## Installation

1. Copiez le module dans le répertoire `addons` de votre installation Odoo
2. Mettez à jour la liste des modules dans Odoo
3. Installez le module "Timesheets - Consistency Checks"

## Auteur

Custom Development
