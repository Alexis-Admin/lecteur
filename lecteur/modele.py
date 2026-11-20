"""Structure d'un livre importé : sections, blocs de texte (texte principal et notes)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

FORMAT = 1


@dataclass
class Bloc:
    id: str
    piste: str  # "texte" ou "notes"
    genre: str  # "titre", "partie", "verset", "paragraphe", "note", "encadre", "note_trad"
    texte: str
    ch: int | None = None  # verset (ou verset d'ancrage pour une note)
    v: int | None = None
    ref: str | None = None  # étiquette d'une note : « 5.1ss »
    page: int | None = None
    ch_fin: int | None = None
    v_fin: int | None = None


@dataclass
class Section:
    id: str
    titre: str
    ref: str = ""  # « Gn 5.1-32 »
    blocs: list[Bloc] = field(default_factory=list)

    def blocs_de(self, piste: str) -> list[Bloc]:
        return [b for b in self.blocs if b.piste == piste]


@dataclass
class Livre:
    id: str
    titre: str
    profil: str
    source: str  # nom du fichier d'origine (jamais le chemin complet)
    pages: list[int] = field(default_factory=list)
    abreviation: str = ""  # « Gn » pour une Bible
    refs_nues: bool = False  # lire « 4.17 » comme une référence
    sections: list[Section] = field(default_factory=list)
    corrections: list[dict] = field(default_factory=list)  # journal des corrections automatiques
    format: int = FORMAT

    # --- lecture ---------------------------------------------------------
    def a_des_notes(self) -> bool:
        return any(b.piste == "notes" for s in self.sections for b in s.blocs)

    def bloc(self, bloc_id: str) -> Bloc | None:
        for s in self.sections:
            for b in s.blocs:
                if b.id == bloc_id:
                    return b
        return None

    # --- JSON ------------------------------------------------------------
    def vers_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def depuis_dict(d: dict) -> "Livre":
        sections = [
            Section(s["id"], s["titre"], s.get("ref", ""), [Bloc(**b) for b in s.get("blocs", [])])
            for s in d.get("sections", [])
        ]
        champs = {k: v for k, v in d.items() if k != "sections"}
        return Livre(**champs, sections=sections)

    def enregistrer(self, chemin: Path) -> None:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        tmp = chemin.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.vers_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(chemin)  # écriture atomique : jamais de fichier à moitié écrit

    @staticmethod
    def ouvrir(chemin: Path) -> "Livre":
        return Livre.depuis_dict(json.loads(chemin.read_text(encoding="utf-8")))


def liste_de_lecture(section: Section, mode: str) -> list[Bloc]:
    """Blocs à lire selon le mode : « texte », « notes » ou « mixte » (chaque note après son verset)."""
    texte = section.blocs_de("texte")
    notes = section.blocs_de("notes")
    if mode == "texte" or not notes:
        return texte if mode != "notes" else notes
    if mode == "notes":
        return notes
    restantes = list(notes)
    res: list[Bloc] = []
    for b in texte:
        res.append(b)
        if b.genre == "verset":
            a_inserer = [n for n in restantes if (n.ch, n.v) == (b.ch, b.v)]
            res.extend(a_inserer)
            restantes = [n for n in restantes if n not in a_inserer]
    res.extend(restantes)
    return res
