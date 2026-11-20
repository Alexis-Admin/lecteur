"""Où vivent les données : %USERPROFILE%\\Documents\\Lecteur (jamais dans le dossier de l'app)."""
from __future__ import annotations

import ctypes
import json
import os
import re
import time
import unicodedata
from pathlib import Path

from .modele import Livre


def dossier_documents() -> Path:
    """Vrai dossier « Documents » de Windows (même s'il a été déplacé, p. ex. vers OneDrive)."""
    if os.name == "nt":
        tampon = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, tampon) == 0 and tampon.value:
            return Path(tampon.value)
    return Path.home() / "Documents"


def racine() -> Path:
    r = Path(os.environ.get("LECTEUR_DONNEES") or dossier_documents() / "Lecteur")
    r.mkdir(parents=True, exist_ok=True)
    return r


def dossier_livres() -> Path:
    d = racine() / "bibliotheque"
    d.mkdir(parents=True, exist_ok=True)
    return d


def lire_json(chemin: Path, defaut):
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaut


def ecrire_json(chemin: Path, donnees) -> None:
    """Écriture atomique, et seulement si le contenu change (jamais de réécriture inutile)."""
    texte = json.dumps(donnees, ensure_ascii=False, indent=1)
    if chemin.exists() and chemin.read_text(encoding="utf-8") == texte:
        return
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(chemin.suffix + ".tmp")
    tmp.write_text(texte, encoding="utf-8")
    tmp.replace(chemin)


def nouvel_id(titre: str) -> str:
    base = unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:40] or "livre"
    return f"{base}-{time.strftime('%Y%m%d-%H%M%S')}"


def chemin_livre(livre_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9\-]+", livre_id):
        raise ValueError("identifiant de livre invalide")
    return dossier_livres() / livre_id / "livre.json"


def enregistrer(livre: Livre, meta: dict | None = None) -> None:
    livre.enregistrer(chemin_livre(livre.id))
    if meta is not None:
        ecrire_json(chemin_livre(livre.id).with_name("meta.json"), meta)


def ouvrir(livre_id: str) -> Livre:
    return Livre.ouvrir(chemin_livre(livre_id))


def meta(livre_id: str) -> dict:
    return lire_json(chemin_livre(livre_id).with_name("meta.json"), {})


def ecrire_meta(livre_id: str, donnees: dict) -> None:
    ecrire_json(chemin_livre(livre_id).with_name("meta.json"), donnees)


def liste() -> list[dict]:
    res = []
    for d in sorted(dossier_livres().iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        f = d / "livre.json"
        if not f.exists():
            continue
        m = lire_json(d / "meta.json", {})
        res.append({"id": d.name, "titre": m.get("titre") or d.name, "profil": m.get("profil", ""), "type": m.get("type", "pdf"),
                    "pages": m.get("nb_pages", 0), "sections": m.get("nb_sections", 0), "importe_le": m.get("importe_le", "")})
    return res


# --- corrections apprises et mots acceptés (communs à tous les livres) -----------
def corrections() -> dict:
    return lire_json(racine() / "corrections.json", {"apprises": {}, "ignores": []})


def ecrire_corrections(c: dict) -> None:
    ecrire_json(racine() / "corrections.json", c)


# --- réglages (fenêtre, thème, vitesse…) -------------------------------------------
def reglages() -> dict:
    return lire_json(racine() / "reglages.json", {})


def ecrire_reglages(r: dict) -> None:
    ecrire_json(racine() / "reglages.json", r)
