# Feuilles de temps - Export CIR (ZIP)

Module Odoo personnalisé qui permet aux administrateurs des feuilles de temps de télécharger,
en un clic, un ZIP contenant la fiche de temps annuelle (« Rapport mensuel d'activité - CIR »)
de chaque collaborateur.

## Version
- **Version** : 19.0.1.0.0
- **Catégorie** : Services/Feuilles de temps
- **Licence** : LGPL-3

## Fonctionnalités

- Bouton **« Export CIR (ZIP) »** dans le panneau de contrôle de l'action « Toutes les feuilles de temps »
  (`/odoo/all-timesheets`, vues liste, calendrier, kanban, pivot et graphique). Un clic télécharge
  `Fiche_de_temps_<année>.zip` pour l'année en cours, **arrêtée au mois révolu précédent**
  (le 12 novembre 2026 : du 1er janvier au 31 octobre 2026 ; en janvier : l'année précédente complète).
- Menu **Feuilles de temps > Feuilles de temps > Export CIR (ZIP)** : assistant permettant de choisir
  l'année, le dernier mois inclus, les collaborateurs et les tâches considérées comme des absences.
- Réservé au groupe *Feuilles de temps / Administrateur* (`hr_timesheet.group_timesheet_manager`).

## Contenu du ZIP

```
Fiche_de_temps_2026.zip
└── 2026/
    ├── Rapport mensuel d'activité - CIR 2026 - Alice MARTIN.xlsx
    ├── Rapport mensuel d'activité - CIR 2026 - Jean DUPONT.xlsx
    └── ...
```

Un classeur par collaborateur ayant des feuilles de temps sur la période (collaborateurs archivés compris),
construit sur le modèle `Rapport mensuel d'activité - CIR - template_V3.0.xlsx` :

| Onglet | Contenu |
|---|---|
| `Synthèse <année>` | Une ligne par projet / étape, une colonne par mois (formules vers les onglets mensuels), total par ligne et ligne TOTAL (hors absences). |
| `ReadMe` | Notes d'utilisation, année, liste des jours fériés (utilisée par les formules `NETWORKDAYS` et la mise en forme). |
| `Janvier` … `Décembre` | En-tête (nom, prénom, matricule, heures / jour, mois, année, nb de jours ouvrés, téléphone), une ligne par projet / étape et une colonne par jour, totaux, bloc de signatures et légende. Les mois postérieurs au mois d'arrêt sont vides. |
| `Jours Feriés` | Jours fériés de l'année (fériés français calculés + jours de fermeture globaux des horaires de travail Odoo). |

Correspondance avec Odoo :

| Fichier | Odoo |
|---|---|
| Projet | Projet de la feuille de temps |
| Etape | Tâche de la feuille de temps |
| Valeur d'un jour | Heures saisies ÷ heures par jour de l'horaire de travail du collaborateur (8 h ⇒ `1`, 4 h ⇒ `0,5`), arrondi à 2 décimales. Les valeurs autres que 1 et 0,5 sont surlignées en rouge, comme dans le modèle. |
| Absence / Congés | Lignes générées par les congés (`holiday_id`, `global_leave_id`), tâche « congés » de la société et tâches dont le nom contient *congé*, *férié*, *time off* ou *absence* (modifiable dans l'assistant). |
| Matricule | Badge ID du collaborateur (`barcode`), vide sinon |
| Nom / Prénom | Mots en majuscules du nom du collaborateur = nom ; les autres = prénom (`Jean DE LA FONTAINE`). Sans majuscules, le premier mot est le prénom. |
| Observations | Descriptions distinctes des lignes du mois pour le projet / l'étape |

Les résultats des formules sont enregistrés dans le fichier : les totaux sont corrects même dans
un aperçu qui ne recalcule pas (navigateur, messagerie).

## Fonctionnement technique

- `models/timesheet_cir_export.py` : modèle abstrait `hr.timesheet.cir.export` (collecte des données,
  génération des classeurs avec `xlsxwriter`, archive ZIP).
- `controllers/main.py` : route `POST /hr_timesheet_cir_export/download` (paramètres optionnels
  `year`, `month`), appelée par le bouton.
- `wizard/` : assistant `hr.timesheet.cir.export.wizard` (menu) et méthode RPC
  `is_export_button_visible` qui décide de l'affichage du bouton.
- `static/src/cir_export_button/` : composant OWL inséré dans le panneau de contrôle
  (`web.ControlPanel`, extension de template) ; il n'est affiché que pour l'action
  `hr_timesheet.timesheet_action_all` et pour les administrateurs.

## Dépendances

- `hr_timesheet` (Feuilles de temps)
- Python : `xlsxwriter` (fourni avec Odoo)

## Installation

1. Copiez le module dans le répertoire `addons` de votre installation Odoo
2. Mettez à jour la liste des modules dans Odoo
3. Installez le module "Timesheets - CIR Export (ZIP)"

## Tests

```
odoo server -c <config> -d <base de test> -i hr_timesheet_cir_export --test-enable --test-tags /hr_timesheet_cir_export --stop-after-init
```

## Auteur

Custom Development
