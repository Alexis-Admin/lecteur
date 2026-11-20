"""Raccroche le minutage des mots prononcés au texte AFFICHÉ.

La voix lit « Genèse, chapitre 4, verset 7 » ; l'écran montre « Gn 4.7 ». Chaque mot prononcé reçoit
la zone du texte affiché qu'il faut surligner (a, b = positions de caractères), ou -1 s'il n'y en a pas
(annonce « Chapitre 5, versets 1 et suivants » d'une note, ajoutée seulement à l'oral).
"""
from __future__ import annotations

import difflib
import re
import unicodedata

_RE_MOT = re.compile(r"[\w’'\-]+", re.UNICODE)


def _norm(m: str) -> str:
    m = unicodedata.normalize("NFD", m.lower().replace("’", "'"))
    return "".join(c for c in m if unicodedata.category(c) != "Mn").strip("'-")


def jetons(texte: str) -> list[tuple[str, int, int]]:
    """Mots d'un texte avec leurs positions : [(mot normalisé, début, fin)]."""
    return [(_norm(m.group(0)), m.start(), m.end()) for m in _RE_MOT.finditer(texte) if _norm(m.group(0))]


def aligner(affiche: str, lu: str, mots_voix: list[tuple[float, float, str]]) -> list[dict]:
    """Retourne [{"d": début_s, "f": fin_s, "a": début_car, "b": fin_car}] dans l'ordre de lecture."""
    j_lu = jetons(lu)
    j_aff = jetons(affiche)

    # 1. Chaque mot de la voix -> un jeton du texte lu (dans l'ordre ; la voix peut regrouper « d'Adam »).
    indices_lu: list[int | None] = []
    k = 0
    for _, _, t in mots_voix:
        cible = _norm(t)
        trouve = None
        for i in range(k, min(k + 6, len(j_lu))):
            if j_lu[i][0] == cible or (cible and (j_lu[i][0].startswith(cible) or cible.startswith(j_lu[i][0]))):
                trouve = i
                break
        indices_lu.append(trouve)
        if trouve is not None:
            k = trouve + 1

    # 2. Texte lu -> texte affiché (les morceaux remplacés, comme une référence, couvrent toute la zone).
    vers_aff: dict[int, tuple[int, int]] = {}
    sm = difflib.SequenceMatcher(a=[j[0] for j in j_lu], b=[j[0] for j in j_aff], autojunk=False)
    for op, i1, i2, k1, k2 in sm.get_opcodes():
        if op == "equal":
            for d in range(i2 - i1):
                vers_aff[i1 + d] = (j_aff[k1 + d][1], j_aff[k1 + d][2])
        elif op == "replace":
            zone = (j_aff[k1][1], j_aff[k2 - 1][2])
            for i in range(i1, i2):
                vers_aff[i] = zone
        # « insert » (seulement à l'oral) et « delete » (seulement à l'écran) : rien à surligner.

    res = []
    for (debut, duree, _), i in zip(mots_voix, indices_lu):
        a, b = vers_aff.get(i, (-1, -1)) if i is not None else (-1, -1)
        res.append({"d": round(debut, 3), "f": round(debut + duree, 3), "a": a, "b": b})
    return res
