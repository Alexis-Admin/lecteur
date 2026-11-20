"""Captures d'écran (OCR Windows), texte collé, pages web (sans Internet : on teste l'extraction sur du texte)."""
from pathlib import Path

import pymupdf
import pytest

from lecteur.nettoyage import corriger_texte
from lecteur.ocr_image import langues_disponibles
from lecteur.texte_brut import _retirer_sections_inutiles, livre_depuis_images, livre_depuis_texte


def test_texte_colle_avec_lignes_vides():
    texte = "Chapitre premier\n\nLe potier prit l'argile et com-\nmença à la façonner.\nIl travailla longtemps.\n\nDeuxième partie\nUne seule ligne ici."
    livre = livre_depuis_texte(texte, "Essai")
    assert [s.titre for s in livre.sections] == ["Chapitre premier", "Deuxième partie"]
    assert livre.sections[0].blocs[1].texte == "Le potier prit l'argile et commença à la façonner. Il travailla longtemps."
    assert livre.sections[1].blocs[1].texte == "Une seule ligne ici."


def test_texte_colle_sans_lignes_vides():
    texte = "Premier paragraphe qui se termine.\nDeuxième paragraphe qui continue\nsur la ligne suivante."
    livre = livre_depuis_texte(texte, "Essai")
    paras = [b.texte for b in livre.sections[0].blocs]
    assert paras == ["Premier paragraphe qui se termine.", "Deuxième paragraphe qui continue sur la ligne suivante."]


def test_texte_vide_refuse():
    with pytest.raises(ValueError):
        livre_depuis_texte("   \n\n  ", "Vide")


def test_markdown_de_page_web():
    md = "# Titre\n\nUn **paragraphe** avec un [lien](http://x)<sup>\\[92\\]</sup>.\n\n## Notes et références\n\n1. source\n\n### Sous-note\n\nencore\n\n## Suite\n\nTexte final."
    propre = _retirer_sections_inutiles(md)
    assert "source" not in propre and "Sous-note" not in propre and "Texte final" in propre
    livre = livre_depuis_texte(md, "Page", markdown=True)
    assert [s.titre for s in livre.sections] == ["Titre", "Suite"]
    assert livre.sections[0].blocs[1].texte == "Un paragraphe avec un lien."


def test_alphabets_etrangers():
    from lecteur.douteux import raison
    from lecteur.prononciation import a_lire

    assert raison("Βιβλίον", set()) is None
    assert a_lire("Le Livre de la Genèse (hébreu : סֵפֶר) est le premier livre.") == "Le Livre de la Genèse (hébreu :) est le premier livre."
    assert a_lire("été") == "été"  # accents décomposés recomposés, pas supprimés


def test_erreurs_ocr_des_captures():
    assert corriger_texte("1'espèce humaine") == "l'espèce humaine"
    assert corriger_texte("«juste et intègre)) ne") == "«juste et intègre» ne"


@pytest.mark.skipif(not any(l.startswith("fr") for l in langues_disponibles()), reason="OCR Windows français absent")
def test_capture_ocr(tmp_path: Path):
    # Une « capture » fabriquée : texte inventé rendu en image.
    doc = pymupdf.open()
    page = doc.new_page(width=500, height=200)
    page.insert_text((30, 50), "Le potier façonne un vase magnifique.", fontname="tiro", fontsize=16)
    page.insert_text((30, 80), "Il le pose ensuite au soleil.", fontname="tiro", fontsize=16)
    img = tmp_path / "capture.png"
    page.get_pixmap(dpi=200).save(img)
    livre, analyses = livre_depuis_images([img], 1, "Capture")
    texte = " ".join(b.texte for s in livre.sections for b in s.blocs)
    assert "potier" in texte and "soleil" in texte
    assert analyses[0]["zones"]
