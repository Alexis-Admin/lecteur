"""Icône de Lecteur (fenêtre, barre des tâches, raccourci), dessinée par le code.

Le dépôt est public et n'accepte aucune image : l'icône est donc calculée ici (livre ouvert couleur laiton sur
fond bleu encre, avec une onde de voix) et écrite dans un fichier .ico la première fois.
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

ENCRE_HAUT, ENCRE_BAS = (0x16, 0x23, 0x3B), (0x2A, 0x3D, 0x5C)
LAITON_CLAIR, LAITON = (0xF0, 0xD8, 0xA8), (0xC9, 0xA4, 0x6A)
TAILLES = (16, 24, 32, 48, 64, 256)


def _dans_carre_arrondi(x: float, y: float, r: float) -> bool:
    cx, cy = min(max(x, r), 1 - r), min(max(y, r), 1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _couleur(x: float, y: float) -> tuple[int, int, int, int] | None:
    """Couleur au point (x, y) dans [0, 1]² ; None = transparent."""
    if not _dans_carre_arrondi(x, y, 0.22):
        return None
    mix = lambda a, b, t: tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))  # noqa: E731
    fond = mix(ENCRE_HAUT, ENCRE_BAS, y)
    # Livre ouvert : deux pages légèrement inclinées, reliure au centre.
    for cote in (-1, 1):
        u = (x - 0.5) * cote  # 0 au centre, positif vers l'extérieur
        if 0.02 <= u <= 0.33:
            haut = 0.40 - 0.06 * (u / 0.33)
            bas = 0.78 - 0.02 * (u / 0.33)
            if haut <= y <= bas:
                # lignes de texte sur la page
                ligne = (y - haut) / (bas - haut)
                if 0.08 < u < 0.29 and 0.22 < ligne < 0.9 and (ligne * 6) % 1 < 0.28:
                    return (*mix(LAITON, ENCRE_BAS, 0.45), 255)
                return (*mix(LAITON_CLAIR, LAITON, ligne), 255)
    # Voix au-dessus du livre : cinq barres de son arrondies, la plus haute au centre.
    for centre, hauteur in ((0.34, 0.07), (0.42, 0.13), (0.5, 0.19), (0.58, 0.13), (0.66, 0.07)):
        demi = 0.026
        milieu = 0.24
        if abs(x - centre) <= demi:
            haut, bas = milieu - hauteur / 2, milieu + hauteur / 2
            if haut <= y <= bas:
                return (*LAITON_CLAIR, 255)
            for bout in (haut, bas):  # bouts arrondis
                if math.hypot(x - centre, y - bout) <= demi:
                    return (*LAITON_CLAIR, 255)
    return (*fond, 255)


def _png(taille: int) -> bytes:
    ech = 4 if taille <= 64 else 2  # suréchantillonnage pour des bords lisses
    lignes = bytearray()
    for py in range(taille):
        lignes.append(0)
        for px in range(taille):
            r = g = b = a = 0
            for sy in range(ech):
                for sx in range(ech):
                    c = _couleur((px + (sx + 0.5) / ech) / taille, (py + (sy + 0.5) / ech) / taille)
                    if c:
                        r, g, b, a = r + c[0] * c[3], g + c[1] * c[3], b + c[2] * c[3], a + c[3]
            n = ech * ech
            lignes += bytes((r // a, g // a, b // a, a // n) if a else (0, 0, 0, 0))

    def bloc(type_: bytes, donnees: bytes) -> bytes:
        return struct.pack(">I", len(donnees)) + type_ + donnees + struct.pack(">I", zlib.crc32(type_ + donnees))

    return (b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", struct.pack(">IIBBBBB", taille, taille, 8, 6, 0, 0, 0))
            + bloc(b"IDAT", zlib.compress(bytes(lignes), 9)) + bloc(b"IEND", b""))


def creer_ico(chemin: Path) -> Path:
    images = [_png(t) for t in TAILLES]
    entete = struct.pack("<HHH", 0, 1, len(images))
    decalage = 6 + 16 * len(images)
    repertoire, donnees = b"", b""
    for t, img in zip(TAILLES, images):
        repertoire += struct.pack("<BBBBHHII", t % 256, t % 256, 0, 0, 1, 32, len(img), decalage + len(donnees))
        donnees += img
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".tmp")
    tmp.write_bytes(entete + repertoire + donnees)
    tmp.replace(chemin)
    return chemin


def chemin_icone() -> Path:
    """L'icône, créée au premier lancement dans le dossier de l'app (ignorée par Git)."""
    f = Path(__file__).resolve().parent.parent / "lecteur.ico"
    if not f.exists():
        creer_ico(f)
    return f


if __name__ == "__main__":  # .venv\Scripts\python.exe -m lecteur.icone  → recrée l'icône
    f = Path(__file__).resolve().parent.parent / "lecteur.ico"
    print(creer_ico(f))
