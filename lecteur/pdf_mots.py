"""Extraction des mots d'une page PDF avec leur position, leur taille et leur police.

Fonctionne avec les PDF « scannés » (texte invisible ajouté par l'OCR, un mot par
segment) comme avec les PDF normaux (plusieurs mots par segment).
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

import pymupdf

_SANS = re.compile(r"arial|helv|sans|calibri|verdana|segoe|tahoma|futura|gill|franklin|myriad|frutiger|univers", re.I)
_GRAS = re.compile(r"bold|black|heavy|semibold|demi", re.I)
_ITAL = re.compile(r"italic|oblique|-it\b|ital", re.I)


@dataclass
class Mot:
    texte: str
    x0: float
    y0: float
    x1: float
    y1: float
    base: float  # ligne de base (y)
    taille: float
    sans: bool
    gras: bool
    italique: bool
    page: int  # numéro de page (1 = première)

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def largeur(self) -> float:
        return self.x1 - self.x0


def _proprietes(span: dict) -> tuple[bool, bool, bool]:
    nom = span.get("font", "")
    drapeaux = span.get("flags", 0)
    sans = bool(_SANS.search(nom))
    gras = bool(_GRAS.search(nom)) or bool(drapeaux & 16)
    italique = bool(_ITAL.search(nom)) or bool(drapeaux & 2)
    return sans, gras, italique


def mots_de_page(page: pymupdf.Page, numero: int) -> list[Mot]:
    """Retourne les mots de la page, dans l'ordre du PDF."""
    mots: list[Mot] = []
    brut = page.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP)
    for bloc in brut.get("blocks", []):
        if bloc.get("type") != 0:
            continue
        for ligne in bloc.get("lines", []):
            dx, dy = ligne.get("dir", (1, 0))
            if abs(dy) > 0.2:  # texte vertical (onglets tournés) : ignoré
                continue
            for span in ligne.get("spans", []):
                sans, gras, italique = _proprietes(span)
                courant: list[dict] = []
                for c in span.get("chars", []) + [None]:
                    if c is None or c["c"].isspace():
                        if courant:
                            texte = "".join(x["c"] for x in courant)
                            x0 = min(x["bbox"][0] for x in courant)
                            y0 = min(x["bbox"][1] for x in courant)
                            x1 = max(x["bbox"][2] for x in courant)
                            y1 = max(x["bbox"][3] for x in courant)
                            mots.append(
                                Mot(texte, x0, y0, x1, y1, courant[0]["origin"][1], span.get("size", 10.0),
                                    sans, gras, italique, numero)
                            )
                            courant = []
                    else:
                        courant.append(c)
    return mots


def taille_corps(mots: list[Mot], sans: bool | None = None) -> float:
    """Taille de police la plus représentative du texte courant."""
    tailles = [m.taille for m in mots if len(m.texte) >= 3 and m.texte.isalpha() and (sans is None or m.sans == sans)]
    if not tailles:
        tailles = [m.taille for m in mots]
    return statistics.median(tailles) if tailles else 10.0


def grouper_en_lignes(mots: list[Mot], tolerance: float | None = None) -> list[list[Mot]]:
    """Regroupe des mots en lignes (par hauteur), chaque ligne triée de gauche à droite."""
    if not mots:
        return []
    corps = taille_corps(mots)
    tol = tolerance if tolerance is not None else corps * 0.45
    tries = sorted(mots, key=lambda m: (m.yc, m.x0))
    lignes: list[list[Mot]] = []
    centres: list[float] = []
    for m in tries:
        # Les grands caractères (lettrines) ne servent pas de référence de ligne.
        if lignes and abs(m.yc - centres[-1]) <= tol:
            lignes[-1].append(m)
            normaux = [x.yc for x in lignes[-1] if x.taille <= corps * 1.4] or [x.yc for x in lignes[-1]]
            centres[-1] = statistics.median(normaux)
        else:
            lignes.append([m])
            centres.append(m.yc)
    for l in lignes:
        l.sort(key=lambda m: m.x0)
    return lignes


def colle(precedent: Mot, mot: Mot) -> bool:
    """Vrai si deux mots se touchent (« l » + « ’ » + « Eternel ») : pas d'espace entre eux."""
    return mot.x0 - precedent.x1 < max(0.8, 0.1 * min(precedent.taille, mot.taille))


def texte_ligne(ligne: list[Mot]) -> str:
    morceaux: list[str] = []
    for i, m in enumerate(ligne):
        if i and not colle(ligne[i - 1], m):
            morceaux.append(" ")
        morceaux.append(m.texte)
    return "".join(morceaux)
