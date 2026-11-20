from pathlib import Path

from lecteur.importer import importer_pdf, lire_pages
from lecteur.modele import Livre, liste_de_lecture
from tests.fabrique import pdf_bible_etude, pdf_deux_colonnes


def _blocs(livre):
    return [b for s in livre.sections for b in s.blocs]


def test_lire_pages():
    assert lire_pages("15-17, 29", 100) == [15, 16, 17, 29]
    assert lire_pages("", 3) == [1, 2, 3]
    assert lire_pages("2-5", 3) == [2, 3]


def test_bible_etude_versets_et_sections(tmp_path: Path):
    pdf = tmp_path / "essai.pdf"
    pdf_bible_etude(pdf)
    livre, analyses = importer_pdf(pdf, "bible_etude")
    assert [s.titre for s in livre.sections] == ["Le jardin des essais", "Le second atelier"]
    versets = [(b.ch, b.v) for b in _blocs(livre) if b.genre == "verset"]
    assert versets == [(1, 1), (1, 2), (1, 3), (1, 4), (1, 5)]
    texte = {(b.ch, b.v): b.texte for b in _blocs(livre) if b.genre == "verset"}
    assert texte[(1, 1)].startswith("Au commencement")
    assert "1.2" not in texte[(1, 2)]  # renvoi de marge ignoré
    assert "Il est magnifique" in texte[(1, 3)]  # « II » corrigé
    assert "recommença" in texte[(1, 3)]  # mot coupé recollé
    assert texte[(1, 4)].startswith("Il fit")  # « *11 » corrigé
    assert "Gn" not in " ".join(texte.values())  # onglet ignoré
    assert "14" not in texte[(1, 1)]  # numéro de page ignoré
    assert analyses and analyses[0].zones


def test_bible_etude_notes(tmp_path: Path):
    pdf = tmp_path / "essai.pdf"
    pdf_bible_etude(pdf)
    livre, _ = importer_pdf(pdf, "bible_etude")
    notes = [b for b in _blocs(livre) if b.piste == "notes"]
    refs = [b.ref for b in notes]
    assert refs == ["1.1", "1.2", "1.3-4", "1.5"]
    n13 = next(b for b in notes if b.ref == "1.3-4")
    assert (n13.ch, n13.v) == (1, 4)  # ancrée après le dernier verset de l'intervalle
    assert "colonne de droite" in n13.texte  # la colonne de droite suit la gauche
    trad = next(b for b in notes if b.genre == "note_trad")
    assert trad.texte.startswith("Dur:")


def test_mode_mixte_insere_les_notes_apres_leur_verset(tmp_path: Path):
    pdf = tmp_path / "essai.pdf"
    pdf_bible_etude(pdf)
    livre, _ = importer_pdf(pdf, "bible_etude")
    lecture = liste_de_lecture(livre.sections[0], "mixte")
    sequence = [(b.genre, b.ref or f"{b.ch}.{b.v}") for b in lecture]
    i_v1 = sequence.index(("verset", "1.1"))
    assert sequence[i_v1 + 1] == ("note", "1.1")
    i_v4 = sequence.index(("verset", "1.4"))
    assert sequence[i_v4 + 1] == ("note", "1.3-4")
    assert all(b.piste == "texte" for b in liste_de_lecture(livre.sections[0], "texte"))
    assert all(b.piste == "notes" for b in liste_de_lecture(livre.sections[0], "notes"))


def test_enregistrer_et_rouvrir(tmp_path: Path):
    pdf = tmp_path / "essai.pdf"
    pdf_bible_etude(pdf)
    livre, _ = importer_pdf(pdf, "bible_etude", livre_id="essai")
    chemin = tmp_path / "livre.json"
    livre.enregistrer(chemin)
    relu = Livre.ouvrir(chemin)
    assert relu == livre


def test_deux_colonnes_gauche_puis_droite(tmp_path: Path):
    pdf = tmp_path / "commentaire.pdf"
    pdf_deux_colonnes(pdf)
    livre, _ = importer_pdf(pdf, "deux_colonnes")
    texte = " ".join(b.texte for b in _blocs(livre))
    assert texte.index("colonne de gauche") < texte.index("colonne de droite")
    assert "Commentaire inventé" not in texte  # en-tête ignoré
    assert livre.sections[0].titre == "Premier chapitre"
