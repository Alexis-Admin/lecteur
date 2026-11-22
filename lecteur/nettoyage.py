"""Correction automatique des erreurs d'OCR et assemblage des lignes en texte continu.

Chaque correction est notée dans un journal (avant, après) pour l'aperçu.
"""
from __future__ import annotations

import re
import unicodedata

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


def _sans_trait(dernier: str, ligne: str) -> str | None:
    """« maî » + « trisait » → « maîtrisait » quand le trait d'union a disparu, seulement si l'un des deux
    morceaux n'est pas un mot et que le mot recollé en est un."""
    premier = ligne.split(" ")[0]
    if not re.fullmatch(r"[A-Za-zÀ-ÿœ’']{2,}", dernier) or not re.match(r"[a-zà-ÿœ]{2,}", premier):
        return None
    tete = re.match(r"[a-zà-ÿœ]+", premier).group(0)
    if connu(dernier) and connu(tete):
        return None
    if connu(dernier + tete):
        return dernier + premier
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
        elif (sans := _sans_trait(dernier, ligne)) is not None:
            # Mot coupé en fin de ligne dont le scan a perdu le trait d'union : « problè » + « mes ».
            premier = ligne.split(" ")[0]
            texte = texte[: -len(dernier)] + sans + ligne[len(premier):]
            if journal is not None:
                journal.append((dernier + " " + premier, sans))
        else:
            texte = texte + " " + ligne
    return texte


_RE_COUPE = re.compile(r"\b([\wÀ-ÿ]{2,})- ([a-zà-ÿ][\wÀ-ÿ]*)")


def recoller_coupures(texte: str, journal: list | None = None) -> str:
    """« maî trisait », « cer titude » : un mot coupé en deux par le scan, recollé si l'un des morceaux n'est pas
    un mot et que le mot entier en est un."""
    mots = re.sub(r" {2,}", " ", texte).split(" ")
    res: list[str] = []
    i = 0
    while i < len(mots):
        a = mots[i]
        if i + 1 < len(mots) and re.fullmatch(r"[A-Za-zÀ-ÿœ]{2,}", a):
            b = mots[i + 1]
            m = re.match(r"([a-zà-ÿœ]{2,})(.*)$", b)
            if m and not re.search(r"\w", m.group(2)) and (not connu(a) or not connu(m.group(1))) \
                    and connu(a + m.group(1)):
                if journal is not None:
                    journal.append((f"{a} {m.group(1)}", a + m.group(1)))
                res.append(a + b)
                i += 2
                continue
        res.append(a)
        i += 1
    return " ".join(res)


def corriger_texte(texte: str, journal: list | None = None, apprises: dict[str, str] | None = None) -> str:
    """Corrections au niveau du texte entier (après assemblage)."""
    t = unicodedata.normalize("NFC", texte).replace(TRAIT_CONDITIONNEL, "")

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

    # Erreurs typiques de la reconnaissance de texte des captures : « 1'espèce », « intègre)) ».
    def r_sub(motif: str, rempl: str, texte: str) -> str:
        def f(m: re.Match) -> str:
            nouveau = m.expand(rempl)
            if journal is not None:
                journal.append((m.group(0), nouveau))
            return nouveau
        return re.sub(motif, f, texte)

    t = r_sub(r"(?<![\w\d])1(['’])(?=[a-zà-ÿ])", r"l\1", t)

    # Nombre collé au mot (« 33mais », « 3ans », « 15Il ») : on remet l'espace si le reste est un mot
    # (jamais pour « 1er », « 2e », « 3ème »).
    def r_num(m: re.Match) -> str:
        if re.fullmatch(r"(er|re|res|ers|e|es|ème|èmes|eme|nd|nde|ds?)", m.group(2)) or not connu(m.group(2)):
            return m.group(0)
        if journal is not None:
            journal.append((m.group(0), f"{m.group(1)} {m.group(2)}"))
        return f"{m.group(1)} {m.group(2)}"

    t = re.sub(r"(?<![\w.,:])(\d{1,3})([a-zà-ÿ][a-zà-ÿ’']+|Il|Ils|Elle|Elles|Et|Le|La|Les|Je|Nous|Vous|Car|Mais|Alors|Or|Ainsi|En|Dieu|Jésus)(?![\w])",
               r_num, t)

    # Appel de note collé à la fin d'un mot (« décennie2 », « laïque3. ») : on retire le chiffre.
    def r_appel(m: re.Match) -> str:
        if not connu(m.group(1)):
            return m.group(0)
        if journal is not None:
            journal.append((m.group(0), m.group(1)))
        return m.group(1)

    t = re.sub(r"(?<![\w\d])([a-zà-ÿœ]{3,})(\d{1,2})(?![\w\d.,]\d)", r_appel, t)
    t = r_sub(r"(?<=\w)\s?\)\)", "»", t)
    t = r_sub(r"\(\(\s?(?=\w)", "«", t)

    t = recoller_coupures(t, journal)
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
