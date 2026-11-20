"""Profil « Livre simple » : une colonne, page après page."""
from . import generique

NOM = "simple"


def construire(doc, pages, titre=None, apprises=None, livre_id=""):
    return generique.construire(doc, pages, 1, NOM, titre=titre, apprises=apprises, livre_id=livre_id)
