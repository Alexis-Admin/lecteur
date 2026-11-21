"""Repère les mots douteux (probables erreurs d'OCR) pour l'aperçu."""
from __future__ import annotations

import difflib
import re
import unicodedata
from collections import Counter, defaultdict

from .dictionnaire import ABREVIATIONS, connu, sans_elision, suggestions
from .modele import Livre

_RE_MOT = re.compile(r"[\wÀ-ÿœŒæ’'\-]+")
_RE_REF = re.compile(r"^\d{1,3}(\.\d{1,3})?[a-c]?(-\d{1,3}[a-c]?)?$")  # 16.3, 4b-9a
_RE_LIVRE_NUM = re.compile(r"^[123][A-ZÉ][a-zé]{0,3}$")  # 1Jn, 2R, 1Co
_RE_AUTRE_ALPHABET = re.compile(r"[Ͱ-Ͽἀ-῿֐-׿؀-ۿ܀-ݏЀ-ӿ]|[̀-ͯ]")
_RE_DEBUT_PHRASE = re.compile(r"(^|[.!?:«—–]\s*|\(\s*)$")


def raison(mot: str, ignores: set[str], debut_phrase: bool = False, noms: set[str] | None = None) -> str | None:
    """Pourquoi ce mot est douteux, ou None s'il semble correct."""
    m = mot.strip("’'-")
    if not m or _RE_REF.match(m) or m.isdigit() or _RE_LIVRE_NUM.match(m):
        return None
    if _RE_AUTRE_ALPHABET.search(m):
        return None  # grec, hébreu, syriaque… : pas une erreur de lecture
    if m.lower() in ignores:
        return None
    if re.search(r"\d", m) and re.search(r"[A-Za-zÀ-ÿ]", m):
        # « 1x3 », « Jl3 » : mélange de chiffres et de lettres (sauf 1er, 2e, 3°…)
        if not re.fullmatch(r"\d+(er|re|e|ème|es|°|ss|s|[abc])", m):
            return "chiffres et lettres mélangés"
        return None
    coeur = sans_elision(m.replace("’", "'"))
    if not coeur or coeur.lower() in ABREVIATIONS:
        return None
    # « McKeown », « MacArthur », « DeVries » : majuscule au milieu, mais un vrai nom.
    nom_compose = re.match(r"^(Mc|Mac|De|Di|Da|Du|La|Le|Van|Von|O['’])[A-ZÀ-Ü][a-zà-ÿ]", coeur)
    if len(coeur) > 2 and re.search(r"[a-zà-ÿ][A-ZÀ-Ü]", coeur) and not coeur.isupper() and not nom_compose:
        return "majuscule au milieu du mot"
    if coeur[:1].isupper():
        # Nom propre probable. En début de phrase, on vérifie quand même s'il n'apparaît jamais ailleurs.
        if debut_phrase and noms is not None and coeur not in noms and len(coeur) > 2 and not connu(coeur, ignores):
            return "inconnu (début de phrase)"
        return None
    if len(coeur) <= 2:
        return None
    if not connu(m, ignores):
        return "mot inconnu du dictionnaire"
    return None


def _noms_propres(livre: Livre) -> Counter:
    """Mots à majuscule rencontrés au milieu d'une phrase : ce sont des noms (Abram, Kénan…), avec leur nombre."""
    noms: Counter = Counter()
    for s in livre.sections:
        for b in s.blocs:
            for m in _RE_MOT.finditer(b.texte):
                coeur = sans_elision(m.group(0).replace("’", "'"))
                if coeur[:1].isupper() and not _RE_DEBUT_PHRASE.search(b.texte[: m.start()]):
                    noms[coeur] += 1
    return noms


