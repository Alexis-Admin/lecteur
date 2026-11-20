"""Point d'entrée de l'import : PDF -> Livre (selon un profil de mise en page)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymupdf

from .modele import Livre
from .profils import bible_etude, deux_colonnes, simple

PROFILS = {
    bible_etude.NOM: ("Bible d'étude", bible_etude.construire),
    deux_colonnes.NOM: ("Commentaire 2 colonnes", deux_colonnes.construire),
    simple.NOM: ("Livre simple", simple.construire),
}


def lire_pages(texte: str, maximum: int) -> list[int]:
    """« 15-17, 29 » -> [15, 16, 17, 29]. Vide = toutes les pages."""
    texte = (texte or "").strip()
    if not texte:
        return list(range(1, maximum + 1))
    pages: list[int] = []
    for morceau in texte.replace(";", ",").split(","):
        morceau = morceau.strip()
        if not morceau:
            continue
        if "-" in morceau:
            a, b = (int(x) for x in morceau.split("-", 1))
            pages.extend(range(a, b + 1))
        else:
            pages.append(int(morceau))
    return [p for p in pages if 1 <= p <= maximum]


def importer_pdf(chemin: Path, profil: str, pages: str = "", titre: str | None = None,
                 apprises: dict[str, str] | None = None, livre_id: str = "", progres=None):
    """Retourne (livre, analyses par page). Le PDF est seulement lu, jamais modifié."""
    with pymupdf.open(chemin) as doc:
        liste = lire_pages(pages, len(doc))
        if not liste:
            raise ValueError("Aucune page à importer : vérifie les numéros de pages.")
        _, fonction = PROFILS[profil]
        livre, analyses = fonction(doc, liste, titre=titre, apprises=apprises, livre_id=livre_id, progres=progres)
    livre.source = Path(chemin).name
    return livre, analyses


def _main() -> None:  # outil de développement : python -m lecteur.importer fichier.pdf --pages 15-17
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("pdf")
    p.add_argument("--profil", default=bible_etude.NOM)
    p.add_argument("--pages", default="")
    p.add_argument("--lu", action="store_true", help="affiche aussi le texte prononcé")
    a = p.parse_args()
    from .prononciation import a_lire, etiquette_a_lire

    livre, _ = importer_pdf(Path(a.pdf), a.profil, a.pages)
    print(f"# {livre.titre} ({livre.abreviation}) — {len(livre.sections)} sections")
    for s in livre.sections:
        print(f"\n== {s.ref} · {s.titre}")
        for b in s.blocs:
            etiq = f"{b.ch}.{b.v}" if b.ch else ""
            print(f"  [{b.piste[0]}:{b.genre}:{b.ref or etiq}] {b.texte}")
            if a.lu:
                prefixe = etiquette_a_lire(b.ref) + ". " if b.genre == "note" and b.ref else ""
                print(f"      ↳ {prefixe}{a_lire(b.texte, livre.refs_nues)}")
    print(f"\n# {len(livre.corrections)} corrections automatiques")
    for c in livre.corrections[:60]:
        print(f"  p{c['page']}: {c['avant']!r} -> {c['apres']!r}")


if __name__ == "__main__":
    _main()
