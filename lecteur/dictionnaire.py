"""Dictionnaire français (hors ligne) pour recoller les mots coupés et repérer les mots douteux."""
from __future__ import annotations

import re
from functools import lru_cache

_RE_ELISION = re.compile(r"^(?:[ldjmntsc]|qu|jusqu|lorsqu|puisqu|quoiqu|presqu)['’]", re.I)
# Abréviations courantes des Bibles d'étude et des commentaires (sans le point).
ABREVIATIONS = {"héb", "litt", "env", "cf", "ex", "av", "apr", "gr", "aram", "chap", "ch", "vv", "etc", "vol", "éd",
                "trad", "var", "lat", "env", "mss", "ms", "sv", "ss", "id", "ibid", "op", "cit", "réf", "voy", "nb"}


@lru_cache(maxsize=1)
def _verif():
    from spellchecker import SpellChecker

    return SpellChecker(language="fr", distance=1)


def sans_elision(mot: str) -> str:
    """« l’Eternel » -> « Eternel », « qu’Abram » -> « Abram »."""
    return _RE_ELISION.sub("", mot)


def _dans_dico(m: str) -> bool:
    d = _verif()
    if m in d:
        return True
    variantes = {m.replace("œ", "oe").replace("æ", "ae"), m.replace("oe", "œ")}
    if any(v in d for v in variantes):
        return True
    # Formes que le dictionnaire n'a pas toujours : pluriels, adverbes en -ment, féminins.
    for fin, rempl in (("s", ""), ("x", ""), ("es", ""), ("ment", ""), ("ement", ""), ("e", ""), ("ée", "é"), ("ées", "é"),
                       ("ait", "er"), ("aient", "er"), ("èrent", "er"), ("ent", "er"), ("ions", "er"), ("iez", "er")):
        if m.endswith(fin) and len(m) - len(fin) >= 3:
            base = m[: len(m) - len(fin)] + rempl
            if base in d or base.replace("œ", "oe") in d:
                return True
    # « pèche » (il pèche) : verbe en -er avec accent grave
    if m.endswith("e") and ("è" in m) and m.replace("è", "é")[:-1] + "er" in d:
        return True
    return False


def connu(mot: str, ignores: frozenset[str] | set[str] = frozenset()) -> bool:
    """Vrai si le mot existe en français (ou s'il est dans la liste des mots acceptés)."""
    m = mot.strip(".,;:!?«»()[]\"'’…-").lower().replace("’", "'")
    if not m:
        return True
    if m in ignores:
        return True
    m = sans_elision(m)
    if not m or m.isdigit() or m in ABREVIATIONS:
        return True
    if "-" in m:
        # « trouve-t-il », « peut-être » : chaque morceau (les petits « t », « y » sont permis)
        return all(len(p) <= 2 or connu(p, ignores) for p in m.split("-") if p)
    if m.replace("'", "") in _verif():  # « aujourd'hui »
        return True
    return _dans_dico(m)


def frequence(mot: str) -> int:
    """Fréquence d'un mot dans le dictionnaire (0 s'il est absent)."""
    return _verif().word_frequency[mot.lower()]


def suggestions(mot: str, maximum: int = 3) -> list[str]:
    m = mot.lower()
    try:
        cands = _verif().candidates(m) or set()
    except Exception:  # noqa: BLE001 - le correcteur peut échouer sur des caractères bizarres
        return []
    freq = _verif().word_frequency
    res = sorted((c for c in cands if c != m), key=lambda c: -freq[c])[:maximum]
    if mot[:1].isupper():
        res = [r[:1].upper() + r[1:] for r in res]
    return res
