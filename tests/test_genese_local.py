"""Test sur le vrai PDF de Genèse, seulement sur l'ordinateur d'Alexis.

Le PDF n'est jamais dans le dépôt. Pour lancer ce test :
    $env:LECTEUR_GENESE = "C:\\...\\2.Genèse.pdf"; pytest
"""
import os
from pathlib import Path

import pytest

from lecteur.importer import importer_pdf

CHEMIN = os.environ.get("LECTEUR_GENESE", "")
pytestmark = pytest.mark.skipif(not CHEMIN or not Path(CHEMIN).exists(), reason="PDF de Genèse absent (normal sur GitHub)")


@pytest.fixture(scope="module")
def livre():
    l, _ = importer_pdf(Path(CHEMIN), "bible_etude", "15-17,29")
    return l


def test_sections(livre):
    refs = [s.ref for s in livre.sections]
    assert refs == ["Gn 4.11-16", "Gn 4.17-24", "Gn 4.25-26", "Gn 5.1-20", "Gn 5.21-32", "Gn 6.1-8", "Gn 6.9-10",
                    "Gn 14.17-24", "Gn 15.1-9"]


def test_versets_continus(livre):
    vs = [(b.ch, b.v) for s in livre.sections for b in s.blocs if b.genre == "verset"]
    for ch in (5, 15):
        nums = [v for c, v in vs if c == ch]
        assert nums == list(range(1, len(nums) + 1)), f"chapitre {ch} : {nums}"


def test_notes_principales(livre):
    refs = {b.ref for s in livre.sections for b in s.blocs if b.genre == "note"}
    for attendu in ("4.14", "4.15", "4.19-26", "5.1ss", "5.3-5", "5.25-27", "6.1-4", "14.18", "15.1", "15.2-3", "15.8"):
        assert attendu in refs


def test_pas_de_debris(livre):
    texte = " ".join(b.texte for s in livre.sections for b in s.blocs if b.genre == "verset")
    for debris in ("■", "lvVôVo", "*11", " II ", "4.12", "Ot 28"):
        assert debris not in texte
