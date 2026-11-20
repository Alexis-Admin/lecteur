"""Fenêtre de l'application (pywebview) et fonctions appelées par l'interface (ui/)."""
from __future__ import annotations

import base64
import json
import threading
import time
from pathlib import Path

import pymupdf
import webview

from . import __version__, bibliotheque, douteux
from .importer import PROFILS, importer_pdf, lire_pages
from .modele import Livre
from .profils import bible_etude, deux_colonnes, simple
from .prononciation import a_lire, bloc_a_lire, etiquette_a_lire

UI = Path(__file__).resolve().parent.parent / "ui" / "index.html"


class Api:
    def __init__(self) -> None:
        self._fenetre: webview.Window | None = None
        self._verrou = threading.Lock()
        self._livres: dict[str, Livre] = {}

    # --- utilitaires -------------------------------------------------------
    def _js(self, code: str) -> None:
        if self._fenetre:
            try:
                self._fenetre.evaluate_js(code)
            except Exception:  # noqa: BLE001 - la fenêtre peut être en train de se fermer
                pass

    def _livre(self, livre_id: str) -> Livre:
        if livre_id not in self._livres:
            self._livres[livre_id] = bibliotheque.ouvrir(livre_id)
        return self._livres[livre_id]

    def _sauver(self, livre: Livre) -> None:
        with self._verrou:
            bibliotheque.enregistrer(livre)

    # --- application -------------------------------------------------------
    def infos(self) -> dict:
        return {"version": __version__, "donnees": str(bibliotheque.racine()),
                "profils": [{"id": k, "nom": v[0]} for k, v in PROFILS.items()]}

    def reglages(self) -> dict:
        return bibliotheque.reglages()

    def enregistrer_reglages(self, r: dict) -> bool:
        actuels = bibliotheque.reglages()
        actuels.update(r or {})
        bibliotheque.ecrire_reglages(actuels)
        return True

    # --- bibliothèque --------------------------------------------------------
    def liste_livres(self) -> list[dict]:
        return bibliotheque.liste()

    def choisir_pdf(self) -> dict | None:
        r = self._fenetre.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False,
                                            file_types=("PDF (*.pdf)", "Tous les fichiers (*.*)"))
        if not r:
            return None
        return self.infos_pdf(r[0] if isinstance(r, (list, tuple)) else r)

    def infos_pdf(self, chemin: str) -> dict:
        with pymupdf.open(chemin) as doc:
            texte = "".join(doc[i].get_text()[:400] for i in range(min(3, len(doc))))
            return {"chemin": chemin, "nom": Path(chemin).name, "pages": len(doc), "a_du_texte": bool(texte.strip()),
                    "titre": Path(chemin).stem.lstrip("0123456789. ")}

    def importer(self, chemin: str, profil: str, pages: str, titre: str) -> dict:
        corr = bibliotheque.corrections()
        livre_id = bibliotheque.nouvel_id(titre or Path(chemin).stem)
        debut = time.time()

        def progres(i: int, n: int) -> None:
            if i == n or i % 5 == 0:
                self._js(f"window.progresImport && progresImport({i}, {n}, {time.time() - debut:.1f})")

        livre, _ = importer_pdf(Path(chemin), profil, pages, titre or None, corr.get("apprises"), livre_id, progres)
        livre.id = livre_id
        if titre:
            livre.titre = titre
        with pymupdf.open(chemin) as doc:
            nb = len(lire_pages(pages, len(doc)))
        meta = {"titre": livre.titre, "profil": profil, "chemin_source": str(chemin), "nb_pages": nb,
                "pages": pages, "nb_sections": len(livre.sections), "importe_le": time.strftime("%Y-%m-%d %H:%M")}
        bibliotheque.enregistrer(livre, meta)
        self._livres[livre_id] = livre
        return {"id": livre_id}

    def livre(self, livre_id: str) -> dict:
        livre = self._livre(livre_id)
        d = livre.vers_dict()
        d["meta"] = bibliotheque.meta(livre_id)
        return d

    def douteux(self, livre_id: str) -> list[dict]:
        ign = set(bibliotheque.corrections().get("ignores", []))
        return douteux.analyser(self._livre(livre_id), ign)

    def page(self, livre_id: str, numero: int, largeur: int = 900) -> dict:
        """Image de la page scannée et zones détectées (pour l'aperçu)."""
        m = bibliotheque.meta(livre_id)
        chemin = m.get("chemin_source", "")
        if not chemin or not Path(chemin).exists():
            return {"erreur": "Le PDF d'origine a été déplacé ou renommé."}
        with pymupdf.open(chemin) as doc:
            page = doc[numero - 1]
            zoom = largeur / page.rect.width
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            image = "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode()
            profil = m.get("profil")
            if profil == bible_etude.NOM:
                zones = bible_etude.analyser_page(page, numero).zones
            elif profil == deux_colonnes.NOM:
                zones = deux_colonnes.zones_page(page, numero)
            else:
                zones = simple.zones_page(page, numero)
            return {"image": image, "largeur": page.rect.width, "hauteur": page.rect.height, "zones": zones}

    def modifier_bloc(self, livre_id: str, bloc_id: str, texte: str) -> bool:
        livre = self._livre(livre_id)
        b = livre.bloc(bloc_id)
        if b is None or b.texte == texte.strip():
            return False
        b.texte = texte.strip()
        for s in livre.sections:
            if b in s.blocs and b.genre == "titre":
                s.titre = b.texte
        self._sauver(livre)
        return True

    def remplacer(self, livre_id: str, avant: str, apres: str, retenir: bool) -> int:
        livre = self._livre(livre_id)
        n = douteux.remplacer_partout(livre, avant, apres)
        if n:
            self._sauver(livre)
        if retenir and avant != apres:
            c = bibliotheque.corrections()
            c.setdefault("apprises", {})[avant] = apres
            bibliotheque.ecrire_corrections(c)
        return n

    def ignorer(self, mot: str) -> bool:
        c = bibliotheque.corrections()
        ign = set(c.get("ignores", []))
        ign.add(mot.lower())
        c["ignores"] = sorted(ign)
        bibliotheque.ecrire_corrections(c)
        return True

    def prononciation(self, texte: str, refs_nues: bool = False, etiquette: str = "") -> str:
        prefixe = etiquette_a_lire(etiquette) + ". " if etiquette else ""
        return prefixe + a_lire(texte, refs_nues)

    def blocs_lus(self, livre_id: str, bloc_ids: list[str]) -> list[str]:
        """Texte tel qu'il sera prononcé, pour chaque bloc demandé."""
        livre = self._livre(livre_id)
        return [bloc_a_lire(b, livre.refs_nues) if (b := livre.bloc(i)) else "" for i in bloc_ids]

    def renommer(self, livre_id: str, titre: str) -> bool:
        livre = self._livre(livre_id)
        livre.titre = titre.strip() or livre.titre
        m = bibliotheque.meta(livre_id)
        m["titre"] = livre.titre
        bibliotheque.enregistrer(livre, m)
        return True

    def supprimer(self, livre_id: str) -> bool:
        """Vers la corbeille Windows (récupérable). Le PDF d'origine n'est jamais touché."""
        from send2trash import send2trash

        dossier = bibliotheque.chemin_livre(livre_id).parent
        self._livres.pop(livre_id, None)
        send2trash(str(dossier))
        return True


def lancer() -> None:
    api = Api()
    r = bibliotheque.reglages()
    fen = webview.create_window(
        "Lecteur", str(UI), js_api=api, width=r.get("largeur", 1280), height=r.get("hauteur", 820),
        x=r.get("x"), y=r.get("y"), min_size=(900, 600), background_color="#F4F1EA", text_select=True,
    )
    api._fenetre = fen

    def fermeture():
        try:
            bibliotheque.ecrire_reglages({**bibliotheque.reglages(), "largeur": fen.width, "hauteur": fen.height,
                                         "x": fen.x, "y": fen.y})
        except Exception:  # noqa: BLE001
            pass

    fen.events.closing += fermeture
    webview.start(debug=bool(json.loads(str(r.get("debug", "false")).lower())), private_mode=False,
                  storage_path=str(bibliotheque.racine() / "webview"))
