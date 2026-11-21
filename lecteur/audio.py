"""Audio d'un livre : un fichier MP3 + un minutage par bloc, gardés dans le dossier du livre.

    <livre>/audio/blocs/<bloc>-<empreinte>.mp3   la voix
    <livre>/audio/blocs/<bloc>-<empreinte>.json  {"duree": s, "mots": [{d, f, a, b}], "voix": …}

L'empreinte dépend du texte prononcé et de la voix : corriger un bloc ou changer de voix ne refait
que les blocs concernés. Les anciens fichiers d'un bloc modifié sont mis à la corbeille au ménage.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .minutage import aligner
from .modele import Bloc, Livre
from .prononciation import bloc_a_lire


@dataclass
class AudioBloc:
    bloc_id: str
    mp3: Path
    minutage: Path

    def existe(self) -> bool:
        return self.mp3.exists() and self.minutage.exists()


def texte_prononce(livre: Livre, bloc: Bloc) -> str:
    return bloc_a_lire(bloc, livre.refs_nues).strip()


def empreinte(texte_lu: str, voix: str) -> str:
    return hashlib.sha1(f"{voix}\n{texte_lu}".encode("utf-8")).hexdigest()[:12]


def dossier_blocs(dossier_livre: Path) -> Path:
    return dossier_livre / "audio" / "blocs"


def audio_du_bloc(dossier_livre: Path, livre: Livre, bloc: Bloc, voix: str) -> AudioBloc | None:
    """Où vit (ou vivra) l'audio de ce bloc. None si le bloc n'a rien à dire."""
    lu = texte_prononce(livre, bloc)
    if not lu or not any(c.isalnum() for c in lu):
        return None
    base = dossier_blocs(dossier_livre) / f"{bloc.id}-{empreinte(lu, voix)}"
    return AudioBloc(bloc.id, base.with_suffix(".mp3"), base.with_suffix(".json"))


def duree_mp3(chemin: Path) -> float:
    from mutagen.mp3 import MP3

    return float(MP3(str(chemin)).info.length)


async def generer_bloc(dossier_livre: Path, livre: Livre, bloc: Bloc, voix: str, moteur) -> AudioBloc | None:
    """Crée l'audio du bloc s'il n'existe pas déjà (écriture atomique : jamais de fichier à moitié écrit)."""
    cible = audio_du_bloc(dossier_livre, livre, bloc, voix)
    if cible is None or cible.existe():
        return cible
    lu = texte_prononce(livre, bloc)
    mp3, mots = await moteur.synthetiser(lu, voix)
    cible.mp3.parent.mkdir(parents=True, exist_ok=True)
    tmp = cible.mp3.with_suffix(".mp3.tmp")
    tmp.write_bytes(mp3)
    tmp.replace(cible.mp3)
    try:
        duree = duree_mp3(cible.mp3)
    except Exception:  # noqa: BLE001 - moteur de test (faux MP3)
        duree = (mots[-1][0] + mots[-1][1]) if mots else 0.0
    donnees = {"voix": voix, "duree": round(duree, 3), "lu": lu, "mots": aligner(bloc.texte, lu, mots)}
    tmp = cible.minutage.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    tmp.replace(cible.minutage)
    try:  # bornes de la parole calculées tout de suite : les durées des sections restent instantanées
        from .assemblage import parole

        parole(cible)
    except Exception:  # noqa: BLE001 - FFmpeg absent ou faux MP3 de test : calculé plus tard
        pass
    return cible


def etat_audio(dossier_livre: Path, livre: Livre, voix: str) -> dict:
    """Combien de blocs ont déjà leur audio, au total et par section."""
    total = fait = 0
    sections = []
    for s in livre.sections:
        t = f = 0
        for b in s.blocs:
            a = audio_du_bloc(dossier_livre, livre, b, voix)
            if a is None:
                continue
            t += 1
            f += a.existe()
        total += t
        fait += f
        sections.append({"id": s.id, "total": t, "fait": f})
    return {"total": total, "fait": fait, "sections": sections}


async def generer_livre(dossier_livre: Path, livre: Livre, voix: str, moteur, *, en_parallele: int = 3,
                        progres=None, arret=None, sections: list[str] | None = None) -> dict:
    """Crée l'audio de tous les blocs qui n'en ont pas. Reprend où ça s'était arrêté.

    progres(fait, total, section_id) est appelé après chaque bloc ; arret() -> True interrompt proprement.
    """
    a_faire: list[tuple[str, Bloc]] = []
    for s in livre.sections:
        if sections and s.id not in sections:
            continue
        for b in s.blocs:
            a = audio_du_bloc(dossier_livre, livre, b, voix)
            if a is not None and not a.existe():
                a_faire.append((s.id, b))
    etat = etat_audio(dossier_livre, livre, voix)
    fait, total = etat["fait"], etat["total"]
    erreurs: list[str] = []
    file: asyncio.Queue = asyncio.Queue()
    for x in a_faire:
        file.put_nowait(x)

    async def ouvrier():
        nonlocal fait
        while not file.empty():
            if arret and arret():
                return
            section_id, bloc = await file.get()
            try:
                await generer_bloc(dossier_livre, livre, bloc, voix, moteur)
                fait += 1
            except Exception as e:  # noqa: BLE001 - on continue avec les autres blocs, on signale à la fin
                erreurs.append(str(e))
                if len(erreurs) >= 5:
                    while not file.empty():
                        file.get_nowait()
            if progres:
                progres(fait, total, section_id)

    await asyncio.gather(*(ouvrier() for _ in range(max(1, en_parallele))))
    return {"fait": fait, "total": total, "erreurs": erreurs[:3], "interrompu": bool(arret and arret())}


def menage(dossier_livre: Path, livre: Livre, voix: str) -> list[Path]:
    """Fichiers audio périmés (bloc modifié ou voix changée). L'appelant les met à la corbeille."""
    gardes = set()
    for s in livre.sections:
        for b in s.blocs:
            a = audio_du_bloc(dossier_livre, livre, b, voix)
            if a:
                gardes.update({a.mp3.name, a.minutage.name, a.mp3.with_suffix(".parole.json").name})
    d = dossier_blocs(dossier_livre)
    if not d.exists():
        return []
    return [f for f in d.iterdir() if f.name not in gardes and f.suffix in (".mp3", ".json", ".tmp")]
