"""Assemble l'audio d'une section (blocs + silences) en un seul MP3, avec le minutage de tous les mots.

Utilise FFmpeg (installé sur le PC). Le fichier de section est refait seulement si un de ses blocs change.
    <livre>/audio/sections/<section>-<mode>-<empreinte>.mp3 / .json
"""
from __future__ import annotations

import array
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .audio import audio_du_bloc
from .modele import Livre, Section, liste_de_lecture

# Pauses (secondes) entre deux blocs, une fois retirés les silences que la voix met au début et à la fin
# de chaque morceau (edge-tts : ≈ 0,2 s avant, ≈ 0,85 s après). Sans ça, chaque verset était suivi d'un
# trou d'environ 1,4 s, même quand la phrase continuait au verset suivant.
PAUSE_SUITE = 0.15        # la phrase continue au bloc suivant (pas de point final)
PAUSE_PHRASE = 0.5        # fin de phrase
PAUSE_PARAGRAPHE = 0.7    # fin de paragraphe d'un commentaire
PAUSE_TITRE = 0.75        # après un titre ou une partie
PAUSE_CHANGEMENT = 0.8    # passage du texte biblique à une note, ou retour au texte
PAUSE_FIN = 0.4           # fin de la section
SILENCES = {"partie": PAUSE_TITRE, "titre": PAUSE_TITRE, "verset": PAUSE_PHRASE, "paragraphe": PAUSE_PARAGRAPHE,
            "note": PAUSE_CHANGEMENT, "note_trad": PAUSE_CHANGEMENT, "encadre": PAUSE_CHANGEMENT}
TAUX = 24000              # échantillons par seconde (format de la voix : 24 kHz mono)
VERSION_ASSEMBLAGE = "2"  # changer ce numéro refait les sections assemblées
_FIN_DE_PHRASE = re.compile(r"[.!?…]\W*$")
_FLAGS = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0  # pas de console noire


def pause_apres(bloc, suivant) -> float:
    """Pause après un bloc, selon ce qui suit et sa ponctuation finale."""
    if suivant is None:
        return PAUSE_FIN
    if bloc.genre in ("titre", "partie"):
        return PAUSE_TITRE
    if suivant.piste != bloc.piste or bloc.genre in ("note", "note_trad", "encadre"):
        return PAUSE_CHANGEMENT
    if not _FIN_DE_PHRASE.search(bloc.texte.strip()):
        return PAUSE_SUITE
    return PAUSE_PARAGRAPHE if bloc.genre == "paragraphe" else PAUSE_PHRASE


def _decoder(mp3: Path) -> bytes:
    """MP3 → échantillons bruts (16 bits, 24 kHz, mono)."""
    r = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", str(mp3), "-f", "s16le", "-ac", "1",
                        "-ar", str(TAUX), "-"], capture_output=True, creationflags=_FLAGS)
    if r.returncode != 0:
        raise ErreurAssemblage(f"Lecture impossible de {mp3.name} : {r.stderr.decode(errors='replace')[-200:]}")
    return r.stdout


