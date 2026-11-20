"""Références bibliques : reconnaissance, correction des erreurs d'OCR et lecture au long.

Exemples :
    « Ge 2.4a »          -> « Genèse, chapitre 2, verset 4 a »
    « Ps 150.3-5 »       -> « Psaume 150, versets 3 à 5 »
    « Rm 4.3,9,22 »      -> « Romains, chapitre 4, versets 3, 9 et 22 »
    « Jd 11 »            -> « Jude, verset 11 »
    « (cf. 4.17) »       -> « (voir chapitre 4, verset 17) »  (références « nues », profil Bible)
"""
from __future__ import annotations

import re

# (nom lu, abréviations, livre à un seul chapitre)
LIVRES: list[tuple[str, list[str], bool]] = [
    ("Genèse", ["Gn", "Ge", "Gen"], False),
    ("Exode", ["Ex"], False),
    ("Lévitique", ["Lv", "Lé"], False),
    ("Nombres", ["Nb", "No"], False),
    ("Deutéronome", ["Dt", "De"], False),
    ("Josué", ["Jos"], False),
    ("Juges", ["Jg"], False),
    ("Ruth", ["Rt", "Ru"], False),
    ("premier Samuel", ["1S", "1Sa", "1 S", "1 Sa"], False),
    ("deuxième Samuel", ["2S", "2Sa", "2 S", "2 Sa"], False),
    ("premier Rois", ["1R", "1Ro", "1 R", "1 Ro"], False),
    ("deuxième Rois", ["2R", "2Ro", "2 R", "2 Ro"], False),
    ("premier Chroniques", ["1Ch", "1 Ch"], False),
    ("deuxième Chroniques", ["2Ch", "2 Ch"], False),
    ("Esdras", ["Esd"], False),
    ("Néhémie", ["Né", "Ne"], False),
    ("Esther", ["Est"], False),
    ("Job", ["Jb"], False),
    ("Psaume", ["Ps"], False),
    ("Proverbes", ["Pr"], False),
    ("Ecclésiaste", ["Ec"], False),
    ("Cantique des cantiques", ["Ct"], False),
    ("Ésaïe", ["Es", "És"], False),
    ("Jérémie", ["Jr"], False),
    ("Lamentations", ["Lm", "La"], False),
    ("Ézéchiel", ["Ez", "Éz"], False),
    ("Daniel", ["Dn", "Da"], False),
    ("Osée", ["Os"], False),
    ("Joël", ["Jl", "Joë"], False),
    ("Amos", ["Am"], False),
    ("Abdias", ["Ab"], True),
    ("Jonas", ["Jon"], False),
    ("Michée", ["Mi"], False),
    ("Nahoum", ["Na"], False),
    ("Habakuk", ["Ha"], False),
    ("Sophonie", ["So"], False),
    ("Aggée", ["Ag"], False),
    ("Zacharie", ["Za"], False),
    ("Malachie", ["Ml"], False),
    ("Matthieu", ["Mt"], False),
    ("Marc", ["Mc"], False),
    ("Luc", ["Lc"], False),
    ("Jean", ["Jn"], False),
    ("Actes", ["Ac"], False),
    ("Romains", ["Rm", "Ro"], False),
    ("premier Corinthiens", ["1Co", "1 Co"], False),
    ("deuxième Corinthiens", ["2Co", "2 Co"], False),
    ("Galates", ["Ga"], False),
    ("Éphésiens", ["Ep", "Ép"], False),
    ("Philippiens", ["Ph"], False),
    ("Colossiens", ["Col"], False),
    ("premier Thessaloniciens", ["1Th", "1 Th"], False),
    ("deuxième Thessaloniciens", ["2Th", "2 Th"], False),
    ("premier Timothée", ["1Tm", "1Ti", "1 Tm", "1 Ti"], False),
    ("deuxième Timothée", ["2Tm", "2Ti", "2 Tm", "2 Ti"], False),
    ("Tite", ["Tt", "Tit"], False),
    ("Philémon", ["Phm"], True),
    ("Hébreux", ["Hé", "He"], False),
    ("Jacques", ["Jc", "Je"], False),
    ("premier Pierre", ["1P", "1Pi", "1 P", "1 Pi"], False),
    ("deuxième Pierre", ["2P", "2Pi", "2 P", "2 Pi"], False),
    ("premier Jean", ["1Jn", "1 Jn"], False),
    ("deuxième Jean", ["2Jn", "2 Jn"], True),
    ("troisième Jean", ["3Jn", "3 Jn"], True),
    ("Jude", ["Jd"], True),
    ("Apocalypse", ["Ap"], False),
]

