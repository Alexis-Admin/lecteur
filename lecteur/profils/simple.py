"""Profil « Livre simple » : une colonne, page après page."""
from . import generique

NOM = "simple"


def construire(doc, pages, titre=None, apprises=None, livre_id="", progres=None):
    return generique.construire(doc, pages, 1, NOM, titre=titre, apprises=apprises, livre_id=livre_id, progres=progres)


def zones_page(page, numero):
    return generique._lignes_de_page(page, numero, 1)[1]
