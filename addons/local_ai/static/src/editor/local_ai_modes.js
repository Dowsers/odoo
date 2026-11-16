import { _t } from "@web/core/l10n/translation";

/** Instructions sent to the model: in French, the language of the users. */
export const REWRITE_MODES = [
    {
        id: "correct",
        label: _t("Correct"),
        instruction:
            "Corrige l'orthographe, la grammaire et la ponctuation du texte, sans changer le sens ni le ton.",
    },
    {
        id: "rephrase",
        label: _t("Rephrase"),
        instruction: "Reformule le texte pour le rendre plus clair et plus professionnel, sans changer le sens.",
    },
    {
        id: "shorten",
        label: _t("Shorten"),
        instruction: "Raccourcis le texte en gardant les informations essentielles.",
    },
    {
        id: "develop",
        label: _t("Develop"),
        instruction:
            "Développe le texte en phrases complètes et bien construites, sans ajouter d'information qui n'y figure pas.",
    },
];

export const REWRITE_SYSTEM =
    "Tu es un assistant de rédaction. Tu appliques la consigne au texte fourni et tu réponds uniquement " +
    "par le texte obtenu, dans la langue du texte fourni, sans guillemets ni commentaire. " +
    "Tu n'inventes aucune information.";

export const WRITE_SYSTEM =
    "Tu es un assistant de rédaction pour une entreprise. Tu écris le texte demandé, en français sauf " +
    "demande contraire, de façon claire et professionnelle, et tu réponds uniquement par ce texte. " +
    "Tu n'inventes ni chiffre, ni nom, ni fait précis : quand une information manque, tu laisses un " +
    "emplacement entre crochets, par exemple [date].";
