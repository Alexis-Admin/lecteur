"""Profil « Commentaire 2 colonnes » : colonne de gauche puis colonne de droite, page après page."""
from . import generique

NOM = "deux_colonnes"


def construire(doc, pages, titre=None, apprises=None, livre_id=""):
    return generique.construire(doc, pages, 2, NOM, titre=titre, apprises=apprises, livre_id=livre_id)
