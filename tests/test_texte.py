from lecteur.nettoyage import assembler, corriger_texte, nettoyer_mot
from lecteur.prononciation import a_lire, etiquette_a_lire
from lecteur.references import analyser_etiquette, corriger_references, lire_references


def test_references_au_long():
    assert lire_references("Ge 2.4a") == "Genèse, chapitre 2, verset 4 a"
    assert lire_references("Ac 7.22") == "Actes, chapitre 7, verset 22"
    assert lire_references("Ps 150.3-5") == "Psaume 150, versets 3 à 5"
    assert lire_references("Rm 4.3,9,22") == "Romains, chapitre 4, versets 3, 9 et 22"
    assert lire_references("Jd 11") == "Jude, verset 11"
    assert lire_references("1Co 15.49") == "premier Corinthiens, chapitre 15, verset 49"
    assert lire_references("Gn 6.1-8.22") == "Genèse, chapitre 6, verset 1, à chapitre 8, verset 22"
    assert lire_references("Gn 4.25; 5.3") == "Genèse, chapitre 4, verset 25 ; chapitre 5, verset 3"
    assert lire_references("Gn 9.20ss") == "Genèse, chapitre 9, versets 20 et suivants"


def test_mots_courants_ne_sont_pas_des_livres():
    assert lire_references("La 3e fois") == "La 3e fois"
    assert lire_references("Je 2 fois") == "Je 2 fois"


def test_references_nues():
    assert a_lire("(cf. 4.17)", refs_nues=True) == "(voir chapitre 4, verset 17)"
    assert a_lire("(cf. 4.17)", refs_nues=False) == "(voir 4.17)"


def test_corrections_ocr_des_references():
    assert corriger_references("ICh 1.2") == "1Ch 1.2"
    assert corriger_references("Le 3.37") == "Lc 3.37"
    assert corriger_references("Gn3.17") == "Gn 3.17"
    assert corriger_references("AC2.21") == "Ac 2.21"
    assert corriger_references("Un 3.12") == "1Jn 3.12"
    assert corriger_references("1S 15:29") == "1S 15.29"
    assert corriger_references("Le chien") == "Le chien"


def test_abreviations():
    assert a_lire("p. ex. un vase") == "par exemple un vase"
    assert a_lire("vers 1000 av. J.-C.") == "vers 1000 avant Jésus-Christ"
    assert a_lire("1° la foi; 2° les œuvres") == "premièrement la foi; deuxièmement les œuvres"
    assert a_lire("Nod: litt. errer") == "Nod: littéralement errer"


def test_etiquettes_de_notes():
    assert analyser_etiquette("4.19-26 Livrés") == ("4.19-26", 4, 19, 4, 26)
    assert analyser_etiquette("5.1ss La Bible") == ("5.1ss", 5, 1, 5, 1)
    assert analyser_etiquette("Le chien") is None
    assert etiquette_a_lire("5.1ss") == "Chapitre 5, versets 1 et suivants"
    assert etiquette_a_lire("16.3") == "Chapitre 16, verset 3"


def test_nettoyer_mot():
    assert nettoyer_mot("*11") == "Il"
    assert nettoyer_mot("II") == "Il"
    assert nettoyer_mot("*il") == "il"
    assert nettoyer_mot("■") == ""
    assert nettoyer_mot('Nod"') == "Nod"
    assert nettoyer_mot("/'Eternel") == "l'Eternel"
    assert nettoyer_mot("11") == "11"  # un vrai nombre reste un nombre


def test_mots_coupes():
    assert assembler(["il les commence-", "ments du monde"]) == "il les commencements du monde"
    assert assembler(["prê­", "tez attention"]) == "prêtez attention"
    assert assembler(["souvenons-", "nous de lui"]) == "souvenons-nous de lui"
    assert corriger_texte("les commence- ments") == "les commencements"


def test_corrections_apprises():
    j = []
    assert corriger_texte("Vielle sera ta descendance", j, {"Vielle": "Telle"}) == "Telle sera ta descendance"
    assert ("Vielle", "Telle") in j
