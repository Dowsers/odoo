# Feuilles de temps - Export CIR (ZIP)

Module Odoo personnalisé qui permet aux administrateurs des feuilles de temps de télécharger,
en un clic, un ZIP contenant la fiche de temps annuelle (« Rapport mensuel d'activité - CIR »)
de chaque collaborateur.

## Version
- **Version** : 19.0.1.1.0
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
    ├── Contrôles de cohérence - CIR 2026.xlsx
    ├── Rapport mensuel d'activité - CIR 2026 - Alice MARTIN.xlsx
    ├── Rapport mensuel d'activité - CIR 2026 - Jean DUPONT.xlsx
    └── ...
```

Un classeur par collaborateur ayant des temps à déclarer sur la période (collaborateurs archivés compris),
construit sur le modèle `Rapport mensuel d'activité - CIR - template_V3.0.xlsx` :

| Onglet | Contenu |
|---|---|
| `Synthèse <année>` | Une ligne par projet / étape, une colonne par mois (formules vers les onglets mensuels), total par ligne et ligne TOTAL (hors absences). |
| `ReadMe` | Notes d'utilisation, année, liste des jours fériés (utilisée par les formules `NETWORKDAYS` et la mise en forme). |
| `Janvier` … `Décembre` | En-tête (nom, prénom, matricule, mois, année, nb de jours ouvrés, téléphone), une ligne par projet / étape et une colonne par jour, totaux, bloc de signatures et légende. Les mois postérieurs au mois d'arrêt sont vides. |
| `Jours Feriés` | Jours fériés de l'année : fériés français calculés et jours fériés enregistrés dans Odoo. Le lundi de Pentecôte est considéré comme travaillé, voir `hr_timesheet_consistency`. |
| `Contrôles` | Anomalies à vérifier : activité saisie un week-end ou un jour férié, plus d'une journée saisie sur une date. |

Le fichier `Contrôles de cohérence - CIR <année>.xlsx` regroupe les anomalies de tous les collaborateurs.

Correspondance avec Odoo :

| Fichier | Odoo |
|---|---|
| Projet | Projet de la feuille de temps |
| Etape | Tâche de la feuille de temps |
| Valeur d'un jour | Heures saisies ÷ durée d'une journée, soit l'unité « Jours » de saisie (8 h ⇒ `1`, 4 h ⇒ `0,5`), arrondi à 2 décimales. Les valeurs autres que 1 et 0,5 sont surlignées en rouge, comme dans le modèle. |
| Absence / Congés | Tâches marquées « Absence (feuilles de temps) » et tâche des congés de la société, qui reçoit les lignes générées par les congés et les jours fériés (modifiable dans l'assistant). Une absence saisie à la main et la ligne générée pour le même congé ne comptent qu'une fois. Les absences saisies un week-end ou un jour férié ne sont pas reprises. |
| Matricule | Badge ID du collaborateur (`barcode`), vide sinon |
| Nom / Prénom | Mots en majuscules du nom du collaborateur = nom ; les autres = prénom (`Jean DE LA FONTAINE`). Sans majuscules, le premier mot est le prénom. |
| Observations | Descriptions distinctes des lignes du mois pour le projet / l'étape |

## Jours non ouvrés et contrôles

Les week-ends et jours fériés ne sont pas des jours ouvrés, comme dans le modèle CIR :

- une absence saisie ces jours-là, par exemple « Férié » ou la ligne générée par un jour férié Odoo, n'est pas reprise ;
- une activité saisie ces jours-là reste affichée, en orange, et figure dans l'onglet `Contrôles` ;
- une date qui totalise plus d'une journée est signalée en orange sur la ligne des totaux et figure dans `Contrôles` ;
- un temps négatif n'est pas repris et figure dans `Contrôles` ;
- un collaborateur qui n'a rien à déclarer, par exemple seulement la ligne générée d'un jour férié, n'a pas de classeur.

Les textes saisis dans Odoo (noms de projets et de tâches, descriptions) restent du texte dans les classeurs : un
texte qui commence par `=` n'y devient jamais une formule.

Les anomalies sont à vérifier et, si besoin, à corriger dans Odoo avant de relancer l'export. Le module
`hr_timesheet_consistency` refuse les nouvelles activités un jour férié et les journées de plus d'un jour ; il
n'interdit pas le travail le week-end.

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
- `hr_timesheet_consistency` (règles des jours fériés, des absences et de la durée d'une journée)
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