# Noms affichés dans les en-têtes de page (« GENÈSE ») -> abréviation principale
_ABR: dict[str, tuple[str, bool]] = {}
for _nom, _abrs, _unique in LIVRES:
    for _a in _abrs:
        _ABR[_a.replace(" ", "")] = (_nom, _unique)

_alternatives = sorted({a for _, abrs, _ in LIVRES for a in abrs}, key=len, reverse=True)
_motif_livre = "|".join(re.escape(a).replace(r"\ ", r"\s?") for a in _alternatives)
# Un livre suivi d'un chiffre (pas précédé d'une lettre, pour ne pas couper un mot).
RE_LIVRE = re.compile(rf"(?<![\w])({_motif_livre})\.?\s?(?=\d)")

_ORDINAUX_LETTRE = {"a": "a", "b": "b", "c": "c"}


def abreviation_de(nom_livre: str) -> str | None:
    """« Genèse » ou « GENÈSE » -> « Gn »."""
    cible = nom_livre.strip().lower()
    for nom, abrs, _ in LIVRES:
        if nom.lower() == cible:
            return abrs[0]
    return None


def nom_affiche(nom_entete: str) -> str:
    """« GENÈSE » -> « Genèse » (avec le nom officiel si on le reconnaît)."""
    cible = nom_entete.strip().lower()
    for nom, _, _ in LIVRES:
        if nom.lower() == cible:
            return nom[0].upper() + nom[1:]
    return nom_entete.strip().capitalize()


# ---------------------------------------------------------------------------
# Correction des erreurs d'OCR dans les références
# ---------------------------------------------------------------------------
_RE_I_NUMERO = re.compile(r"(?<![\w])[Il|](Ch|R|S|Co|Th|Tm|P|Jn|Sa|Ro|Ti|Pi)(?=\s?\d)")
_RE_COLLE = re.compile(rf"(?<![\w])({_motif_livre})(\d)", re.I)
_RE_L_POUR_1 = re.compile(rf"(?<![\w])({_motif_livre})l(?=[.\d])")


def corriger_references(texte: str, journal: list | None = None) -> str:
    """Corrige les erreurs d'OCR fréquentes dans les références (« ICh 1.2 », « Le 3.37 », « Gn3.17 »)."""

    def note(avant: str, apres: str) -> None:
        if journal is not None and avant != apres:
            journal.append((avant, apres))

    def r_i(m: re.Match) -> str:
        res = "1" + m.group(1)
        note(m.group(0), res)
        return res

    texte = _RE_I_NUMERO.sub(r_i, texte)

    # « Un 3.12 » : « 1Jn » mal lu ; « 1S 15:29 » : deux-points au lieu du point.
    def r_un(m: re.Match) -> str:
        note(m.group(0), "1Jn ")
        return "1Jn "

    texte = re.sub(r"(?<![\w])Un\s?(?=\d{1,3}\.\d)", r_un, texte)
    texte = re.sub(rf"(?<![\w])({_motif_livre})(\s?\d{{1,3}}):(\d{{1,3}})", r"\1\2.\3", texte)

    def r_l(m: re.Match) -> str:
        res = m.group(1) + " 1"
        note(m.group(0) + "…", res + "…")
        return res

    texte = _RE_L_POUR_1.sub(r_l, texte)

    # Luc mal lu : « Le 3.37 », « LC 3.37 », « Lc3.37 »
    def r_luc(m: re.Match) -> str:
        res = "Lc " + m.group(1)
        note(m.group(0), res)
        return res

    texte = re.sub(r"(?<![\w])(?:Le|LC|lc)\s?(\d{1,3}\.\d)", r_luc, texte)

    def r_colle(m: re.Match) -> str:
        brut, reste = m.group(1), m.group(2)
        canon = next((a for a in _alternatives if a.replace(" ", "").lower() == re.sub(r"\s", "", brut).lower()), brut)
        res = f"{canon} {reste}"
        note(m.group(0), res)
        return res

    # Seulement quand c'est vraiment une référence : « Gn3.17 », « AC2.21 ».
    texte = re.sub(rf"(?<![\w])({_motif_livre})(\d{{1,3}}\.\d)", r_colle, texte, flags=re.I)
    return texte


