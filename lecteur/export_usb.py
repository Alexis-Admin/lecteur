"""Export vers une clé USB (ou un dossier) : un MP3 par section, numérotés, avec titres dans les métadonnées.

Les fichiers sont copiés UN PAR UN, dans l'ordre : beaucoup de radios d'auto lisent dans l'ordre de copie,
pas dans l'ordre alphabétique. Chaque copie est vérifiée (taille) et forcée sur la clé (fsync).
"""
from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
from pathlib import Path

from .assemblage import assembler, changer_vitesse
from .modele import Livre

_INTERDITS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def nom_fichier(texte: str, longueur: int = 110) -> str:
    """Nom sûr pour une clé FAT32 (caractères interdits retirés, pas de point final)."""
    t = _INTERDITS.sub("", texte).replace("·", "-")
    t = re.sub(r"\s+", " ", t).strip().rstrip(".")
    return t[:longueur].rstrip(" .") or "sans titre"


def cles_usb() -> list[dict]:
    """Clés USB et cartes mémoire branchées (lecteurs amovibles)."""
    res = []
    if os.name != "nt":
        return res
    k32 = ctypes.windll.kernel32
    masque = k32.GetLogicalDrives()
    for i in range(26):
        if not masque & (1 << i):
            continue
        lettre = f"{chr(65 + i)}:\\"
        if k32.GetDriveTypeW(lettre) != 2:  # 2 = amovible
            continue
        nom = ctypes.create_unicode_buffer(261)
        k32.GetVolumeInformationW(lettre, nom, 261, None, None, None, None, 0)
        try:
            u = shutil.disk_usage(lettre)
        except OSError:
            continue  # lecteur de cartes vide
        res.append({"lettre": lettre[:2], "nom": nom.value or "Clé USB", "libre": u.free, "total": u.total})
    return res


def plan(livre: Livre, minutages: list[float | None], vitesse: float) -> list[dict]:
    """Noms des fichiers et durées, dans l'ordre. minutages = durée de chaque section (None = pas d'audio)."""
    n = len(livre.sections)
    largeur = 3 if n > 99 else 2
    res = []
    for i, (s, duree) in enumerate(zip(livre.sections, minutages), 1):
        titre = f"{s.ref} {s.titre}" if s.ref else s.titre
        res.append({"section": s.id, "numero": i, "titre": titre,
                    "fichier": nom_fichier(f"{i:0{largeur}d} - {titre}") + ".mp3",
                    "duree": (duree / vitesse) if duree else None})
    return res


def ecrire_etiquettes(mp3: Path, titre: str, album: str, piste: int, total: int, artiste: str) -> None:
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3NoHeaderError

    try:
        tags = EasyID3(str(mp3))
    except ID3NoHeaderError:
        tags = EasyID3()
    tags["title"] = titre
    tags["album"] = album
    tags["artist"] = artiste
    tags["albumartist"] = artiste
    tags["tracknumber"] = f"{piste}/{total}"
    tags["genre"] = "Livre audio"
    tags.save(str(mp3))


def copier_sur(source: Path, cible: Path) -> None:
    """Copie avec écriture forcée sur la clé et vérification de la taille."""
    tmp = cible.with_name(cible.name + ".partiel")
    with open(source, "rb") as src, open(tmp, "wb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    if tmp.stat().st_size != source.stat().st_size:
        tmp.unlink(missing_ok=True)
        raise OSError(f"Copie incomplète de {cible.name}")
    if cible.exists():
        cible.unlink()
    tmp.rename(cible)


def exporter(dossier_livre: Path, livre: Livre, destination: Path, mode: str, vitesse: float, voix: str,
             nom_voix: str = "", progres=None, arret=None) -> dict:
    """Prépare et copie tous les MP3. Retourne {"copies": n, "dossier": …, "duree": s, "octets": n}."""
    dossier_cible = destination / nom_fichier(livre.titre, 60)
    dossier_cible.mkdir(parents=True, exist_ok=True)
    travail = dossier_livre / "audio" / "export"
    travail.mkdir(parents=True, exist_ok=True)
    sections = [s for s in livre.sections]
    assembles = []
    for s in sections:
        r = assembler(dossier_livre, livre, s, mode, voix)
        assembles.append(r)
    lignes = plan(livre, [r["duree"] if r else None for r in assembles], vitesse)
    a_copier = [(l, r) for l, r in zip(lignes, assembles) if r]
    total, copies, octets, duree = len(a_copier), 0, 0, 0.0
    artiste = f"Lecteur · {nom_voix}" if nom_voix else "Lecteur"
    for i, (l, r) in enumerate(a_copier, 1):
        if arret and arret():
            break
        if progres:
            progres(i - 1, total, l["fichier"])
        prepare = travail / f"{i:04d}.mp3"
        changer_vitesse(r["mp3"], prepare, vitesse)
        ecrire_etiquettes(prepare, l["titre"], livre.titre, i, total, artiste)
        copier_sur(prepare, dossier_cible / l["fichier"])
        octets += prepare.stat().st_size
        duree += l["duree"] or 0
        prepare.unlink(missing_ok=True)
        copies += 1
    if progres:
        progres(copies, total, "")
    return {"copies": copies, "total": total, "dossier": str(dossier_cible), "duree": duree, "octets": octets,
            "interrompu": bool(arret and arret())}


def ejecter(lettre: str) -> bool:
    """Éjecte la clé (comme « Éjecter » dans l'Explorateur). Faux si Windows refuse (fichier ouvert…)."""
    if not re.fullmatch(r"[A-Z]:", lettre):
        return False
    script = f"(New-Object -ComObject Shell.Application).Namespace(17).ParseName('{lettre}').InvokeVerb('Eject')"
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True,
                       creationflags=0x08000000)
    return r.returncode == 0
