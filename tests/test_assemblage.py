"""Assemblage d'une section (FFmpeg) et changement de vitesse pour la clé USB."""
import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from lecteur.assemblage import assembler, changer_vitesse
from lecteur.audio import duree_mp3, generer_livre
from lecteur.modele import Bloc, Livre, Section

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg absent")


class VoixBip:
    """Fausse voix qui rend un vrai MP3 (un bip de 1 s) au format de edge-tts."""

    def __init__(self, dossier: Path):
        self.mp3 = dossier / "bip.mp3"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                        "-ar", "24000", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "48k", str(self.mp3)], check=True)

    async def synthetiser(self, texte, voix):
        mots = [(i * 0.2, 0.15, m) for i, m in enumerate(texte.split()[:5])]
        return self.mp3.read_bytes(), mots


def _livre():
    s = Section("s001", "Essai", blocs=[
        Bloc("b1", "texte", "titre", "Le jardin"),
        Bloc("b2", "texte", "verset", "Premier verset.", 1, 1),
        Bloc("b3", "texte", "verset", "Deuxième verset.", 1, 2),
        Bloc("b4", "notes", "note", "Une note.", 1, 1, ref="1.1"),
    ])
    return Livre("essai", "Essai", "bible_etude", "", [1], "Gn", sections=[s])


def test_assembler_et_minutage(tmp_path: Path):
    livre, voix = _livre(), "edge:x"
    assert assembler(tmp_path, livre, livre.sections[0], "mixte", voix) is None  # audio pas encore créé
    asyncio.run(generer_livre(tmp_path, livre, voix, VoixBip(tmp_path)))
    r = assembler(tmp_path, livre, livre.sections[0], "mixte", voix)
    m = json.loads(r["minutage"].read_text(encoding="utf-8"))
    assert [b["bloc"] for b in m["blocs"]] == ["b1", "b2", "b4", "b3"]  # la note suit son verset
    assert abs(duree_mp3(r["mp3"]) - m["duree"]) < 0.25  # minutage fidèle au fichier
    assert m["blocs"][1]["debut"] > m["blocs"][0]["fin"]  # silence entre les blocs
    seul = assembler(tmp_path, livre, livre.sections[0], "texte", voix)
    assert [b["bloc"] for b in json.loads(seul["minutage"].read_text(encoding="utf-8"))["blocs"]] == ["b1", "b2", "b3"]
    # Deuxième appel : déjà fait, même fichier
    assert assembler(tmp_path, livre, livre.sections[0], "mixte", voix)["mp3"] == r["mp3"]


def test_vitesse_cle_usb(tmp_path: Path):
    voix = VoixBip(tmp_path)
    rapide = tmp_path / "rapide.mp3"
    changer_vitesse(voix.mp3, rapide, 1.25)
    assert abs(duree_mp3(rapide) - 0.8) < 0.1
