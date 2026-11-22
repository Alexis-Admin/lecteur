"""Profils génériques : livre à une colonne, ou commentaire à deux colonnes (gauche puis droite).

Ignore en-têtes, pieds de page et numéros de page. Repère les titres (plus gros ou en gras)
pour découper en sections ; sans titre, coupe environ toutes les 1 500 mots.
Sert aussi aux captures d'écran (mots venant de l'OCR de Windows).
"""
from __future__ import annotations

import re
import statistics
from typing import Callable

import pymupdf

from ..modele import Bloc, Livre, Section
from ..nettoyage import assembler, corriger_texte, nettoyer_mot
from ..pdf_mots import Mot, colle, grouper_en_lignes, mots_de_page, taille_corps, texte_ligne

MOTS_PAR_SECTION = 1500

# source(numero) -> (mots, largeur, hauteur, couper_les_bords)
Source = Callable[[int], tuple[list[Mot], float, float, bool]]


def _gouttiere(mots: list[Mot], largeur: float) -> float | None:
    """Bande verticale vide qui sépare deux blocs de texte (colonnes, ou encadrés sur le côté), ou None."""
    if len(mots) < 30:
        return None
    couverture = [0] * (int(largeur) + 2)
    for m in mots:
        for x in range(max(0, int(m.x0)), min(int(m.x1) + 1, len(couverture))):
            couverture[x] += 1
    # Seulement entre le premier et le dernier mot : les marges vides de la page ne sont pas une gouttière.
    gauche_txt = int(min(m.x0 for m in mots)) + 1
    droite_txt = int(max(m.x1 for m in mots)) - 1
    a, b = max(int(largeur * 0.12), gauche_txt), min(int(largeur * 0.88), droite_txt)
    meilleure, debut = None, None
    for x in range(a, b + 1):
        if couverture[x] == 0 and x < b:
            debut = x if debut is None else debut
        elif debut is not None:
            if x - debut >= largeur * 0.012 and (meilleure is None or x - debut > meilleure[1] - meilleure[0]):
                meilleure = (debut, x)
            debut = None
    if not meilleure:
        return None
    milieu = (meilleure[0] + meilleure[1]) / 2
    gauche = sum(1 for m in mots if (m.x0 + m.x1) / 2 < milieu)
    if min(gauche, len(mots) - gauche) < 15:
        return None
    return milieu


def _colonnes_auto(mots: list[Mot], largeur: float) -> list[tuple[list[Mot], bool]]:
    """Une colonne, deux colonnes, ou un texte avec des encadrés sur le côté : [(mots, est_un_encadré)].

    Les encadrés (colonne nettement plus étroite que l'autre) sont lus à part, à la fin de la section :
    sinon leurs lignes se mélangent à celles du texte (« prisonroi », « aveccritiquéHérodiade »).
    """
    milieu = _gouttiere(mots, largeur)
    if milieu is None:
        return [(mots, False)]
    g = [m for m in mots if (m.x0 + m.x1) / 2 < milieu]
    d = [m for m in mots if (m.x0 + m.x1) / 2 >= milieu]
    lg = max(m.x1 for m in g) - min(m.x0 for m in g)
    ld = max(m.x1 for m in d) - min(m.x0 for m in d)
    if min(lg, ld) < 0.6 * max(lg, ld):
        etroit_gauche = lg < ld
        return [(d, False), (g, True)] if etroit_gauche else [(g, False), (d, True)]
    return [(g, False), (d, False)]


def _colonnes(mots: list[Mot], largeur: float, nb: int) -> list[list[Mot]]:
    if nb == 1 or not mots:
        return [mots]
    # Gouttière : bande verticale la moins couverte au milieu de la page.
    couverture = [0] * int(largeur + 1)
    for m in mots:
        for x in range(max(0, int(m.x0)), min(int(m.x1) + 1, len(couverture))):
            couverture[x] += 1
    a, b = int(largeur * 0.35), int(largeur * 0.65)
    milieu = min(range(a, b), key=lambda x: (couverture[x], abs(x - largeur / 2)))
    return [[m for m in mots if m.x1 <= milieu + 2 or (m.x0 + m.x1) / 2 < milieu],
            [m for m in mots if not (m.x1 <= milieu + 2 or (m.x0 + m.x1) / 2 < milieu)]]


