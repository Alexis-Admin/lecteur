"""Verrou de commit : refuse tout fichier qui ne doit pas aller sur GitHub (dépôt public).

Lancé automatiquement avant chaque commit (outils/hooks/pre-commit).
Refuse : PDF, images, audio, livres, fichiers de données, gros fichiers, et texte qui
ressemble à un extrait de livre (versets numérotés en série).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

INTERDITS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".svg",
             ".mp3", ".wav", ".ogg", ".m4a", ".opus", ".flac", ".aac", ".epub", ".mobi", ".docx", ".doc",
             ".zip", ".7z", ".json", ".txt", ".csv", ".xlsx", ".db", ".sqlite", ".lecteur", ".onnx",
             ".woff2", ".woff", ".ttf", ".otf"}
PERMIS_TXT = {"requirements.txt"}
DOSSIERS_INTERDITS = ("donnees/", "bibliotheque/", "livres/", "audio/")
TAILLE_MAX = 300_000  # octets


def fichiers_indexes() -> list[str]:
    sortie = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                            capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return [l.strip() for l in sortie.splitlines() if l.strip()]


def ressemble_a_un_livre(texte: str) -> bool:
    """Plusieurs numéros de verset consécutifs dans un même paragraphe (« 12 … 13 … 14 … »)."""
    nums = [int(n) for n in re.findall(r"(?<![\d.,])(\d{1,3}) [A-ZÀ-Üa-zà-ÿ«]", texte)]
    suite = 1
    for a, b in zip(nums, nums[1:]):
        suite = suite + 1 if b == a + 1 else 1
        if suite >= 6:
            return True
    return False


def verifier(chemins: list[str]) -> list[str]:
    problemes = []
    for chemin in chemins:
        p = Path(chemin)
        nom = p.name.lower()
        # Seule exception binaire : les polices de l'interface (licence OFL), petites.
        if chemin.replace("\\", "/").startswith("ui/polices/") and p.suffix.lower() == ".woff2":
            if p.exists() and p.stat().st_size > TAILLE_MAX:
                problemes.append(f"{chemin} : police trop grosse")
            continue
        if p.suffix.lower() in INTERDITS and nom not in PERMIS_TXT:
            problemes.append(f"{chemin} : type de fichier interdit ({p.suffix})")
            continue
        if any(d in chemin.replace("\\", "/").lower() for d in DOSSIERS_INTERDITS):
            problemes.append(f"{chemin} : dossier de données")
            continue
        if p.exists():
            if p.stat().st_size > TAILLE_MAX:
                problemes.append(f"{chemin} : trop gros ({p.stat().st_size // 1000} Ko)")
                continue
            try:
                contenu = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                problemes.append(f"{chemin} : fichier binaire")
                continue
            if p.suffix.lower() in {".md", ".html", ".js", ".py"} and ressemble_a_un_livre(contenu):
                problemes.append(f"{chemin} : ressemble à un extrait de livre (versets numérotés)")
    return problemes


def main() -> int:
    problemes = verifier(fichiers_indexes())
    if problemes:
        print("\n  VERROU : commit refusé. Ces fichiers ne doivent pas aller sur GitHub :\n")
        for p in problemes:
            print("   -", p)
        print("\n  Retire-les avec : git restore --staged <fichier>\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
