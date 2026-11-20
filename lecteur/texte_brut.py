"""Import de texte collé, de pages web et de captures d'écran."""
from __future__ import annotations

import re
from pathlib import Path

from .modele import Livre
from .nettoyage import assembler, corriger_texte
from .profils.generique import assembler_sections, construire_depuis

_FIN_PHRASE = re.compile(r"[.!?»:…)\]\"”]$")
_A_SAUTER = re.compile(r"^(notes?( et références)?|références|bibliographie|liens externes|voir aussi|articles connexes|"
                       r"sources?|annexes|partager|commentaires|à lire aussi|sur le même sujet)\b", re.I)


def _paragraphes(texte: str) -> list[tuple[str, list[str]]]:
    """Découpe en paragraphes. Retourne (genre, lignes) avec genre « titre » ou « paragraphe »."""
    texte = texte.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    lignes = [l.rstrip() for l in texte.split("\n")]
    a_des_blancs = any(not l.strip() for l in lignes)
    blocs: list[list[str]] = []
    courant: list[str] = []
    for i, l in enumerate(lignes):
        s = l.strip()
        if not s:
            if courant:
                blocs.append(courant)
                courant = []
            continue
        if re.match(r"^#{1,6}\s", s):  # titre Markdown (pages web)
            if courant:
                blocs.append(courant)
            blocs.append([s])
            courant = []
            continue
        courant.append(s)
        if not a_des_blancs:
            # Sans lignes vides : une ligne qui finit une phrase termine le paragraphe,
            # sauf si la suivante commence par une minuscule (texte copié d'un PDF).
            suivante = lignes[i + 1].strip() if i + 1 < len(lignes) else ""
            if _FIN_PHRASE.search(s) and not (suivante[:1].islower()):
                blocs.append(courant)
                courant = []
    if courant:
        blocs.append(courant)

    res: list[tuple[str, list[str]]] = []
    for b in blocs:
        premier = b[0]
        # « Deuxième partie » suivi directement du texte : le titre est détaché.
        if len(b) >= 2 and len(premier) <= 60 and not _FIN_PHRASE.search(premier) and premier[-1:] not in ",;-" \
                and b[1][:1].isupper() and not re.match(r"^#{1,6}\s|^([-–*+•]|\d+[.)])\s", premier):
            res.append(("titre", [premier]))
            b = b[1:]
            premier = b[0]
        if re.match(r"^#{1,6}\s", premier):
            res.append(("titre", [re.sub(r"^#{1,6}\s+", "", premier)]))
        elif len(b) == 1 and len(premier) <= 90 and not _FIN_PHRASE.search(premier) and not premier[-1:] in ",;" \
                and not re.match(r"^([-–*+•]|\d+[.)])\s", premier):
            res.append(("titre", b))
        else:
            res.append(("paragraphe", b))
    return res


def _nettoyer_markdown(t: str) -> str:
    t = re.sub(r"<sup>.*?</sup>", "", t)  # appels de note « [92] »
    t = re.sub(r"\\?\[\d{1,3}\\?\]", "", t)
    t = re.sub(r"</?[a-z][^>]*>", "", t)  # autres balises restées
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)  # images
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)  # liens -> texte
    t = re.sub(r"(\*\*|__)(.+?)\1", r"\2", t)
    t = re.sub(r"(?<!\w)[*_](.+?)[*_](?!\w)", r"\1", t)
    t = re.sub(r"^\s*[-*+]\s+", "– ", t)
    t = re.sub(r"^\s*>\s?", "", t)
    return t


def _retirer_sections_inutiles(markdown: str) -> str:
    """Retire « Notes et références », « Bibliographie », « Liens externes »… et leurs sous-sections."""
    garder: list[str] = []
    niveau_saute = 0
    for ligne in markdown.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)$", ligne.strip())
        if m:
            niveau = len(m.group(1))
            if niveau_saute and niveau > niveau_saute:
                continue
            niveau_saute = niveau if _A_SAUTER.match(m.group(2)) else 0
            if niveau_saute:
                continue
        elif niveau_saute:
            continue
        garder.append(ligne)
    return "\n".join(garder)


def livre_depuis_texte(texte: str, titre: str, apprises: dict[str, str] | None = None, livre_id: str = "",
                       profil: str = "texte", markdown: bool = False) -> Livre:
    livre = Livre(livre_id, titre or "Texte", profil, "", [])
    journal: list[tuple[str, str, None]] = []
    paragraphes = []
    if markdown:
        texte = _retirer_sections_inutiles(texte)
    for genre, lignes in _paragraphes(texte):
        if markdown:
            lignes = [_nettoyer_markdown(l) for l in lignes]
        j: list = []
        t = corriger_texte(assembler(lignes, j), j, apprises)
        journal.extend((a, b, None) for a, b in j)
        paragraphes.append((genre, t, None))
    assembler_sections(livre, paragraphes)
    if not livre.sections:
        raise ValueError("Le texte est vide.")
    livre.corrections = [{"avant": a, "apres": b, "page": p} for a, b, p in journal if a != b]
    return livre


def lire_page_web(url: str) -> tuple[str, str]:
    """Télécharge une page web et garde seulement l'article (sans menus ni publicités). Retourne (titre, texte)."""
    import trafilatura

    if not re.match(r"^https?://", url.strip(), re.I):
        url = "https://" + url.strip()
    html = trafilatura.fetch_url(url)
    if not html:
        raise ValueError("Impossible de télécharger cette page (adresse incorrecte, page privée ou pas d'Internet).")
    texte = trafilatura.extract(html, output_format="markdown", include_comments=False, include_tables=False,
                                include_links=False, include_formatting=True)
    if not texte or len(texte.split()) < 30:
        raise ValueError("Je n'ai pas trouvé d'article lisible sur cette page.")
    meta = trafilatura.extract_metadata(html)
    titre = (meta.title if meta and meta.title else "") or url
    # « Livre de la Genèse — Wikipédia » -> « Livre de la Genèse »
    site = (meta.sitename if meta and meta.sitename else "") or ""
    titre = re.sub(rf"\s+[—–|·-]\s+({re.escape(site)}|Wikipédia|Wikipedia)\s*$", "", titre.strip(), flags=re.I) if titre else titre
    return titre.strip(), texte


def livre_depuis_images(chemins: list[Path], nb_colonnes: int, titre: str, apprises: dict[str, str] | None = None,
                        livre_id: str = "", progres=None):
    """Captures d'écran -> livre (une image = une page). OCR de Windows en français."""
    from .ocr_image import lire_image

    pages = list(range(1, len(chemins) + 1))

    def source(p: int):
        mots, w, h = lire_image(chemins[p - 1], p)
        return mots, w, h, False  # une capture n'a pas d'en-tête de livre : on garde tout

    livre, analyses = construire_depuis(source, pages, nb_colonnes, "images", titre, apprises, livre_id, progres)
    if not livre.sections:
        raise ValueError("Aucun texte trouvé dans ces images.")
    return livre, analyses
