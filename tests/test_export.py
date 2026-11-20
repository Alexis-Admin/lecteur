"""Export clé USB : noms de fichiers sûrs, ordre, métadonnées, vitesse (dans un dossier temporaire)."""
import asyncio
import shutil
from pathlib import Path

import pytest

from lecteur.audio import duree_mp3, generer_livre
from lecteur.export_usb import exporter, nom_fichier, plan
from lecteur.modele import Bloc, Livre, Section
from tests.test_assemblage import VoixBip


def _livre(n=3):
    sections = [Section(f"s{i:03d}", f"Partie : {i}?", ref=f"Gn {i}.1-5",
                        blocs=[Bloc(f"b{i}", "texte", "verset", f"Texte {i}.", i, 1)]) for i in range(1, n + 1)]
    return Livre("essai", "Genèse / essai", "bible_etude", "", [1], "Gn", sections=sections)


def test_nom_fichier_fat32():
    assert nom_fichier('01 - Gn 1.1 Quoi? "Oui" / non.') == "01 - Gn 1.1 Quoi Oui non"
    assert len(nom_fichier("x" * 300)) == 110


def test_plan_numerote():
    p = plan(_livre(), [10.0, None, 20.0], 1.25)
    assert [f["fichier"] for f in p] == ["01 - Gn 1.1-5 Partie 1.mp3", "02 - Gn 2.1-5 Partie 2.mp3", "03 - Gn 3.1-5 Partie 3.mp3"]
    assert p[0]["duree"] == 8.0 and p[1]["duree"] is None
    assert plan(_livre(120), [1.0] * 120, 1)[0]["fichier"].startswith("001 - ")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg absent")
def test_export_complet(tmp_path: Path):
    from mutagen.easyid3 import EasyID3

    livre, voix = _livre(), "edge:x"
    donnees, cle = tmp_path / "livre", tmp_path / "cle"
    asyncio.run(generer_livre(donnees, livre, voix, VoixBip(tmp_path)))
    etapes = []
    r = exporter(donnees, livre, cle, "texte", 1.25, voix, "Sylvie", progres=lambda f, t, n: etapes.append((f, t)))
    assert r["copies"] == 3 and not r["interrompu"]
    dossier = cle / "Genèse essai"
    fichiers = sorted(p.name for p in dossier.iterdir())
    assert fichiers == ["01 - Gn 1.1-5 Partie 1.mp3", "02 - Gn 2.1-5 Partie 2.mp3", "03 - Gn 3.1-5 Partie 3.mp3"]
    t = EasyID3(str(dossier / fichiers[1]))
    assert t["title"] == ["Gn 2.1-5 Partie : 2?"] and t["tracknumber"] == ["2/3"] and t["album"] == ["Genèse / essai"]
    assert t["artist"] == ["Lecteur · Sylvie"]
    assert duree_mp3(dossier / fichiers[0]) < 1.2  # 1 s de voix + 0,35 s de silence, accéléré 1,25x
    assert etapes[-1] == (3, 3)
    assert not list(dossier.glob("*.partiel"))
