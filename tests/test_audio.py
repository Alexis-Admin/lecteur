"""Moteur de voix, cache par bloc et minutage raccroché au texte affiché (fausse voix : pas d'Internet)."""
import asyncio
import os
import re
from pathlib import Path

import pytest

from lecteur.audio import audio_du_bloc, etat_audio, generer_livre, menage
from lecteur.minutage import aligner
from lecteur.modele import Bloc, Livre, Section


class FausseVoix:
    """Imite edge-tts : un mot toutes les 0,3 s."""

    def __init__(self):
        self.appels = 0

    async def synthetiser(self, texte, voix):
        self.appels += 1
        mots = [(i * 0.3, 0.25, m) for i, m in enumerate(re.findall(r"[\w’'\-]+", texte))]
        return b"FAUX-MP3", mots


def _livre():
    s = Section("s001", "Essai", blocs=[
        Bloc("b1", "texte", "titre", "Le jardin"),
        Bloc("b2", "texte", "verset", "Voir Gn 4.7 maintenant.", 1, 1),
        Bloc("b3", "notes", "note", "Une note.", 1, 1, ref="1.1"),
        Bloc("b4", "texte", "verset", "סֵפֶר", 1, 2),  # rien de lisible en français : pas d'audio
    ])
    return Livre("essai", "Essai", "bible_etude", "", [1], "Gn", sections=[s])


def test_alignement_reference_lue_au_long():
    affiche = "Voir Gn 4.7 maintenant."
    lu = "Voir Genèse, chapitre 4, verset 7 maintenant."
    mots = [(i * 0.3, 0.25, m) for i, m in enumerate(lu.replace(",", "").replace(".", "").split())]
    res = aligner(affiche, lu, mots)
    zones = [affiche[r["a"]:r["b"]] if r["a"] >= 0 else None for r in res]
    assert zones[0] == "Voir" and zones[-1] == "maintenant"
    assert zones[1] in ("Gn", "Gn 4.7")  # « Genèse » allume la référence affichée
    assert all(r["f"] > r["d"] for r in res)


def test_annonce_orale_sans_surlignage():
    res = aligner("Une note.", "Chapitre 1, verset 1. Une note.",
                  [(0, .2, "Chapitre"), (.3, .2, "1"), (.6, .2, "verset"), (.9, .2, "1"), (1.2, .2, "Une"), (1.5, .2, "note")])
    assert [r["a"] for r in res[:4]] == [-1, -1, -1, -1]
    assert res[4]["a"] == 0 and res[5]["a"] == 4


def test_generation_et_reprise(tmp_path: Path):
    livre, voix, moteur = _livre(), "edge:fr-CA-SylvieNeural", FausseVoix()
    r = asyncio.run(generer_livre(tmp_path, livre, voix, moteur))
    assert r == {"fait": 3, "total": 3, "erreurs": [], "interrompu": False}
    assert moteur.appels == 3
    assert audio_du_bloc(tmp_path, livre, livre.sections[0].blocs[3], voix) is None
    # Relancer ne refait rien (reprise)
    asyncio.run(generer_livre(tmp_path, livre, voix, moteur))
    assert moteur.appels == 3
    # Corriger un bloc : seul ce bloc est refait, l'ancien fichier devient périmé
    livre.sections[0].blocs[1].texte = "Voir Gn 4.8 maintenant."
    assert etat_audio(tmp_path, livre, voix)["fait"] == 2
    asyncio.run(generer_livre(tmp_path, livre, voix, moteur))
    assert moteur.appels == 4
    perimes = menage(tmp_path, livre, voix)
    assert len(perimes) == 2 and all(p.name.startswith("b2-") for p in perimes)


def test_arret_propre(tmp_path: Path):
    livre, moteur = _livre(), FausseVoix()
    r = asyncio.run(generer_livre(tmp_path, livre, "edge:x", moteur, en_parallele=1, arret=lambda: moteur.appels >= 1))
    assert r["interrompu"] and r["fait"] == 1


@pytest.mark.skipif(not os.environ.get("LECTEUR_RESEAU"), reason="Internet : seulement avec LECTEUR_RESEAU=1")
def test_voix_hors_ligne_piper(tmp_path: Path, monkeypatch):
    import json

    from lecteur.voix import MoteurPiper

    monkeypatch.setenv("LECTEUR_DONNEES", str(tmp_path / "donnees"))
    livre = _livre()
    asyncio.run(generer_livre(tmp_path, livre, "piper:fr_FR-siwis-medium", MoteurPiper(), en_parallele=1))
    a = audio_du_bloc(tmp_path, livre, livre.sections[0].blocs[1], "piper:fr_FR-siwis-medium")
    m = json.loads(a.minutage.read_text(encoding="utf-8"))
    assert m["duree"] > 1 and len(m["mots"]) >= 6
    assert m["mots"][-1]["f"] <= m["duree"] + 0.2


@pytest.mark.skipif(not os.environ.get("LECTEUR_RESEAU"), reason="Internet : seulement avec LECTEUR_RESEAU=1")
def test_vraie_voix_sylvie(tmp_path: Path):
    from lecteur.voix import MoteurEdge

    livre = _livre()
    asyncio.run(generer_livre(tmp_path, livre, "edge:fr-CA-SylvieNeural", MoteurEdge()))
    a = audio_du_bloc(tmp_path, livre, livre.sections[0].blocs[1], "edge:fr-CA-SylvieNeural")
    import json

    m = json.loads(a.minutage.read_text(encoding="utf-8"))
    assert m["duree"] > 1 and len(m["mots"]) >= 6
    assert any(r["a"] >= 0 for r in m["mots"])
