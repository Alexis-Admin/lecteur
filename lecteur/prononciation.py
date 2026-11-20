"""Transforme le texte affiché en texte à lire à voix haute.

Le texte affiché garde ses abréviations (« p. ex. », « Gn 4.7 »). La voix reçoit la forme
longue (« par exemple », « Genèse, chapitre 4, verset 7 »).
"""
from __future__ import annotations

import re

from .references import lire_etiquette, lire_references

# (motif, remplacement) — appliqués dans l'ordre.
ABREVIATIONS: list[tuple[str, str]] = [
    (r"\bp\.\s?ex\.", "par exemple"),
    (r"\bav\.\s?J\.?-C\.", "avant Jésus-Christ"),
    (r"\bapr\.\s?J\.?-C\.", "après Jésus-Christ"),
    (r"\bJ\.-C\.", "Jésus-Christ"),
    (r"\bcf\.", "voir"),
    (r"\blitt\.", "littéralement"),
    (r"\bhéb\.", "hébreu"),
    (r"\bgr\.", "grec"),
    (r"\baram\.", "araméen"),
    (r"\benv\.", "environ"),
    (r"\bchap\.\s?(?=\d)", "chapitre "),
    (r"\bch\.\s?(?=\d)", "chapitre "),
    (r"\bvv\.\s?(?=\d)", "versets "),
    (r"\bv\.\s?(?=\d)", "verset "),
    (r"\bs\.\s?(?=\d)", "siècle "),
    (r"\bn°\s?", "numéro "),
    (r"\bvol\.\s?", "volume "),
    (r"\bt\.\s?(?=\d)", "tome "),
    (r"\bAT\b", "Ancien Testament"),
    (r"\bNT\b", "Nouveau Testament"),
    (r"\bLXX\b", "la Septante"),
    (r"\bMgr\b", "Monseigneur"),
    (r"\bM\.\s(?=[A-ZÉ])", "monsieur "),
    (r"\bMme\b", "madame"),
    (r"\betc\.", "et cetera."),
]
_ORDINAUX = {"1": "premièrement", "2": "deuxièmement", "3": "troisièmement", "4": "quatrièmement",
             "5": "cinquièmement", "6": "sixièmement", "7": "septièmement", "8": "huitièmement"}
_RE_ABR = [(re.compile(m), r) for m, r in ABREVIATIONS]


def a_lire(texte: str, refs_nues: bool = False) -> str:
    """Texte affiché -> texte prononcé."""
    t = texte
    for motif, remplacement in _RE_ABR:
        t = motif.sub(remplacement, t)
    t = re.sub(r"(?<!\d)([1-8])°", lambda m: _ORDINAUX[m.group(1)], t)
    t = lire_references(t, refs_nues=refs_nues)
    # Tirets de liste : après une fin de phrase on les enlève, ailleurs ils deviennent une pause.
    t = re.sub(r"([.!?:;»])\s*[-–]\s", r"\1 ", t)
    t = re.sub(r"^\s*[-–]\s*", "", t)
    t = re.sub(r"(\s)[-–]\s", r", ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def bloc_a_lire(bloc, refs_nues: bool = False) -> str:
    """Texte prononcé pour un bloc, avec son annonce (« Chapitre 5, versets 1 et suivants. », « Encadré. »)."""
    corps = a_lire(bloc.texte, refs_nues)
    if bloc.genre == "note" and bloc.ref:
        return f"{etiquette_a_lire(bloc.ref)}. {corps}"
    if bloc.genre == "note_trad":
        return f"Note de traduction{', ' + etiquette_a_lire(bloc.ref).lower() if bloc.ref else ''}. {corps}"
    if bloc.genre == "encadre":
        return f"Encadré. {corps}"
    return corps


def etiquette_a_lire(etiquette: str) -> str:
    """« 5.1ss » -> « Chapitre 5, versets 1 et suivants »."""
    return lire_etiquette(etiquette)