def lignes_de_mots(mots: list[Mot], W: float, H: float, numero: int, nb_colonnes: int,
                   couper_bords: bool = True) -> tuple[list[dict], list[dict], float]:
    mots = [m for m in mots if m.texte.strip()]
    haut, bas = (H * 0.06, H * 0.95) if couper_bords else (-1, H + 1)
    ignores = [m for m in mots if m.y1 <= haut or m.y0 >= bas]
    mots = [m for m in mots if m.y1 > haut and m.y0 < bas]
    corps = taille_corps(mots)
    zones = []
    if ignores:
        zones.append({"genre": "ignore", "x0": min(m.x0 for m in ignores), "y0": min(m.y0 for m in ignores),
                      "x1": max(m.x1 for m in ignores), "y1": max(m.y1 for m in ignores)})
    sortie: list[dict] = []
    colonnes = _colonnes_auto(mots, W) if nb_colonnes == 1 else [(c, False) for c in _colonnes(mots, W, nb_colonnes)]
    for col, encadre in colonnes:
        if not col:
            continue
        x_gauche = statistics.median(sorted(m.x0 for m in col)[: max(1, len(col) // 10)])
        x_droite = max(m.x1 for m in col)
        zones.append({"genre": "encadre" if encadre else "bible", "x0": min(m.x0 for m in col),
                      "y0": min(m.y0 for m in col), "x1": x_droite, "y1": max(m.y1 for m in col)})
        precedente = None
        for ligne in grouper_en_lignes(col):
            txt = texte_ligne(ligne)
            taille = statistics.median(m.taille for m in ligne)
            if re.fullmatch(r"[\divxlcIVXLC\-–— ]{1,8}", txt):
                # Gros chiffre seul en haut d'une page : numéro de chapitre (« 2 » au-dessus de « RHYS »).
                if not encadre and taille >= 1.5 * corps and ligne[0].y0 < 0.5 * H and re.fullmatch(r"\d{1,3}|[IVXLC]{1,6}", txt.strip()):
                    sortie.append({"texte": txt.strip(), "mots": ligne, "titre": False, "nouveau": True, "ecart": True,
                                   "encadre": False, "numero_chapitre": True, "y0": ligne[0].y0,
                                   "y1": max(m.y1 for m in ligne), "x1": max(m.x1 for m in ligne), "page": numero, "H": H})
                continue  # sinon : numéro de page égaré
            alinea = ligne[0].x0 - x_gauche > 1.2 * corps
            ecart = precedente is not None and ligne[0].y0 - precedente["y1"] > 0.9 * corps
            # Titre : plus gros ou en gras, MAIS aussi court, détaché du texte au-dessus, qui commence par une
            # majuscule ou un chiffre et qui n'est ni un dialogue ni une fin de phrase. Sur les scans, la
            # reconnaissance de texte grossit ou met en gras des lignes ordinaires (roman : 93 faux chapitres).
            titre = ((taille >= 1.18 * corps or all(m.gras for m in ligne)) and len(ligne) <= 10
                     and (precedente is None or ecart)
                     and bool(re.match(r"[A-ZÀ-Ü0-9ÉÈ«\"]", txt)) and len(re.sub(r"\W", "", txt)) >= 2
                     and not re.search(r"[.,;:!?…»]$", txt)
                     and not re.search(r"[a-zà-ÿ][.;!?]\s+\S", txt))  # « faveur. 4 Il posera » : une phrase, pas un titre
            courte = precedente is not None and precedente["x1"] < x_droite - 4 * corps and re.search(r"[.!?»:]$", precedente["texte"])
            sortie.append({"texte": txt, "mots": ligne, "titre": titre, "nouveau": bool(alinea or ecart or courte),
                           "ecart": bool(ecart), "encadre": encadre, "y0": min(m.y0 for m in ligne),
                           "y1": max(m.y1 for m in ligne), "x1": max(m.x1 for m in ligne), "page": numero, "H": H})
            precedente = sortie[-1]
    return sortie, zones, corps


def _lignes_de_page(page: pymupdf.Page, numero: int, nb_colonnes: int) -> tuple[list[dict], list[dict], float]:
    return lignes_de_mots(mots_de_page(page, numero), page.rect.width, page.rect.height, numero, nb_colonnes)


def assembler_sections(livre: Livre, paragraphes: list[tuple[str, str, int | None]], min_mots: int = 0) -> None:
    """(genre, texte, page) -> sections du livre. Titres consécutifs fusionnés ; longues parties coupées."""
    n = 0

    def nid() -> str:
        nonlocal n
        n += 1
        return f"b{n:05d}"

    section: Section | None = None
    mots_section = 0
    for genre, texte, page in paragraphes:
        if not texte:
            continue
        if genre == "encadre":
            if section is None:
                section = Section(f"s{len(livre.sections) + 1:03d}", f"Partie {len(livre.sections) + 1}")
                livre.sections.append(section)
            section.blocs.append(Bloc(nid(), "notes", "encadre", texte, page=page))
            continue
        if genre == "titre":
            if section and section.blocs and all(b.genre == "titre" for b in section.blocs):
                section.titre += " — " + texte
                section.blocs.append(Bloc(nid(), "texte", "titre", texte, page=page))
                continue
            section = Section(f"s{len(livre.sections) + 1:03d}", texte)
            livre.sections.append(section)
            section.blocs.append(Bloc(nid(), "texte", "titre", texte, page=page))
            mots_section = 0
            continue
        nb = len(texte.split())
        # Sans titre (ou section très longue) : on coupe environ tous les MOTS_PAR_SECTION mots.
        # Un vrai chapitre n'est coupé que s'il est très long (≈ 1 h d'écoute) ; sans titre : environ 10 min.
        trop_long = mots_section >= (MOTS_PAR_SECTION if section and section.titre.startswith("Partie ") else MOTS_PAR_SECTION * 6)
        if section is None or trop_long:
            titre_s = f"Partie {len(livre.sections) + 1}" if section is None or section.titre.startswith("Partie ") \
                else f"{section.titre} (suite)"
            section = Section(f"s{len(livre.sections) + 1:03d}", titre_s)
            livre.sections.append(section)
            mots_section = 0
        section.blocs.append(Bloc(nid(), "texte", "paragraphe", texte, page=page))
        mots_section += nb
    fusionner_petites_sections(livre, min_mots=min_mots)


def fusionner_petites_sections(livre: Livre, min_mots: int = 0) -> None:
    """Une section sans texte (titre seul : « Au chef de chœur. ») ou minuscule (page de copyright) est réunie
    à la suivante : sinon la liste des sections se remplit de morceaux de quelques mots."""
    res: list[Section] = []
    attente: Section | None = None
    for s in livre.sections:
        if attente is not None:
            s.blocs = attente.blocs + s.blocs
            if any(b.genre == "titre" for b in attente.blocs):
                s.titre = attente.titre
            attente = None
        corps = [b for b in s.blocs if b.genre not in ("titre", "partie")]
        mots = sum(len(b.texte.split()) for b in corps if b.piste == "texte")
        if not corps or (min_mots and mots < min_mots):
            attente = s
            continue
        res.append(s)
    if attente is not None:  # la dernière section est petite : on la garde (ou on la colle à la précédente)
        if res and not any(b.genre not in ("titre", "partie") for b in attente.blocs):
            res[-1].blocs += attente.blocs
        else:
            res.append(attente)
    livre.sections = res


_FIN_PHRASE = re.compile(r"[.!?…»:\"”)]\s*$")


def recoller_paragraphes(paragraphes: list[tuple[str, str, int]], journal: list) -> list[tuple[str, str, int]]:
    """Un paragraphe qui commence par une minuscule continue le précédent (coupé par un changement de page,
    un en-tête retiré ou une colonne) : on les recolle, en refaisant le mot coupé s'il y en a un."""
    res: list[list] = []
    dernier = None  # index du dernier paragraphe de texte
    for genre, texte, page in paragraphes:
        if (genre == "paragraphe" and dernier is not None and re.match(r"[a-zà-ÿ]", texte)
                and not _FIN_PHRASE.search(res[dernier][1])):
            avant = res[dernier][1]
            colle = assembler([avant, texte], journal)
            res[dernier][1] = colle
            continue
        res.append([genre, texte, page])
        if genre == "paragraphe":
            dernier = len(res) - 1
        elif genre == "titre":
            dernier = None
    return [tuple(x) for x in res]


def _signature(txt: str) -> str:
    return re.sub(r"[\d\W_]+", " ", txt).strip().lower()


def entetes_repetes(pages_lignes: list[tuple[int, list[dict]]]) -> set[str]:
    """Lignes du haut ou du bas de page qui se répètent d'une page à l'autre (titre du livre, nom de l'auteur,
    « LE BUT 13 ») : ce sont des en-têtes et des pieds de page, pas des titres de chapitre."""
    if len(pages_lignes) < 3:
        return set()
    vues: dict[str, set[int]] = {}
    for p, lignes in pages_lignes:
        principales = [l for l in lignes if not l.get("encadre")]
        for l in principales[:2] + principales[-2:]:
            sig = _signature(l["texte"])
            haut = l["y0"] < 0.14 * l["H"]
            bas = l["y1"] > 0.88 * l["H"]
            if sig and len(sig) <= 60 and (haut or bas):
                vues.setdefault(sig, set()).add(p)
    seuil = max(2, round(0.08 * len(pages_lignes)))
    return {s for s, pages in vues.items() if len(pages) >= seuil}


_MOTS_EN = {"the", "and", "of", "to", "is", "you", "that", "with", "for", "your", "this", "it", "are", "was", "be"}
_MOTS_FR = {"le", "la", "les", "et", "de", "des", "un", "une", "est", "que", "qui", "dans", "pour", "pas", "il"}


def detecter_langue(textes: list[str]) -> str:
    mots = re.findall(r"[a-zà-ÿ]+", " ".join(textes[:400]).lower())
    en = sum(1 for m in mots if m in _MOTS_EN)
    fr = sum(1 for m in mots if m in _MOTS_FR)
    return "en" if en > 2 * fr and en >= 20 else "fr"


def construire_depuis(source: Source, pages: list[int], nb_colonnes: int, nom_profil: str, titre: str | None = None,
                      apprises: dict[str, str] | None = None, livre_id: str = "", progres=None):
    livre = Livre(livre_id, titre or "Livre", nom_profil, "", pages)
    journal: list[tuple[str, str, int]] = []
    analyses = []
    paragraphes: list[tuple[str, str, int]] = []
    courant: list[str] = []
    page_courant = pages[0] if pages else 1

    def nettoyer_ligne(ligne: dict) -> str:
        j: list = []
        texte, precedent = "", None
        for m in ligne["mots"]:
            propre = nettoyer_mot(m.texte, j)
            if propre:
                texte += propre if (not texte or (precedent and colle(precedent, m))) else " " + propre
                precedent = m
        journal.extend((a, b, ligne["page"]) for a, b in j)
        return texte

    def fermer():
        nonlocal courant
        if courant:
            j: list = []
            t = corriger_texte(assembler(courant, j), j, apprises)
            journal.extend((a, b, page_courant) for a, b in j)
            if t:
                paragraphes.append(("paragraphe", t, page_courant))
        courant = []

    # 1. Lire toutes les pages, puis repérer les en-têtes et pieds de page répétés.
    pages_lignes = []
    for i, p in enumerate(pages):
        if progres:
            progres(i + 1, len(pages))
        mots, W, H, couper = source(p)
        lignes, zones, _ = lignes_de_mots(mots, W, H, p, nb_colonnes, couper)
        analyses.append({"numero": p, "zones": zones, "largeur": W, "hauteur": H})
        pages_lignes.append((p, lignes))
    entetes = entetes_repetes(pages_lignes)
    numero_chapitre: str | None = None

    # 2. Texte principal en paragraphes ; encadrés à part.
    for p, lignes in pages_lignes:
        encadre: list[str] = []

        def fermer_encadre():
            nonlocal encadre
            if encadre:
                j: list = []
                t = corriger_texte(assembler(encadre, j), j, apprises)
                journal.extend((a, b, p) for a, b in j)
                if t and len(t.split()) >= 3:
                    paragraphes.append(("encadre", t, p))
            encadre = []

        for l in lignes:
            if l.get("numero_chapitre"):
                fermer()
                numero_chapitre = l["texte"]
                continue
            if _signature(l["texte"]) in entetes and (l["y0"] < 0.14 * l["H"] or l["y1"] > 0.88 * l["H"]):
                continue
            if l["encadre"]:
                if l["ecart"] or l["titre"]:
                    fermer_encadre()
                encadre.append(nettoyer_ligne(l))
                continue
            if l["titre"]:
                fermer()
                t = nettoyer_ligne(l)
                if t.isupper():
                    t = t.title()  # « BRIDGET » → « Bridget » (plus lisible dans la liste)
                if numero_chapitre:
                    t = f"Chapitre {numero_chapitre} · {t}"
                    numero_chapitre = None
                paragraphes.append(("titre", t, p))
                continue
            if numero_chapitre:  # numéro sans titre : le chapitre s'appelle « Chapitre 3 »
                paragraphes.append(("titre", f"Chapitre {numero_chapitre}", p))
                numero_chapitre = None
            if l["nouveau"]:
                fermer()
            if not courant:
                page_courant = p
            courant.append(nettoyer_ligne(l))
        fermer_encadre()
    fermer()
    paragraphes = recoller_paragraphes(paragraphes, journal_pages := [])
    journal.extend((a, b, page_courant) for a, b in journal_pages)
    livre.langue = detecter_langue([t for g, t, _ in paragraphes if g == "paragraphe"])
    assembler_sections(livre, paragraphes, min_mots=60)  # scans : pages de garde et de copyright réunies
    livre.corrections = [{"avant": a, "apres": b, "page": p} for a, b, p in journal if a != b]
    return livre, analyses


def construire(doc: pymupdf.Document, pages: list[int], nb_colonnes: int, nom_profil: str, titre: str | None = None,
               apprises: dict[str, str] | None = None, livre_id: str = "", progres=None):
    def source(p: int):
        page = doc[p - 1]
        return mots_de_page(page, p), page.rect.width, page.rect.height, True

    return construire_depuis(source, pages, nb_colonnes, nom_profil, titre, apprises, livre_id, progres)
