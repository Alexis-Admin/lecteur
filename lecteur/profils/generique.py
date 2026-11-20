"""Profils génériques : livre à une colonne, ou commentaire à deux colonnes (gauche puis droite).

Ignore en-têtes, pieds de page et numéros de page. Repère les titres (plus gros ou en gras)
pour découper en sections ; sans titre, coupe environ toutes les 1 500 mots.
"""
from __future__ import annotations

import re
import statistics

import pymupdf

from ..modele import Bloc, Livre, Section
from ..nettoyage import assembler, corriger_texte, nettoyer_mot
from ..pdf_mots import Mot, grouper_en_lignes, mots_de_page, taille_corps, texte_ligne

MOTS_PAR_SECTION = 1500


def _colonnes(mots: list[Mot], largeur: float, nb: int) -> list[list[Mot]]:
    if nb == 1 or not mots:
        return [mots]
    # Gouttière : bande verticale la moins couverte au milieu de la page.
    couverture = [0] * int(largeur + 1)
    for m in mots:
        for x in range(int(m.x0), min(int(m.x1) + 1, len(couverture))):
            couverture[x] += 1
    a, b = int(largeur * 0.35), int(largeur * 0.65)
    milieu = min(range(a, b), key=lambda x: (couverture[x], abs(x - largeur / 2)))
    return [[m for m in mots if m.x1 <= milieu + 2 or (m.x0 + m.x1) / 2 < milieu],
            [m for m in mots if not (m.x1 <= milieu + 2 or (m.x0 + m.x1) / 2 < milieu)]]


def _lignes_de_page(page: pymupdf.Page, numero: int, nb_colonnes: int) -> tuple[list[dict], list[dict], float]:
    W, H = page.rect.width, page.rect.height
    mots = [m for m in mots_de_page(page, numero) if m.texte.strip()]
    haut, bas = H * 0.06, H * 0.95
    ignores = [m for m in mots if m.y1 <= haut or m.y0 >= bas]
    mots = [m for m in mots if m.y1 > haut and m.y0 < bas]
    corps = taille_corps(mots)
    zones = []
    if ignores:
        zones.append({"genre": "ignore", "x0": min(m.x0 for m in ignores), "y0": min(m.y0 for m in ignores),
                      "x1": max(m.x1 for m in ignores), "y1": max(m.y1 for m in ignores)})
    sortie: list[dict] = []
    for col in _colonnes(mots, W, nb_colonnes):
        if not col:
            continue
        x_gauche = statistics.median(sorted(m.x0 for m in col)[: max(1, len(col) // 10)])
        x_droite = max(m.x1 for m in col)
        zones.append({"genre": "bible", "x0": min(m.x0 for m in col), "y0": min(m.y0 for m in col),
                      "x1": x_droite, "y1": max(m.y1 for m in col)})
        precedente = None
        for ligne in grouper_en_lignes(col):
            txt = texte_ligne(ligne)
            if re.fullmatch(r"[\divxlcIVXLC\-–— ]{1,8}", txt):  # numéro de page égaré
                continue
            taille = statistics.median(m.taille for m in ligne)
            titre = (taille >= 1.18 * corps or all(m.gras for m in ligne)) and len(ligne) <= 16
            alinea = ligne[0].x0 - x_gauche > 1.2 * corps
            ecart = precedente is not None and ligne[0].y0 - precedente["y1"] > 0.9 * corps
            courte = precedente is not None and precedente["x1"] < x_droite - 4 * corps and re.search(r"[.!?»:]$", precedente["texte"])
            sortie.append({"texte": txt, "mots": ligne, "titre": titre, "nouveau": bool(alinea or ecart or courte),
                           "y1": max(m.y1 for m in ligne), "x1": max(m.x1 for m in ligne), "page": numero})
            precedente = sortie[-1]
    return sortie, zones, corps


def construire(doc: pymupdf.Document, pages: list[int], nb_colonnes: int, nom_profil: str, titre: str | None = None,
               apprises: dict[str, str] | None = None, livre_id: str = "", progres=None):
    livre = Livre(livre_id, titre or "Livre", nom_profil, "", pages)
    journal: list[tuple[str, str, int]] = []
    analyses = []
    paragraphes: list[tuple[str, str, int]] = []  # (genre, texte, page)
    courant: list[str] = []
    page_courant = pages[0] if pages else 1

    def nettoyer_ligne(ligne: dict) -> str:
        j: list = []
        mots = [nettoyer_mot(m.texte, j) for m in ligne["mots"]]
        journal.extend((a, b, ligne["page"]) for a, b in j)
        return " ".join(m for m in mots if m)

    def fermer():
        nonlocal courant
        if courant:
            j: list = []
            t = corriger_texte(assembler(courant, j), j, apprises)
            journal.extend((a, b, page_courant) for a, b in j)
            if t:
                paragraphes.append(("paragraphe", t, page_courant))
        courant = []

    for i, p in enumerate(pages):
        if progres:
            progres(i + 1, len(pages))
        lignes, zones, _ = _lignes_de_page(doc[p - 1], p, nb_colonnes)
        analyses.append({"numero": p, "zones": zones, "largeur": doc[p - 1].rect.width, "hauteur": doc[p - 1].rect.height})
        for l in lignes:
            if l["titre"]:
                fermer()
                paragraphes.append(("titre", nettoyer_ligne(l), p))
                continue
            if l["nouveau"]:
                fermer()
            if not courant:
                page_courant = p
            courant.append(nettoyer_ligne(l))
    fermer()

    # Titres consécutifs fusionnés ; sections.
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
        trop_long = mots_section >= (MOTS_PAR_SECTION if section and section.titre.startswith("Partie ") else MOTS_PAR_SECTION * 3)
        if section is None or trop_long:
            titre_s = f"Partie {len(livre.sections) + 1}" if section is None or section.titre.startswith("Partie ") \
                else f"{section.titre} (suite)"
            section = Section(f"s{len(livre.sections) + 1:03d}", titre_s)
            livre.sections.append(section)
            mots_section = 0
        section.blocs.append(Bloc(nid(), "texte", "paragraphe", texte, page=page))
        mots_section += nb
    livre.corrections = [{"avant": a, "apres": b, "page": p} for a, b, p in journal if a != b]
    return livre, analyses
