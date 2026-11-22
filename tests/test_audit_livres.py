"""1.1.0 : audit sur des livres variés (romans, essais, Bible avec encadrés, livres anglais).

Tests avec des pages inventées : en-têtes répétés, paragraphes coupés par la page, encadrés sur le côté,
numéros de chapitre, mots coupés sans trait d'union, langue.
"""
from lecteur.modele import Bloc, Livre, Section
from lecteur.nettoyage import corriger_texte, recoller_coupures
from lecteur.pdf_mots import Mot
from lecteur.profils.generique import (_colonnes_auto, construire_depuis, detecter_langue,
                                       fusionner_petites_sections)


def _ligne(y, texte, x=60.0, taille=10.0, gras=False, page=1):
    mots = []
    for t in texte.split():
        mots.append(Mot(t, x, y, x + 5.5 * len(t), y + taille, y + taille * 0.8, taille, False, gras, False, page))
        x += 5.5 * len(t) + 4
    return mots


PHRASE = "Elle marche dans la rue et regarde les vitrines des magasins avant de rentrer chez elle le soir"


def _page(p, debut=""):
    mots = _ligne(30, "TWISTED GAMES", x=200, page=p)  # en-tête répété
    y = 120
    if debut:
        mots += _ligne(y, debut, page=p)
        y += 12
    for _ in range(20):
        mots += _ligne(y, PHRASE, page=p)
        y += 12
    mots += _ligne(y, "et puis elle", page=p)  # le paragraphe continue sur la page suivante
    return mots


def test_entetes_repetes_et_paragraphes_recolles():
    pages = {1: _page(1), 2: _page(2, "continue sa route."), 3: _page(3, "dort enfin.")}
    livre, _ = construire_depuis(lambda p: (pages[p], 600, 800, True), [1, 2, 3], 1, "simple")
    textes = [b.texte for s in livre.sections for b in s.blocs]
    assert not any("TWISTED" in t for t in textes)  # l'en-tête n'est ni un titre ni du texte
    assert not any(t[:1].islower() for t in textes)  # aucun paragraphe ne commence au milieu d'une phrase
    assert any("et puis elle continue sa route." in t for t in textes)


def test_encadre_sur_le_cote():
    mots = []
    for i in range(30):
        mots += _ligne(100 + 12 * i, "Texte principal de la Bible qui continue encore", x=300)
    for i in range(12):
        mots += _ligne(100 + 12 * i, "Encadré étroit ici", x=40)
    colonnes = _colonnes_auto(mots, 600)
    assert [enc for _, enc in colonnes] == [False, True]  # texte d'abord, encadré à part


def test_numero_de_chapitre():
    mots = _ligne(80, "2", x=290, taille=30) + _ligne(130, "RHYS", x=270, taille=24, gras=True)
    for i in range(20):
        mots += _ligne(180 + 12 * i, PHRASE)
    livre, _ = construire_depuis(lambda p: (mots, 600, 800, True), [1], 1, "simple")
    assert livre.sections[0].titre == "Chapitre 2 · Rhys"


def test_mots_coupes_et_nombres_colles():
    assert recoller_coupures("Dieu maî trisait la situation") == "Dieu maîtrisait la situation"
    assert recoller_coupures("de faire la paix") == "de faire la paix"  # deux vrais mots : on ne touche pas
    assert corriger_texte("une décennie2 plus tard") == "une décennie plus tard"
    assert corriger_texte("il a 3ans et le 1er") == "il a 3 ans et le 1er"


def test_langue():
    assert detecter_langue(["This is the book that you will read with your family and the world."] * 5) == "en"
    assert detecter_langue(["Le livre est dans la maison et il ne veut pas le lire pour les enfants."] * 5) == "fr"


def test_petites_sections_reunies():
    livre = Livre("x", "x", "bible_etude", "", [])
    livre.sections = [
        Section("s1", "La certitude du jugement divin", blocs=[Bloc("t1", "texte", "titre", "La certitude du jugement divin")]),
        Section("s2", "Au chef de chœur.", blocs=[Bloc("t2", "texte", "titre", "Au chef de chœur.")]),
        Section("s3", "De David.", blocs=[Bloc("t3", "texte", "titre", "De David."), Bloc("v", "texte", "verset", "Éternel.", 7, 1)]),
    ]
    fusionner_petites_sections(livre)
    assert [s.titre for s in livre.sections] == ["La certitude du jugement divin"]
    assert len(livre.sections[0].blocs) == 4