def bornes_parole(pcm: bytes, seuil: int = 400, avant: float = 0.04, apres: float = 0.12) -> tuple[int, int]:
    """Premier et dernier échantillon où l'on parle (avec une petite marge), en nombre d'échantillons."""
    ech = array.array("h")
    ech.frombytes(pcm[: len(pcm) // 2 * 2])
    n = len(ech)
    fen = TAUX // 100  # fenêtres de 10 ms
    debut, fin = 0, n
    for i in range(0, n, fen):
        if max(map(abs, ech[i:i + fen]), default=0) > seuil:
            debut = i
            break
    else:
        return 0, n  # rien d'audible : on garde tout
    for i in range(n - fen, -1, -fen):
        if max(map(abs, ech[max(0, i):i + fen]), default=0) > seuil:
            fin = min(n, i + fen)
            break
    return max(0, debut - int(avant * TAUX)), min(n, fin + int(apres * TAUX))


def parole(a) -> tuple[float, float, bytes]:
    """(début, fin) de la parole dans le MP3 du bloc, en secondes, et ses échantillons.

    Les bornes sont gardées à côté du MP3 (.parole.json) pour calculer les durées sans tout décoder.
    """
    pcm = _decoder(a.mp3)
    d, f = bornes_parole(pcm)
    cache = a.mp3.with_suffix(".parole.json")
    if not cache.exists():
        tmp = cache.with_name(f"{cache.name}.{os.getpid()}-{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps({"debut": d / TAUX, "fin": f / TAUX}), encoding="utf-8")
        try:
            tmp.replace(cache)
        except OSError:  # un autre fil vient de l'écrire : même contenu
            tmp.unlink(missing_ok=True)
    return d / TAUX, f / TAUX, pcm


def duree_parole(a) -> float:
    cache = a.mp3.with_suffix(".parole.json")
    if cache.exists():
        c = json.loads(cache.read_text(encoding="utf-8"))
        return c["fin"] - c["debut"]
    d, f, _ = parole(a)
    return f - d


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
    paires = []
    for b in liste_de_lecture(section, mode):
        a = audio_du_bloc(dossier_livre, livre, b, voix)
        if a is None:
            continue
        if not a.existe():
            return None
        paires.append((b, a))
    return [(b, a, pause_apres(b, paires[i + 1][0] if i + 1 < len(paires) else None))
            for i, (b, a) in enumerate(paires)]


def duree_section(dossier_livre: Path, livre: Livre, section: Section, mode: str, voix: str) -> float | None:
    """Durée de la section sans l'assembler (None si son audio n'est pas complet)."""
    liste = morceaux(dossier_livre, livre, section, mode, voix)
    if not liste:
        return None
    return sum(duree_parole(a) + s for _, a, s in liste)


def _ligne_concat(chemin: Path) -> str:
    return "file '" + chemin.as_posix().replace("'", "'\\''") + "'"


def _base_section(dossier_livre: Path, section: Section, mode: str, liste: list) -> Path:
    cle = hashlib.sha1((VERSION_ASSEMBLAGE + "|" + "|".join(f"{a.mp3.name}:{s}" for _, a, s in liste)).encode()).hexdigest()[:10]
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

    # Chaque bloc est décodé, ses silences de début et de fin sont coupés, puis on ajoute la pause voulue.
    # Tout est compté en échantillons : le minutage reste exact jusqu'à la fin de la section.
    brut = bytearray()
    blocs_min = []
    with ThreadPoolExecutor(max_workers=8) as pool:  # décodage en parallèle : FFmpeg tourne hors de Python
        decodes = list(pool.map(lambda x: parole(x[1]), liste))
    for (b, a, s), (debut, fin, pcm) in zip(liste, decodes):
        m = json.loads(a.minutage.read_text(encoding="utf-8"))
        t = len(brut) // 2 / TAUX
        brut += pcm[int(debut * TAUX) * 2: int(fin * TAUX) * 2]
        t_fin = len(brut) // 2 / TAUX
        mots = []
        for x in m["mots"]:
            d = min(max(x["d"] - debut, 0.0), fin - debut)
            f = min(max(x["f"] - debut, d), fin - debut)
            mots.append({**x, "d": round(d + t, 3), "f": round(f + t, 3)})
        blocs_min.append({"bloc": b.id, "piste": b.piste, "debut": round(t, 3), "fin": round(t_fin, 3), "mots": mots})
        brut += bytes(int(s * TAUX) * 2)
    t = len(brut) // 2 / TAUX
    unique = f"{os.getpid()}-{threading.get_ident()}"  # deux assemblages en même temps ne se marchent pas dessus
    raw = base.with_name(f"{base.name}.{unique}.raw")
    tmp = base.with_name(f"{base.name}.{unique}.tmp.mp3")
    try:
        raw.write_bytes(bytes(brut))
        _lancer(["-f", "s16le", "-ar", str(TAUX), "-ac", "1", "-i", str(raw), "-c:a", "libmp3lame", "-b:a", "48k",
                 str(tmp)])
        tmp.replace(mp3)
    finally:
        raw.unlink(missing_ok=True)
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
