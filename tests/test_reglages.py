"""Réglages enregistrés en même temps par plusieurs appels de l'interface : aucun ne doit se perdre."""
import threading


def test_reglages_simultanes(tmp_path, monkeypatch):
    monkeypatch.setenv("LECTEUR_DONNEES", str(tmp_path))
    from lecteur.app import Api

    api = Api()
    fils = [threading.Thread(target=api.enregistrer_reglages, args=({f"cle{i}": i},)) for i in range(40)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    r = api.reglages()
    assert all(r.get(f"cle{i}") == i for i in range(40))
    assert not list(tmp_path.glob("*.tmp"))