def _sans_accents(mot: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", mot) if not unicodedata.combining(c)).lower()


def propositions(mot: str, raison_: str, noms: Counter, ignores: set[str]) -> tuple[list[str], bool]:
    """Corrections proposées pour un mot douteux, et si la première est sûre (cochée d'office).

    Sûre = seulement un accent qui manque (« Etreint » → « Étreint »), un « à » collé (« Hénocà » → « Hénoc à »),
    ou une seule lettre de différence avec un mot fréquent bien plus probable que les autres (« ouand » → « quand »).
    """
    if not raison_.startswith(("mot inconnu", "inconnu")):
        return [], False
    m = mot.replace("’", "'")
    coeur = sans_elision(m)
    prefixe = m[: len(m) - len(coeur)]  # « D' », « l' »… à remettre devant la proposition
    props: list[str] = []
    sur = False
    # 1. « à » collé au mot précédent (« Hénocà Noé ») : erreur fréquente des scans.
    colle = re.match(r"^(.{2,}?)(à)$", coeur)
    if colle and (connu(colle.group(1), ignores) or colle.group(1) in noms):
        props.append(f"{colle.group(1)} à")
        sur = True
    # 2. Noms du livre qui ressemblent (« Metüshélah » → « Methushélah »).
    if coeur[:1].isupper():
        proches = difflib.get_close_matches(coeur, [n for n in noms if n != coeur], n=2, cutoff=0.8)
        props.extend(proches)
    # 3. Dictionnaire.
    dico = suggestions(coeur)
    for p in dico:
        if p not in props:
            props.append(p)
    if props and not sur:
        p = props[0]
        # Seulement des accents (« Etreint » → « Étreint »), ou une confusion typique d'un scan (« ouand » → « quand »).
        sur = _sans_accents(p) == _sans_accents(coeur) or (len(coeur) >= 4 and _confusion_ocr(coeur, p))
    return [prefixe + p for p in props[:3]], sur


# Lettres que la reconnaissance de texte confond souvent sur un scan.
_CONFUSIONS = {frozenset(p) for p in ("oq", "ce", "li", "l1", "nu", "hb", "ft", "o0", "Il", "rn", "ao")}
_CONFUSIONS_MULTI = (("rn", "m"), ("cl", "d"), ("ii", "ü"), ("li", "h"), ("vv", "w"), ("in", "m"))


def _confusion_ocr(lu: str, propose: str) -> bool:
    """Vrai si « propose » ne diffère de « lu » que par UNE confusion typique d'un scan."""
    a, b = lu.lower(), propose.lower()
    if len(a) == len(b):
        diff = [(x, y) for x, y in zip(a, b) if x != y]
        return len(diff) == 1 and frozenset(diff[0]) in _CONFUSIONS
    for x, y in _CONFUSIONS_MULTI:
        for s, t in ((x, y), (y, x)):
            i = a.find(s)
            while i >= 0:
                if a[:i] + t + a[i + len(s):] == b:
                    return True
                i = a.find(s, i + 1)
    return False


def analyser(livre: Livre, ignores: set[str], max_mots: int = 400, sans_ocr: bool = False) -> list[dict]:
    """Liste des mots douteux du livre, regroupés par mot (un mot corrigé = corrigé partout).

    sans_ocr : texte qui ne vient pas d'une reconnaissance de texte (page web) → seulement les vrais
    accidents (chiffres et lettres mélangés, majuscule au milieu), pas les mots absents du dictionnaire.
    """
    noms = _noms_propres(livre)
    trouves: dict[str, dict] = {}
    occurrences: dict[str, list] = defaultdict(list)
    for s in livre.sections:
        for b in s.blocs:
            for m in _RE_MOT.finditer(b.texte):
                mot = m.group(0).rstrip("-")
                debut = bool(_RE_DEBUT_PHRASE.search(b.texte[: m.start()]))
                if mot not in trouves:
                    r = raison(mot, ignores, debut, noms)
                    if not r or (sans_ocr and "inconnu" in r):
                        continue
                if mot in trouves or r:
                    if mot not in trouves:
                        trouves[mot] = {"mot": mot, "raison": r}
                    if len(occurrences[mot]) < 5:
                        a, z = max(0, m.start() - 40), min(len(b.texte), m.end() + 40)
                        occurrences[mot].append({
                            "bloc": b.id, "section": s.id, "page": b.page, "piste": b.piste,
                            "avant": ("…" if a else "") + b.texte[a:m.start()],
                            "apres": b.texte[m.start() + len(mot):z] + ("…" if z < len(b.texte) else ""),
                        })
                    trouves[mot]["nb"] = trouves[mot].get("nb", 0) + 1
    res = []
    for mot, info in list(trouves.items())[:max_mots]:
        info["exemples"] = occurrences[mot]
        info["suggestions"], info["sur"] = propositions(mot, info["raison"], noms, ignores)
        res.append(info)
    return res


def remplacer_plusieurs(livre: Livre, paires: list[tuple[str, str]]) -> int:
    """Applique plusieurs remplacements d'un coup (changements sûrs cochés)."""
    return sum(remplacer_partout(livre, a, b) for a, b in paires if a and b and a != b)


def remplacer_partout(livre: Livre, avant: str, apres: str) -> int:
    """Remplace un mot exact dans tout le livre. Retourne le nombre de remplacements."""
    motif = re.compile(rf"(?<![\wÀ-ÿ]){re.escape(avant)}(?![\wÀ-ÿ])")
    total = 0
    for s in livre.sections:
        for b in s.blocs:
            nouveau, n = motif.subn(apres, b.texte)
            if n:
                b.texte = nouveau
                total += n
    for s in livre.sections:
        titres = [b for b in s.blocs if b.genre == "titre"]
        if titres:
            s.titre = titres[0].texte
    return total
