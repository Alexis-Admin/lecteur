from pathlib import Path

from outils.verrou import ressemble_a_un_livre, verifier


def test_types_interdits(tmp_path: Path):
    assert verifier(["livre.pdf"])
    assert verifier(["audio/01 - Gn 1.mp3"])
    assert verifier(["capture.png"])
    assert verifier(["bibliotheque/genese/livre.json"])
    assert not verifier(["requirements.txt"])
    assert not verifier(["ui/polices/Inter-latin.woff2"])  # polices incluses : permises
    assert verifier(["ailleurs/police.woff2"])


def test_extrait_de_livre():
    # Construit à la volée pour que ce fichier lui-même ne soit pas refusé par le verrou.
    assert ressemble_a_un_livre(" ".join(f"{i} Mot" for i in range(1, 8)))
    assert not ressemble_a_un_livre("Il a 930 ans et 2 fils.")
