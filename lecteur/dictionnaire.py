"""Dictionnaire français (hors ligne) pour recoller les mots coupés et repérer les mots douteux."""
from __future__ import annotations

import re
from functools import lru_cache

_RE_ELISION = re.compile(r"^(?:[ldjmntsc]|qu|jusqu|lorsqu|puisqu|quoiqu)['’]", re.I)


@lru_cache(maxsize=1)
def _verif():
    from spellchecker import SpellChecker

    return SpellChecker(language="fr", distance=1)


def connu(mot: str, ignores: frozenset[str] | set[str] = frozenset()) -> bool:
    """Vrai si le mot existe en français (ou s'il est dans la liste des mots acceptés)."""
    m = mot.strip(".,;:!?«»()[]\"'’…").lower()
    if not m:
        return True
    if m in ignores:
        return True
    m = _RE_ELISION.sub("", m)
    if not m or m.isdigit():
        return True
    if "-" in m:
        return all(connu(p, ignores) for p in m.split("-") if p)
    return m in _verif()


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
