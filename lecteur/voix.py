"""Moteurs de voix : edge-tts (en ligne, fr-CA), plus tard Piper (hors ligne) ou une voix premium.

Chaque moteur reçoit un texte à lire et rend (mp3, mots), où mots = [(début_s, durée_s, texte)]
dans l'ordre où ils sont prononcés. Ajouter une voix = ajouter une classe avec la même méthode.
"""
from __future__ import annotations

import asyncio
import re
import threading
from dataclasses import dataclass


class ErreurVoix(RuntimeError):
    """Erreur de création de la voix, avec un message clair pour l'interface."""


@dataclass
class Voix:
    id: str  # « edge:fr-CA-SylvieNeural »
    nom: str  # « Sylvie »
    description: str


VOIX_EDGE = [
    Voix("edge:fr-CA-SylvieNeural", "Sylvie", "Québec · femme · claire et posée"),
    Voix("edge:fr-CA-AntoineNeural", "Antoine", "Québec · homme"),
    Voix("edge:fr-CA-JeanNeural", "Jean", "Québec · homme · grave"),
    Voix("edge:fr-CA-ThierryNeural", "Thierry", "Québec · homme"),
]
VOIX_PIPER = [
    Voix("piper:fr_FR-siwis-medium", "Siwis (hors ligne)",
         "France · femme · sans Internet · 63 Mo à télécharger une fois · surlignage approximatif"),
]
VOIX_PAR_DEFAUT = VOIX_EDGE[0].id


def liste_des_voix() -> list[Voix]:
    # Voix premium payée à l'usage (plus tard) : ajouter ici une liste VOIX_PREMIUM et un moteur dans moteur_pour().
    return list(VOIX_EDGE) + list(VOIX_PIPER)


class MoteurEdge:
    """Voix neuronales de Microsoft Edge (gratuites, Internet requis). Seul le texte à lire est envoyé."""

    nom = "edge"

    async def synthetiser(self, texte: str, voix: str) -> tuple[bytes, list[tuple[float, float, str]]]:
        import edge_tts

        nom_voix = voix.split(":", 1)[1] if ":" in voix else voix
        audio = bytearray()
        mots: list[tuple[float, float, str]] = []
        dernier_essai: Exception | None = None
        for essai in range(3):
            audio.clear()
            mots.clear()
            try:
                com = edge_tts.Communicate(texte, nom_voix, boundary="WordBoundary")
                async for m in com.stream():
                    if m["type"] == "audio":
                        audio.extend(m["data"])
                    elif m["type"] == "WordBoundary":
                        mots.append((m["offset"] / 1e7, m["duration"] / 1e7, m["text"]))
                if audio:
                    return bytes(audio), mots
            except Exception as e:  # noqa: BLE001 - réseau, service saturé…
                dernier_essai = e
            await asyncio.sleep(2 * (essai + 1))
        raise ErreurVoix("La voix en ligne ne répond pas (Internet coupé ou service saturé). "
                         f"Réessaie dans quelques minutes. Détail : {dernier_essai}")


class MoteurPiper:
    """Voix Piper, entièrement hors ligne (modèle téléchargé une fois dans Documents\\Lecteur\\voix).

    Piper ne donne pas le moment de chaque mot : on le calcule phrase par phrase (chaque phrase est lue
    à part, sa durée est donc connue), puis on répartit les mots selon leur longueur.
    """

    nom = "piper"
    _charges: dict = {}
    _verrou = threading.Lock()

    def _modele(self, nom: str):
        from . import bibliotheque

        with self._verrou:
            if nom not in self._charges:
                from piper import PiperVoice
                from piper.download_voices import download_voice

                dossier = bibliotheque.racine() / "voix"
                dossier.mkdir(parents=True, exist_ok=True)
                onnx = dossier / f"{nom}.onnx"
                if not onnx.exists():
                    try:
                        download_voice(nom, dossier)
                    except Exception as e:  # noqa: BLE001
                        raise ErreurVoix(f"Téléchargement de la voix hors ligne impossible (Internet ?) : {e}") from e
                self._charges[nom] = PiperVoice.load(str(onnx))
            return self._charges[nom]

    def _synth(self, texte: str, voix: str) -> tuple[bytes, list[tuple[float, float, str]]]:
        import subprocess

        modele = self._modele(voix.split(":", 1)[1])
        phrases = [p for p in re.split(r"(?<=[.!?;:])\s+", texte.strip()) if p.strip()]
        pcm, mots, t, taux = bytearray(), [], 0.0, 22050
        for phrase in phrases:
            audio = bytearray()
            for morceau in modele.synthesize(phrase):
                taux = morceau.sample_rate
                audio.extend(morceau.audio_int16_bytes)
            duree = len(audio) / 2 / taux
            liste = re.findall(r"[\w’'\-]+", phrase)
            poids = [len(m) + 1 for m in liste]
            total = sum(poids) or 1
            debut = t
            for m, p in zip(liste, poids):
                d = duree * p / total
                mots.append((round(debut, 3), round(d * 0.9, 3), m))
                debut += d
            pcm.extend(audio)
            t += duree
        from .assemblage import ffmpeg

        r = subprocess.run([ffmpeg(), "-loglevel", "error", "-f", "s16le", "-ar", str(taux), "-ac", "1", "-i", "pipe:0",
                            "-ar", "24000", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "48k", "-f", "mp3", "pipe:1"],
                           input=bytes(pcm), capture_output=True, creationflags=0x08000000)
        if r.returncode != 0:
            raise ErreurVoix("Conversion en MP3 impossible (FFmpeg).")
        return r.stdout, mots

    async def synthetiser(self, texte: str, voix: str) -> tuple[bytes, list[tuple[float, float, str]]]:
        return await asyncio.to_thread(self._synth, texte, voix)


def moteur_pour(voix: str):
    if voix.startswith("edge:"):
        return MoteurEdge()
    if voix.startswith("piper:"):
        return MoteurPiper()
    raise ErreurVoix(f"Voix inconnue : {voix}")
