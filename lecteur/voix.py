"""Moteurs de voix : edge-tts (en ligne, fr-CA), plus tard Piper (hors ligne) ou une voix premium.

Chaque moteur reçoit un texte à lire et rend (mp3, mots), où mots = [(début_s, durée_s, texte)]
dans l'ordre où ils sont prononcés. Ajouter une voix = ajouter une classe avec la même méthode.
"""
from __future__ import annotations

import asyncio
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
VOIX_PAR_DEFAUT = VOIX_EDGE[0].id


def liste_des_voix() -> list[Voix]:
    return list(VOIX_EDGE)


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


def moteur_pour(voix: str):
    if voix.startswith("edge:"):
        return MoteurEdge()
    raise ErreurVoix(f"Voix inconnue : {voix}")