# Abréviations qui sont aussi des mots courants : il faut « chapitre.verset » pour y croire.
_AMBIGUS = {"La", "Le", "Je", "No", "Na", "Ha", "Es", "Am", "Ab", "So", "Ne", "De", "Ex", "Ac", "Mi", "Os", "Ro",
            "Ru", "Pr", "Ph", "Est", "Ga", "He", "Lé", "Né", "Da", "Ec", "Col", "Tit", "Ge", "Gen", "Jon", "Ep"}


# ---------------------------------------------------------------------------
# Lecture au long
# ---------------------------------------------------------------------------
_RE_CV = re.compile(r"(\d{1,3})(?:\.(\d{1,3})([abc])?)?")
_RE_INTERVALLE = re.compile(r"\s?[-–]\s?(\d{1,3})(?:\.(\d{1,3}))?([abc])?")
_RE_SUIVANTS = re.compile(r"(ss|s)(?![\w])")
_RE_LISTE = re.compile(r"\s?,\s?(\d{1,3})([abc])?(?![\d.])(?:\s?[-–]\s?(\d{1,3}))?")
_RE_POINT_VIRGULE = re.compile(r"\s?;\s?(?=\d{1,3}\.\d)")


def _v(n: str, lettre: str | None) -> str:
    return f"{n} {lettre}" if lettre else n


def _lire_queue(s: str, i: int, unique: bool, psaume: bool) -> tuple[int, list[str]]:
    """Lit « 4.1-17; 5.3 » à partir de s[i]. Retourne (fin, morceaux lus)."""
    morceaux: list[str] = []
    while True:
        m = _RE_CV.match(s, i)
        if not m:
            break
        ch, vs, lettre = m.group(1), m.group(2), m.group(3)
        if m.end() < len(s) and (s[m.end()].isalpha() and not s.startswith(("ss", "s"), m.end())):
            break  # « 3e fois », « 2nd » : pas une référence
        i = m.end()
        if vs is None and unique:
            # « Jd 11 » : livre d'un seul chapitre -> verset
            ch, vs = "1", ch
        prefixe = (ch if psaume else f"chapitre {ch}") if not unique else ""
        if vs is None:
            morceaux.append(prefixe)
        else:
            versets = [_v(vs, lettre)]
            pluriel = False
            mi = _RE_INTERVALLE.match(s, i)
            ms = _RE_SUIVANTS.match(s, i)
            if mi:
                i = mi.end()
                if mi.group(2):  # autre chapitre : 6.1-8.22
                    txt = f"verset {_v(vs, lettre)}, à chapitre {mi.group(1)}, verset {_v(mi.group(2), mi.group(3))}"
                    morceaux.append(", ".join(x for x in (prefixe, txt) if x))
                    if not (mp := _RE_POINT_VIRGULE.match(s, i)):
                        break
                    i = mp.end()
                    continue
                versets = [f"{_v(vs, lettre)} à {_v(mi.group(1), mi.group(3))}"]
                pluriel = True
            elif ms:
                i = ms.end()
                versets = [f"{_v(vs, lettre)} et suivant" + ("s" if ms.group(1) == "ss" else "")]
                pluriel = True
            while (ml := _RE_LISTE.match(s, i)):
                i = ml.end()
                pluriel = True
                versets.append(f"{_v(ml.group(1), ml.group(2))} à {ml.group(3)}" if ml.group(3) else _v(ml.group(1), ml.group(2)))
            liste = versets[0] if len(versets) == 1 else ", ".join(versets[:-1]) + " et " + versets[-1]
            txt = ("versets " if pluriel else "verset ") + liste
            morceaux.append(", ".join(x for x in (prefixe, txt) if x))
        mp = _RE_POINT_VIRGULE.match(s, i)
        if not mp:
            break
        i = mp.end()
    return i, morceaux


