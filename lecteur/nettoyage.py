"""Correction automatique des erreurs d'OCR et assemblage des lignes en texte continu.

Chaque correction est notée dans un journal (avant, après) pour l'aperçu.
"""
from __future__ import annotations

import re

from .dictionnaire import connu
from .references import corriger_references

TRAIT_CONDITIONNEL = "­"  # trait d'union de coupure (soft hyphen)
_DEBRIS = re.compile(r"[■□▪▫●○◆◇►◄▲▼•¤¦|~^_<>{}\\■-◿�]")
_RE_IL = re.compile(r"^(?:\*11|\*?II|\*Il|lI|1l)$")
_PONCTUATION_PERMISE = {"«", "»", ":", ";", "!", "?", "—", "–", "-", "…", "(", ")", "’", "'", ",", ".", TRAIT_CONDITIONNEL}


def nettoyer_mot(mot: str, journal: list | None = None) -> str:
    """Corrige un mot isolé. Retourne "" si c'est un débris à jeter."""
    avant = mot
    m = _DEBRIS.sub("", mot)
    m = m.replace('"', "").replace("”", "").replace("“", "")
    if _RE_IL.match(m):
        m = "Il"
    elif m.startswith("*") and len(m) > 1 and m[1].isalpha():
        m = m[1:]
    m = m.replace("*", "")
    # « /'Eternel », « ('Ecriture » : le l minuscule pris pour une barre ou une parenthèse.
    m = re.sub(r"^[/(\[]([’'])(?=[A-ZÀ-Üa-zà-ÿ])", r"l\1", m)
    # Ponctuation seule et isolée (débris de tache) : on jette, sauf la vraie ponctuation française.
    if m and not any(c.isalnum() for c in m) and m not in _PONCTUATION_PERMISE:
        m = ""
    if journal is not None and m != avant and avant.strip(TRAIT_CONDITIONNEL) != m:
        journal.append((avant, m or "∅"))
    return m


def _recoller(gauche: str, droite: str) -> str | None:
    """« commence- » + « ments » -> « commencements » si le mot recollé existe."""
    base = gauche.rstrip("-")
    tete = re.match(r"^[\wÀ-ÿ’']+", droite)
    if not base or not tete:
        return None
    colle = base + droite
    mot_colle = re.sub(r"[^\wÀ-ÿ’'-]", "", base + tete.group(0))
    # On recolle si le mot entier existe, ou si le morceau de droite n'est pas un mot à lui seul
    # (« ments »). « souvenons-nous », « peut-être » gardent leur trait d'union.
    if connu(mot_colle) or not connu(tete.group(0)):
        return colle
    return None


def assembler(lignes: list[str], journal: list | None = None) -> str:
    """Joint des lignes en un texte continu en recollant les mots coupés en fin de ligne."""
    texte = ""
    for ligne in lignes:
        ligne = ligne.strip()
        if not ligne:
            continue
        if not texte:
            texte = ligne
            continue
        dernier = texte.split(" ")[-1]
        if texte.endswith(TRAIT_CONDITIONNEL):
            texte = texte[:-1] + ligne
            if journal is not None:
                premier = ligne.split(" ")[0]
                journal.append((dernier.rstrip(TRAIT_CONDITIONNEL) + "- " + premier, dernier.rstrip(TRAIT_CONDITIONNEL) + premier))
        elif texte.endswith("-") and ligne[:1].islower():
            premier = ligne.split(" ")[0]
            recolle = _recoller(dernier, premier)
            if recolle:
                texte = texte[: -len(dernier)] + recolle + ligne[len(premier):]
                if journal is not None:
                    journal.append((dernier + " " + premier, recolle))
            else:
                texte = texte + ligne  # trait d'union d'un mot composé : « souvenons-nous »
        else:
            texte = texte + " " + ligne
    return texte


_RE_COUPE = re.compile(r"\b([\wÀ-ÿ]{2,})- ([a-zà-ÿ][\wÀ-ÿ]*)")


def corriger_texte(texte: str, journal: list | None = None, apprises: dict[str, str] | None = None) -> str:
    """Corrections au niveau du texte entier (après assemblage)."""
    t = texte.replace(TRAIT_CONDITIONNEL, "")

    # Mots coupés restés au milieu d'une ligne : « commence- ments »
    def r_coupe(m: re.Match) -> str:
        colle = m.group(1) + m.group(2)
        if connu(colle) or not connu(m.group(2)):
            if journal is not None:
                journal.append((m.group(0), colle))
            return colle
        return m.group(0)

    t = _RE_COUPE.sub(r_coupe, t)

    # « II » / « *11 » pris pour « Il » quand ils sont au milieu du texte.
    def r_il(m: re.Match) -> str:
        if journal is not None:
            journal.append((m.group(1), "Il"))
        return "Il" + m.group(2)

    t = re.sub(r"(?<![\w*])(\*11|\*II|II|\*Il)(\s+[a-zà-ÿ’'])", r_il, t)

    t = corriger_references(t, journal)

    # Corrections apprises (mot exact -> remplacement), mémorisées depuis les aperçus précédents.
    if apprises:
        for avant, apres in apprises.items():
            motif = re.compile(rf"(?<![\w]){re.escape(avant)}(?![\w])")
            if motif.search(t):
                t = motif.sub(apres, t)
                if journal is not None:
                    journal.append((avant, apres))

    # Espaces : une seule, pas avant la virgule ou le point.
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" ([,.])", r"\1", t)
    t = re.sub(r"([.,;:!?»])(?=[A-ZÀ-Ü«])", r"\1 ", t)
    return t.strip()
