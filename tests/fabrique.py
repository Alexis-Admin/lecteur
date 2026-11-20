"""Fabrique de faux PDF pour les tests (texte inventé : aucun contenu protégé dans le dépôt)."""
from __future__ import annotations

import pymupdf


def _ecrire(page, x, y, texte, police="tiro", taille=11):
    page.insert_text((x, y), texte, fontname=police, fontsize=taille)


def page_bible_etude(doc: pymupdf.Document, *, premiere=True) -> None:
    """Une page imitant une Bible d'étude : en-tête, intertitre, lettrine, versets, renvois de marge,
    onglets, note de traduction et notes sur deux colonnes."""
    page = doc.new_page(width=520, height=730)
    _ecrire(page, 68, 34, "LIVRET 1.1", "heit", 10)  # en-tête (nom du livre inventé)
    _ecrire(page, 490, 34, "14", "heit", 9)  # numéro de page
    _ecrire(page, 490, 80, "Gn", "hebo", 6)  # onglet
    _ecrire(page, 70, 70, "Le jardin des essais", "tiit", 11)  # intertitre
    _ecrire(page, 70, 100, "1", "hebo", 26)  # lettrine du chapitre 1
    _ecrire(page, 92, 88, "Au commencement un potier modela un vase sur son tour", "tiro", 11)
    _ecrire(page, 70, 101, "et le posa au soleil.", "tiro", 11)
    _ecrire(page, 172, 101, "2", "tiro", 8)
    _ecrire(page, 180, 101, "Le vase devint dur comme la pierre", "tiro", 11)
    _ecrire(page, 455, 101, "1.2", "hebo", 6)  # renvoi de marge
    _ecrire(page, 70, 114, "et brilla au soleil du matin.", "tiro", 11)
    _ecrire(page, 205, 114, "3", "tiro", 8)
    _ecrire(page, 213, 114, "Le potier fut content et dit: «II est", "tiro", 11)
    _ecrire(page, 70, 127, "magnifique.» Puis il recom­", "tiro", 11)
    _ecrire(page, 70, 140, "mença le travail.", "tiro", 11)
    _ecrire(page, 160, 140, "4", "tiro", 8)
    _ecrire(page, 168, 140, "*11 fit encore dix vases (voir Lc 2.4a).", "tiro", 11)
    _ecrire(page, 70, 160, "Le second atelier", "tiit", 11)
    _ecrire(page, 70, 174, "5", "tiro", 8)
    _ecrire(page, 78, 174, "Le lendemain, il vendit les vases au marché.", "tiro", 11)
    _ecrire(page, 70, 190, "a 1.2 Dur: litt. cuit au four.", "heit", 7)  # note de traduction
    # Notes sur deux colonnes
    gauche = ["1.1 Le potier représente le soin que", "l'on met à bien faire les choses", "(cf. 1.4).",
              "1.3-4 La joie du travail accompli est", "une bonne chose; voir Ps 150.3-5."]
    droite = ["suite de la note de gauche qui continue", "dans la colonne de droite.",
              "1.5 Le marché est un lieu d'échange", "et de rencontre, p. ex. le samedi."]
    # La colonne de droite doit être lue APRÈS celle de gauche.
    for i, l in enumerate(gauche):
        _ecrire(page, 72, 620 + i * 9, l, "helv", 7)
    for i, l in enumerate(droite):
        _ecrire(page, 290, 620 + i * 9, l, "helv", 7)


def pdf_bible_etude(chemin) -> None:
    doc = pymupdf.open()
    page_bible_etude(doc)
    doc.save(chemin)


def pdf_deux_colonnes(chemin) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=520, height=730)
    _ecrire(page, 230, 30, "Commentaire inventé", "tiro", 9)  # en-tête
    _ecrire(page, 60, 70, "Premier chapitre", "tibo", 15)
    g = ["La colonne de gauche commence ici et", "se poursuit sur plusieurs lignes pour", "former un paragraphe complet."]
    d = ["La colonne de droite vient ensuite et", "termine la page proprement."]
    for i, l in enumerate(g):
        _ecrire(page, 60, 100 + i * 14, l, "tiro", 11)
    for i, l in enumerate(d):
        _ecrire(page, 280, 100 + i * 14, l, "tiro", 11)
    _ecrire(page, 255, 715, "7", "tiro", 9)  # numéro de page
    doc.save(chemin)
