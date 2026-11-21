"""Publie une version dans les GitHub Releases : zip du code (git archive) + notes de version.

    .venv\\Scripts\\python.exe -m outils.publier

Refuse si : des changements ne sont pas commités, la branche n'est pas poussée, ou la version existe déjà.
Le zip ne contient que les fichiers suivis par Git (donc jamais de livre, d'audio ni de données).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=RACINE, capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    version = re.search(r'__version__ = "([^"]+)"', (RACINE / "lecteur" / "__init__.py").read_text(encoding="utf-8")).group(1)
    tag = f"v{version}"
    if git("status", "--porcelain"):
        print("Des changements ne sont pas commités : fais un commit d'abord.")
        return 1
    git("fetch", "-q")
    if git("rev-parse", "HEAD") != git("rev-parse", "@{u}"):
        print("La branche n'est pas à jour sur GitHub : fais « git push » d'abord.")
        return 1
    existe = subprocess.run(["gh", "release", "view", tag], cwd=RACINE, capture_output=True).returncode == 0
    if existe:
        print(f"La version {tag} existe déjà. Monte la version dans lecteur/__init__.py.")
        return 1
    # Notes de cette version seulement
    notes = (RACINE / "NOTES-DE-VERSION.md").read_text(encoding="utf-8")
    m = re.search(rf"^## {re.escape(version)}.*?(?=^## |\Z)", notes, re.S | re.M)
    if not m:
        print(f"Ajoute une section « ## {version} » dans NOTES-DE-VERSION.md.")
        return 1
    dist = RACINE / "dist"
    dist.mkdir(exist_ok=True)
    zip_ = dist / f"Lecteur-{version}.zip"
    git("archive", "--format=zip", f"--prefix=Lecteur-{version}/", "-o", str(zip_), "HEAD")
    fichier_notes = dist / f"notes-{version}.md"
    fichier_notes.write_text(m.group(0).strip() + "\n\nInstallation : voir GUIDE-INSTALLATION.md.\n", encoding="utf-8")
    subprocess.run(["gh", "release", "create", tag, str(zip_), "--title", f"Lecteur {version}",
                    "--notes-file", str(fichier_notes)], cwd=RACINE, check=True)
    print(f"Publié : {tag} ({zip_.stat().st_size // 1000} Ko)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
