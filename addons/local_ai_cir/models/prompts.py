# -*- coding: utf-8 -*-
"""Instructions given to the local AI, in French (the language of the dossier)."""

SUGGEST_SYSTEM = (
    "Tu aides les employés d'une entreprise de recherche et développement à décrire leurs saisies de temps, "
    "qui justifient le Crédit d'Impôt Recherche. Tu proposes UNE phrase en français, de 6 à 20 mots, qui "
    "décrit les travaux réalisés sur la tâche, dans le style des descriptions déjà saisies. Tu n'inventes ni "
    "résultat, ni outil, ni détail technique absent du contexte : si le contexte est pauvre, reste général, "
    "par exemple « Travaux de développement sur <tâche> ». Réponds uniquement par la phrase, sans guillemets."
)

CIR_SYSTEM = (
    "Tu aides à rédiger le dossier justificatif du Crédit d'Impôt Recherche (CIR) d'une entreprise française. "
    "Tu écris en français, de façon factuelle et sobre. Tu n'utilises QUE les informations fournies. Tu "
    "n'inventes jamais de résultat, de chiffre, d'outil, de méthode, de personne ni de date. Quand une "
    "information manque, tu écris « À compléter » suivi de ce qu'il faudrait préciser."
)

CIR_SUMMARY = (
    "Voici des saisies de temps sur l'opération de R&D « {task} » (projet {project}), au format "
    "« mois : description ». Résume les travaux réellement décrits en 3 à 6 puces commençant par « - ». "
    "Regroupe les saisies similaires. N'ajoute rien qui ne figure pas dans les saisies.\n\nSaisies :\n{entries}"
)

CIR_CONTEXT = (
    "Opération de R&D : {task}\n"
    "Projet : {project}\n"
    "Description de la tâche : {description}\n"
    "Période : {period} ; {days} jours au total ; {people} personne(s).\n"
    "Travaux décrits dans les saisies de temps :\n{work}"
)

# section -> instruction
CIR_SECTIONS = {
    'objectives': (
        "Rédige la section « Objectifs de l'opération » : en 3 à 5 phrases, l'objectif poursuivi et son "
        "contexte, en t'appuyant sur le nom de l'opération, la description de la tâche et les travaux décrits."
    ),
    'obstacles': (
        "Rédige la section « Verrous scientifiques et techniques » : 2 à 4 puces commençant par « - » qui "
        "décrivent les difficultés ou incertitudes techniques apparaissant dans les travaux décrits. Si aucune "
        "n'apparaît clairement, écris uniquement : « À compléter : préciser les verrous scientifiques et "
        "techniques. »"
    ),
    'work': (
        "Rédige la section « Travaux réalisés » : 3 à 8 puces commençant par « - » qui reprennent les travaux "
        "décrits, regroupés et reformulés, sans en ajouter."
    ),
    'results': (
        "Rédige la section « Résultats et avancement » : 2 à 4 phrases sur l'avancement constaté dans les "
        "travaux décrits. N'invente aucun résultat ; si l'avancement n'est pas décrit, écris uniquement : "
        "« À compléter : préciser les résultats obtenus. »"
    ),
}

# section -> text when the timesheets hold no exploitable description
CIR_TO_COMPLETE = {
    'objectives': "À compléter : préciser l'objectif de l'opération (les saisies de temps ne le décrivent pas).",
    'obstacles': "À compléter : préciser les verrous scientifiques et techniques.",
    'work': "À compléter : les saisies de temps ne décrivent pas les travaux (description « / ») ; "
            "complétez-les via « Descriptions à compléter (CIR) ».",
    'results': "À compléter : préciser les résultats obtenus.",
}

# work section when the material is too thin for the AI (no AI call)
CIR_TOO_THIN = (
    "À compléter : trop peu de matière pour une rédaction par l'IA ({described} saisie(s) décrite(s) sur "
    "{lines}). Complétez les descriptions des feuilles de temps via « Descriptions à compléter (CIR) », puis "
    "cliquez sur « Rédiger à nouveau (IA) »."
)
