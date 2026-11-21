"""1.0.1 : enchaînement des blocs, changements sûrs de la révision, ordre des encadrés, titres des romans."""
import array
from collections import Counter

from lecteur.assemblage import PAUSE_CHANGEMENT, PAUSE_FIN, PAUSE_PHRASE, PAUSE_SUITE, TAUX, bornes_parole, pause_apres
from lecteur.douteux import propositions
from lecteur.modele import Bloc, Section, liste_de_lecture
from lecteur.pdf_mots import Mot
from lecteur.profils.generique import lignes_de_mots


def test_pause_selon_la_ponctuation():
    v1 = Bloc("b1", "texte", "verset", "Il leur dit", 1, 1)
    v2 = Bloc("b2", "texte", "verset", "de partir.", 1, 2)
    note = Bloc("b3", "notes", "note", "Une note.", 1, 2)
    assert pause_apres(v1, v2) == PAUSE_SUITE        # la phrase continue : presque pas de pause
    assert pause_apres(v2, v1) == PAUSE_PHRASE       # fin de phrase
    assert pause_apres(v2, note) == PAUSE_CHANGEMENT  # on passe à une note
    assert pause_apres(v2, None) == PAUSE_FIN


def test_bornes_de_la_parole():
    silence, son = [0] * (TAUX // 2), [3000, -3000] * (TAUX // 2)
    pcm = array.array("h", silence + son + silence * 2).tobytes()
    d, f = bornes_parole(pcm)
    assert abs(d / TAUX - 0.46) < 0.02   # 0,5 s de silence coupé, moins la marge de 0,04 s
    assert abs(f / TAUX - 1.62) < 0.02   # 1 s de son + marge de 0,12 s


def test_encadres_a_la_fin_de_la_section():
    s = Section("s1", "Essai", blocs=[
        Bloc("v1", "texte", "verset", "Un.", 1, 1),
        Bloc("e", "notes", "encadre", "Étude de personnage.", 1, 1),
        Bloc("n", "notes", "note", "Note.", 1, 1),
        Bloc("v2", "texte", "verset", "Deux.", 1, 2),
    ])
    assert [b.id for b in liste_de_lecture(s, "mixte")] == ["v1", "n", "v2", "e"]


def test_changements_surs():
    noms = Counter({"Hénoc": 4})
    assert propositions("Etreint", "inconnu (début de phrase)", noms, set()) == (["Étreint"], True)
    assert propositions("ouand", "mot inconnu du dictionnaire", noms, set()) == (["quand"], True)
    props, sur = propositions("D'Hénocà", "inconnu (début de phrase)", noms, set())
    assert props[0] == "D'Hénoc à" and sur
    # Un vrai mot rare n'est jamais « sûr » : pas de panetier → papetier coché d'office.
    assert propositions("panetier", "mot inconnu du dictionnaire", noms, set())[1] is False


def _ligne(y, texte, taille=10.0, gras=False):
    mots, x = [], 50.0
    for t in texte.split():
        mots.append(Mot(t, x, y, x + 6 * len(t), y + taille, y + taille * 0.8, taille, False, gras, False, 1))
        x += 6 * len(t) + 4
    return mots


def test_ligne_grossie_par_le_scan_pas_un_titre():
    mots = (_ligne(100, "BRIDGET", 16, True)
            + _ligne(140, "Les convives les plus proches sont assis à trois tables de nous.")
            + _ligne(152, "- Fais-moi confiance. Je sais. Et puis même, il n'y a rien", 12, True)
            + _ligne(164, "de mal à baiser. Je ris, mais je cesse d'essayer de la faire."))
    lignes, _, _ = lignes_de_mots(mots, 600, 800, 1, 1)
    assert [l["texte"] for l in lignes if l["titre"]] == ["BRIDGET"]
