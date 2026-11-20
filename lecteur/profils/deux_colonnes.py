"""Profil « Commentaire 2 colonnes » : colonne de gauche puis colonne de droite, page après page."""
from . import generique

NOM = "deux_colonnes"


def construire(doc, pages, titre=None, apprises=None, livre_id="", progres=None):
    return generique.construire(doc, pages, 2, NOM, titre=titre, apprises=apprises, livre_id=livre_id, progres=progres)


def zones_page(page, numero):
    return generique._lignes_de_page(page, numero, 2)[1]