def lire_references(texte: str, refs_nues: bool = False) -> str:
    """Remplace les références par leur lecture au long."""
    sortie: list[str] = []
    i = 0
    while True:
        m = RE_LIVRE.search(texte, i)
        if not m:
            break
        abr = re.sub(r"\s", "", m.group(1))
        nom, unique = _ABR.get(abr, (None, False))
        if nom is not None and abr in _AMBIGUS and not re.match(r"\d{1,3}\.\d", texte[m.end():]):
            nom = None  # « La 3e fois » n'est pas Lamentations 3
        if nom is None:
            sortie.append(texte[i:m.end()])
            i = m.end()
            continue
        fin, morceaux = _lire_queue(texte, m.end(), unique, nom == "Psaume")
        if not morceaux:
            sortie.append(texte[i:m.end()])
            i = m.end()
            continue
        sortie.append(texte[i:m.start()])
        if nom == "Psaume":
            sortie.append(f"Psaume {' ; '.join(morceaux)}")
        else:
            sortie.append(f"{nom}, {' ; '.join(morceaux)}")
        i = fin
    sortie.append(texte[i:])
    res = "".join(sortie)
    if refs_nues:
        res = lire_references_nues(res)
    return res


_RE_NUE = re.compile(r"(?<![\w.,])(\d{1,3}\.\d{1,3}[abc]?(?:\s?[-–]\s?\d{1,3}(?:\.\d{1,3})?[abc]?|ss|s(?![\w]))?)(?![\d\w])")


def lire_references_nues(texte: str) -> str:
    """« (cf. 4.17) » -> « (cf. chapitre 4, verset 17) ». Pour les livres où les décimales s'écrivent avec une virgule."""

    def r(m: re.Match) -> str:
        fin, morceaux = _lire_queue(texte, m.start(), False, False)
        return " ; ".join(morceaux) if morceaux and fin == m.end() else m.group(0)

    # On relit avec _lire_queue pour gérer les listes « 4.3, 9 ».
    sortie, i = [], 0
    for m in _RE_NUE.finditer(texte):
        if m.start() < i:
            continue
        fin, morceaux = _lire_queue(texte, m.start(), False, False)
        if not morceaux:
            continue
        sortie.append(texte[i:m.start()])
        sortie.append(" ; ".join(morceaux))
        i = fin
    sortie.append(texte[i:])
    return "".join(sortie)


_RE_ETIQUETTE = re.compile(r"^(\d{1,3})\.(\d{1,3})([abc])?(?:\s?[-–]\s?(\d{1,3})(?:\.(\d{1,3}))?([abc])?|(ss|s)(?![\w]))?")


def analyser_etiquette(texte: str) -> tuple[str, int, int, int, int] | None:
    """« 4.19-26 Livrés… » -> (« 4.19-26 », ch, v, ch_fin, v_fin). None si ce n'est pas une étiquette de note."""
    m = _RE_ETIQUETTE.match(texte.strip())
    if not m:
        return None
    ch, v = int(m.group(1)), int(m.group(2))
    ch_fin, v_fin = ch, v
    if m.group(4):
        if m.group(5):
            ch_fin, v_fin = int(m.group(4)), int(m.group(5))
        else:
            v_fin = int(m.group(4))
    return m.group(0), ch, v, ch_fin, v_fin


def lire_etiquette(etiquette: str) -> str:
    """« 5.1ss » -> « Chapitre 5, versets 1 et suivants »."""
    _, morceaux = _lire_queue(etiquette, 0, False, False)
    txt = " ; ".join(morceaux)
    return txt[:1].upper() + txt[1:] if txt else etiquette
