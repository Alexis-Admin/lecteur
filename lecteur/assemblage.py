"""Assemble l'audio d'une section (blocs + silences) en un seul MP3, avec le minutage de tous les mots.

Utilise FFmpeg (installé sur le PC). Le fichier de section est refait seulement si un de ses blocs change.
    <livre>/audio/sections/<section>-<mode>-<empreinte>.mp3 / .json
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from .audio import audio_du_bloc
from .modele import Livre, Section, liste_de_lecture

# Silences (secondes) après chaque genre de bloc.
SILENCES = {"partie": 0.9, "titre": 1.0, "verset": 0.35, "paragraphe": 0.6, "note": 0.8, "note_trad": 0.8, "encadre": 0.9}
_FLAGS = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0  # pas de console noire


class ErreurAssemblage(RuntimeError):
    pass


def ffmpeg() -> str:
    chemin = shutil.which("ffmpeg")
    if not chemin:
        raise ErreurAssemblage("FFmpeg n'est pas installé. Ouvre un terminal et tape : winget install Gyan.FFmpeg "
                               "(puis relance l'app).")
    return chemin


def _lancer(args: list[str]) -> None:
    r = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True,
                       text=True, creationflags=_FLAGS)
    if r.returncode != 0:
        raise ErreurAssemblage(f"FFmpeg a échoué : {r.stderr.strip()[-300:]}")


def silence(dossier_livre: Path, secondes: float) -> Path:
    """MP3 de silence au même format que la voix (24 kHz, mono, 48 kbit/s)."""
    d = dossier_livre / "audio" / "silences"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"silence-{int(secondes * 1000)}.mp3"
    if not f.exists():
        tmp = f.with_name(f.stem + ".tmp.mp3")
        _lancer(["-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", f"{secondes:.3f}",
                 "-c:a", "libmp3lame", "-b:a", "48k", str(tmp)])
        tmp.replace(f)
    return f


def morceaux(dossier_livre: Path, livre: Livre, section: Section, mode: str, voix: str) -> list[tuple]:
    """[(bloc, AudioBloc, silence_apres)] dans l'ordre de lecture ; None si un bloc n'a pas encore son audio."""
    res = []
    for b in liste_de_lecture(section, mode):
        a = audio_du_bloc(dossier_livre, livre, b, voix)
        if a is None:
            continue
        if not a.existe():
            return None
        res.append((b, a, SILENCES.get(b.genre, 0.5)))
    return res


def duree_section(dossier_livre: Path, livre: Livre, section: Section, mode: str, voix: str) -> float | None:
    """Durée de la section sans l'assembler (None si son audio n'est pas complet)."""
    liste = morceaux(dossier_livre, livre, section, mode, voix)
    if not liste:
        return None
    return sum(json.loads(a.minutage.read_text(encoding="utf-8"))["duree"] + s for _, a, s in liste)


def _ligne_concat(chemin: Path) -> str:
    return "file '" + chemin.as_posix().replace("'", "'\\''") + "'"


def _base_section(dossier_livre: Path, section: Section, mode: str, liste: list) -> Path:
    cle = hashlib.sha1("|".join(f"{a.mp3.name}:{s}" for _, a, s in liste).encode()).hexdigest()[:10]
    return dossier_livre / "audio" / "sections" / f"{section.id}-{mode}-{cle}"


def sections_perimees(dossier_livre: Path, livre: Livre, voix: str) -> list[Path]:
    """Fichiers de sections assemblées qui ne servent plus (texte corrigé, voix changée…)."""
    d = dossier_livre / "audio" / "sections"
    if not d.exists():
        return []
    gardes = set()
    for s in livre.sections:
        for mode in ("texte", "notes", "mixte"):
            liste = morceaux(dossier_livre, livre, s, mode, voix)
            if liste:
                b = _base_section(dossier_livre, s, mode, liste)
                gardes.update({b.name + ".mp3", b.name + ".json"})
    return [f for f in d.iterdir() if f.name not in gardes]


def assembler(dossier_livre: Path, livre: Livre, section: Section, mode: str, voix: str) -> dict | None:
    """Retourne {"mp3": Path, "minutage": Path, "duree": s} ou None si l'audio n'est pas complet."""
    liste = morceaux(dossier_livre, livre, section, mode, voix)
    if not liste:
        return None
    base = _base_section(dossier_livre, section, mode, liste)
    d = base.parent
    d.mkdir(parents=True, exist_ok=True)
    mp3, js = base.with_suffix(".mp3"), base.with_suffix(".json")
    if mp3.exists() and js.exists():
        return {"mp3": mp3, "minutage": js, "duree": json.loads(js.read_text(encoding="utf-8"))["duree"]}

    # Liste pour le « concat demuxer » de FFmpeg, et minutage cumulé.
    lignes, blocs_min, t = [], [], 0.0
    for b, a, s in liste:
        m = json.loads(a.minutage.read_text(encoding="utf-8"))
        blocs_min.append({"bloc": b.id, "piste": b.piste, "debut": round(t, 3), "fin": round(t + m["duree"], 3),
                          "mots": [{**x, "d": round(x["d"] + t, 3), "f": round(x["f"] + t, 3)} for x in m["mots"]]})
        lignes.append(_ligne_concat(a.mp3))
        t += m["duree"]
        sil = silence(dossier_livre, s)
        lignes.append(_ligne_concat(sil))
        t += s
    liste_txt = base.with_suffix(".txt")
    liste_txt.write_text("\n".join(lignes), encoding="utf-8")
    tmp = base.with_name(base.name + ".tmp.mp3")
    try:
        _lancer(["-f", "concat", "-safe", "0", "-i", str(liste_txt), "-c", "copy", str(tmp)])
        tmp.replace(mp3)
    finally:
        liste_txt.unlink(missing_ok=True)
    js.write_text(json.dumps({"mode": mode, "duree": round(t, 3), "blocs": blocs_min}, ensure_ascii=False), encoding="utf-8")
    return {"mp3": mp3, "minutage": js, "duree": round(t, 3)}


def changer_vitesse(source: Path, cible: Path, vitesse: float) -> None:
    """Copie le MP3 à une autre vitesse sans changer la hauteur de la voix (pour la clé USB)."""
    if abs(vitesse - 1.0) < 0.01:
        shutil.copyfile(source, cible)
        return
    filtres, v = [], vitesse
    while v > 2.0:  # atempo accepte 0,5 à 2 par étape
        filtres.append("atempo=2.0")
        v /= 2.0
    filtres.append(f"atempo={v:.4f}")
    _lancer(["-i", str(source), "-filter:a", ",".join(filtres), "-c:a", "libmp3lame", "-b:a", "48k", "-ac", "1",
             "-ar", "24000", str(cible)])
