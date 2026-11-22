"""Fenêtre de l'application (pywebview) et fonctions appelées par l'interface (ui/)."""
from __future__ import annotations

import asyncio
import base64
import difflib
import json
import os
import re
import shutil
import threading
import time
from pathlib import Path

import pymupdf
import webview

from . import __version__, bibliotheque, douteux, export_usb, serveur_audio
from .assemblage import assembler, duree_section, sections_perimees
from .audio import etat_audio, generer_livre, menage, texte_prononce
from .importer import PROFILS, importer_pdf, lire_pages
from .modele import Livre
from .pdf_mots import mots_de_page
from .ocr_image import langues_disponibles
from .profils import bible_etude, deux_colonnes, simple
from .prononciation import a_lire, bloc_a_lire, etiquette_a_lire
from .texte_brut import lire_page_web, livre_depuis_images, livre_depuis_texte
from .voix import VOIX_PAR_DEFAUT, VOIX_PAR_DEFAUT_EN, langue_de_voix, liste_des_voix, moteur_pour

UI = Path(__file__).resolve().parent.parent / "ui" / "index.html"


class Api:
    def __init__(self) -> None:
        self._fenetre: webview.Window | None = None
        self._verrou = threading.Lock()
        self._verrou_reglages = threading.Lock()
        self._livres: dict[str, Livre] = {}
        self._generation: dict | None = None  # création d'audio en cours
        self._export: dict | None = None  # copie sur clé USB en cours
        self._positions: dict[tuple[str, str], dict] = {}  # vue « Page » : mots d'un bloc sur le scan

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
        self._positions = {k: v for k, v in self._positions.items() if k[0] != livre.id}  # texte changé

    # --- application -------------------------------------------------------
    def infos(self) -> dict:
        return {"version": __version__, "donnees": str(bibliotheque.racine()),
                "profils": [{"id": k, "nom": v[0]} for k, v in PROFILS.items()]}

    def reglages(self) -> dict:
        return bibliotheque.reglages()

    def enregistrer_reglages(self, r: dict) -> bool:
        with self._verrou_reglages:  # lire-modifier-écrire d'un bloc : aucun réglage perdu
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
                    "titre": Path(chemin).stem.lstrip("0123456789. "), "profil_conseille": self._profil_conseille(doc)}

    @staticmethod
    def _profil_conseille(doc) -> str:
        """Bible d'étude si des pages du milieu ont l'en-tête « GENÈSE 4.12 » ; sinon « Livre » (les colonnes et
        les encadrés y sont détectés tout seuls). Le nom du fichier ne suffit pas (« All the Genealogies of the bible »)."""
        n = len(doc)
        echantillon = sorted({max(0, min(n - 1, int(n * f))) for f in (0.3, 0.45, 0.6, 0.75)})
        bible = 0
        for i in echantillon:
            try:
                if bible_etude.analyser_page(doc[i], i + 1).entete_livre:
                    bible += 1
            except Exception:  # noqa: BLE001 - page illisible : on l'ignore
                pass
        return bible_etude.NOM if bible >= 2 else simple.NOM

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
        meta = {"type": "pdf", "titre": livre.titre, "profil": profil, "chemin_source": str(chemin), "nb_pages": nb,
                "pages": pages, "nb_sections": len(livre.sections), "importe_le": time.strftime("%Y-%m-%d %H:%M")}
        bibliotheque.enregistrer(livre, meta)
        self._livres[livre_id] = livre
        return {"id": livre_id}

    # --- captures d'écran, texte collé, page web ---------------------------
    def ocr_disponible(self) -> bool:
        return any(l.lower().startswith("fr") for l in langues_disponibles())

    def choisir_images(self) -> list[dict]:
        r = self._fenetre.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True,
                                             file_types=("Images (*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.tif;*.tiff;*.webp)",))
        return [{"chemin": c, "nom": Path(c).name} for c in sorted(r or [])]

    def importer_images(self, sources: list[dict], profil: str, titre: str) -> dict:
        """sources : [{"chemin": …}] ou [{"donnees": "data:image/png;base64,…", "nom": …}] (capture collée)."""
        if not sources:
            raise ValueError("Ajoute au moins une image.")
        titre = titre.strip() or "Captures du " + time.strftime("%Y-%m-%d")
        livre_id = bibliotheque.nouvel_id(titre)
        dossier = bibliotheque.chemin_livre(livre_id).parent / "images"
        dossier.mkdir(parents=True, exist_ok=True)
        chemins: list[Path] = []
        for i, s in enumerate(sources, 1):
            if s.get("donnees"):
                entete, _, b64 = s["donnees"].partition(",")
                ext = ".jpg" if "jpeg" in entete else ".png"
                cible = dossier / f"{i:03d}{ext}"
                cible.write_bytes(base64.b64decode(b64))
            else:
                src = Path(s["chemin"])
                cible = dossier / f"{i:03d}{src.suffix.lower()}"
                shutil.copy2(src, cible)  # copie : l'original n'est jamais touché
            chemins.append(cible)
        debut = time.time()

        def progres(i: int, n: int) -> None:
            self._js(f"window.progresImport && progresImport({i}, {n}, {time.time() - debut:.1f})")

        nb_col = 2 if profil == deux_colonnes.NOM else 1
        livre, analyses = livre_depuis_images(chemins, nb_col, titre, bibliotheque.corrections().get("apprises"),
                                              livre_id, progres)
        livre.source = f"{len(chemins)} capture(s)"
        bibliotheque.ecrire_json(dossier.parent / "zones.json", {str(a["numero"]): a for a in analyses})
        return self._enregistrer_nouveau(livre, {"type": "images", "profil": profil, "nb_pages": len(chemins),
                                                 "images": [c.name for c in chemins]})

    def importer_texte(self, texte: str, titre: str) -> dict:
        titre = titre.strip() or (texte.strip().splitlines() or ["Texte"])[0][:60]
        livre_id = bibliotheque.nouvel_id(titre)
        livre = livre_depuis_texte(texte, titre, bibliotheque.corrections().get("apprises"), livre_id)
        livre.source = "texte collé"
        return self._enregistrer_nouveau(livre, {"type": "texte", "profil": "texte", "nb_pages": 0})

    def importer_url(self, url: str, titre: str) -> dict:
        titre_page, texte = lire_page_web(url)
        titre = titre.strip() or titre_page
        livre_id = bibliotheque.nouvel_id(titre)
        livre = livre_depuis_texte(texte, titre, bibliotheque.corrections().get("apprises"), livre_id,
                                   profil="web", markdown=True)
        livre.source = url
        return self._enregistrer_nouveau(livre, {"type": "web", "profil": "web", "url": url, "nb_pages": 0})

    def _enregistrer_nouveau(self, livre: Livre, meta: dict) -> dict:
        meta.update({"titre": livre.titre, "nb_sections": len(livre.sections), "importe_le": time.strftime("%Y-%m-%d %H:%M")})
        bibliotheque.enregistrer(livre, meta)
        self._livres[livre.id] = livre
        return {"id": livre.id}

    def livre(self, livre_id: str) -> dict:
        livre = self._livre(livre_id)
        d = livre.vers_dict()
        d["meta"] = bibliotheque.meta(livre_id)
        return d

    def douteux(self, livre_id: str) -> list[dict]:
        ign = set(bibliotheque.corrections().get("ignores", []))
        # Page web ou livre anglais : pas de vérification par le dictionnaire français, seulement les vrais accidents.
        sans_ocr = bibliotheque.meta(livre_id).get("type") == "web" or self._langue(livre_id) == "en"
        return douteux.analyser(self._livre(livre_id), ign, sans_ocr=sans_ocr)

    def page(self, livre_id: str, numero: int, largeur: int = 900) -> dict:
        """Image de la page scannée et zones détectées (pour l'aperçu)."""
        m = bibliotheque.meta(livre_id)
        if m.get("type") == "images":
            dossier = bibliotheque.chemin_livre(livre_id).parent
            nom = m.get("images", [])[numero - 1]
            fichier = dossier / "images" / nom
            if not fichier.exists():
                return {"erreur": "Image introuvable."}
            ext = fichier.suffix.lower().lstrip(".").replace("jpg", "jpeg")
            image = f"data:image/{ext};base64," + base64.b64encode(fichier.read_bytes()).decode()
            z = bibliotheque.lire_json(dossier / "zones.json", {}).get(str(numero), {})
            return {"image": image, "largeur": z.get("largeur", 1), "hauteur": z.get("hauteur", 1), "zones": z.get("zones", [])}
        if m.get("type") in ("texte", "web"):
            return {"sans_page": True, "source": m.get("url") or "Texte collé"}
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

    def position_mot(self, livre_id: str, numero: int, mot: str) -> dict:
        """Où se trouve un mot sur la page scannée (pour l'encadrer en jaune dans l'aperçu)."""
        m = bibliotheque.meta(livre_id)
        chemin = m.get("chemin_source", "")
        if m.get("type") in ("images", "texte", "web") or not chemin or not Path(chemin).exists() or not mot:
            return {"rects": []}
        with pymupdf.open(chemin) as doc:
            if not 1 <= numero <= len(doc):
                return {"rects": []}
            page = doc[numero - 1]
            # Les mots tels que l'app les lit sur la page : un mot du texte peut venir de 1 à 3 morceaux du scan
            # (« de » + « facto » → « defacto »), et le scan peut contenir des signes en plus (« *11 »).
            def norme(t: str) -> str:
                return re.sub(r"[^\wÀ-ÿ]", "", t).lower()

            cible = norme(mot)
            mots = [m for m in mots_de_page(page, numero) if m.texte.strip()]
            rects = []
            if cible:
                for i in range(len(mots)):
                    concat = ""
                    for k in range(i, min(i + 3, len(mots))):
                        concat += norme(mots[k].texte)
                        if concat == cible or (k == i and cible in concat and len(cible) >= 4):
                            groupe = mots[i:k + 1]
                            rects.append([min(m.x0 for m in groupe), min(m.y0 for m in groupe),
                                          max(m.x1 for m in groupe), max(m.y1 for m in groupe)])
                            break
                        if not cible.startswith(concat):
                            break
            return {"largeur": page.rect.width, "hauteur": page.rect.height, "rects": rects[:6]}

    def positions_bloc(self, livre_id: str, bloc_id: str) -> dict:
        """Où se trouve chaque mot d'un bloc sur le scan (vue « Page » : le mot lu y est encadré).

        Les mots du bloc sont alignés sur ceux de sa page (et de la suivante, s'il continue) : un mot corrigé
        ou recollé prend la place de son voisin le plus proche. {"pages": {n: [L, H]}, "mots": [{a, b, p, r}]}
        """
        cle = (livre_id, bloc_id)
        if cle in self._positions:
            return self._positions[cle]
        m = bibliotheque.meta(livre_id)
        livre = self._livre(livre_id)
        b = livre.bloc(bloc_id)
        chemin = m.get("chemin_source", "")
        res: dict = {"pages": {}, "mots": []}
        if b is None or not b.page or m.get("type", "pdf") != "pdf" or not chemin or not Path(chemin).exists():
            return res

        def norme(t: str) -> str:
            return re.sub(r"[^\wÀ-ÿ]", "", t).lower()

        jetons = [(x.start(), x.end(), norme(x.group(0))) for x in re.finditer(r"[\wÀ-ÿ’'\-]+", b.texte)]
        mots_page: list[tuple[str, int, list[float]]] = []
        with pymupdf.open(chemin) as doc:
            for p in (b.page, b.page + 1):
                if 1 <= p <= len(doc):
                    page = doc[p - 1]
                    res["pages"][p] = [page.rect.width, page.rect.height]
                    for w in mots_de_page(page, p):
                        if w.texte.strip():
                            mots_page.append((norme(w.texte), p, [w.x0, w.y0, w.x1, w.y1]))
        if not jetons or not mots_page:
            return res
        sm = difflib.SequenceMatcher(None, [j[2] for j in jetons], [w[0] for w in mots_page], autojunk=False)
        trouve: dict[int, int] = {}
        for bloc_m in sm.get_matching_blocks():
            for k in range(bloc_m.size):
                trouve[bloc_m.a + k] = bloc_m.b + k
        precedent = None
        for i, (a, z, _) in enumerate(jetons):
            j = trouve.get(i, precedent)
            if j is None:
                j = next((trouve[k] for k in range(i, len(jetons)) if k in trouve), None)
            if j is None:
                continue
            precedent = j
            _, p, r = mots_page[j]
            res["mots"].append({"a": a, "b": z, "p": p, "r": r, "exact": i in trouve})
        if len(self._positions) > 400:
            self._positions.clear()
        self._positions[cle] = res
        return res

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

    def remplacer_plusieurs(self, livre_id: str, paires: list, retenir: bool) -> int:
        """Changements sûrs cochés dans l'aperçu : tout appliquer en une fois."""
        livre = self._livre(livre_id)
        paires = [(str(a), str(b)) for a, b in paires]
        n = douteux.remplacer_plusieurs(livre, paires)
        if n:
            self._sauver(livre)
        if retenir:
            c = bibliotheque.corrections()
            for a, b in paires:
                if a != b:
                    c.setdefault("apprises", {})[a] = b
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
        return [texte_prononce(livre, b) if (b := livre.bloc(i)) else "" for i in bloc_ids]

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

    # --- audio (phase 2) ------------------------------------------------------
    def _voix(self, livre_id: str | None = None) -> str:
        """Voix du livre : la voix anglaise choisie pour un livre en anglais, sinon la voix française."""
        r = bibliotheque.reglages()
        if livre_id and self._langue(livre_id) == "en":
            return r.get("voix_en") or VOIX_PAR_DEFAUT_EN
        return r.get("voix") or VOIX_PAR_DEFAUT

    def _langue(self, livre_id: str) -> str:
        try:
            return getattr(self._livre(livre_id), "langue", "fr") or "fr"
        except Exception:  # noqa: BLE001
            return "fr"

    def _dossier(self, livre_id: str) -> Path:
        return bibliotheque.chemin_livre(livre_id).parent

    def voix(self, livre_id: str = "") -> dict:
        """Voix proposées pour ce livre (selon sa langue) et celle qui est choisie."""
        langue = self._langue(livre_id) if livre_id else "fr"
        liste = [v for v in liste_des_voix() if langue_de_voix(v.id) == langue]
        return {"choisie": self._voix(livre_id or None), "langue": langue, "voix": [v.__dict__ for v in liste]}

    def choisir_voix(self, voix_id: str) -> bool:
        if voix_id not in {v.id for v in liste_des_voix()}:
            return False
        self.enregistrer_reglages({"voix_en" if langue_de_voix(voix_id) == "en" else "voix": voix_id})
        return True

    def extrait_voix(self, voix_id: str) -> str:
        """Court extrait pour choisir la voix (gardé dans Documents\\Lecteur\\extraits)."""
        f = bibliotheque.racine() / "extraits" / (voix_id.replace(":", "-") + ".mp3")
        if not f.exists():
            nom = next((v.nom for v in liste_des_voix() if v.id == voix_id), "")
            texte = (f"Hello, I am {nom.split(' (')[0]}. This is how I will read your English books: "
                     "In the beginning, God created the heavens and the earth.") if langue_de_voix(voix_id) == "en" else (
                     f"Bonjour, je suis {nom}. Voici comment je lirai tes livres : "
                     "Genèse, chapitre 1, verset 1. Au commencement, Dieu créa le ciel et la terre.")
            mp3, _ = asyncio.run(moteur_pour(voix_id).synthetiser(texte, voix_id))
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(mp3)
        return "data:audio/mpeg;base64," + base64.b64encode(f.read_bytes()).decode()

    def etat_audio(self, livre_id: str) -> dict:
        e = etat_audio(self._dossier(livre_id), self._livre(livre_id), self._voix(livre_id))
        g = self._generation
        e["en_cours"] = bool(g and g["livre"] == livre_id and g["en_cours"])
        e["autre_en_cours"] = bool(g and g["livre"] != livre_id and g["en_cours"])
        e["erreurs"] = g["erreurs"] if g and g["livre"] == livre_id else []
        e["voix"] = self._voix(livre_id)
        return e

    def generer_audio(self, livre_id: str, depuis_section: str = "") -> dict:
        """Lance la création de l'audio en arrière-plan (un livre à la fois). L'interface suit avec etat_audio.

        La section ouverte passe en premier : on peut l'écouter au bout d'une minute au lieu d'attendre tout le livre.
        """
        if self._generation and self._generation["en_cours"]:
            return {"deja": self._generation["livre"]}
        livre, voix, dossier = self._livre(livre_id), self._voix(livre_id), self._dossier(livre_id)
        g = {"livre": livre_id, "en_cours": True, "arret": False, "erreurs": []}
        self._generation = g

        def travail():
            try:
                r = asyncio.run(generer_livre(dossier, livre, voix, moteur_pour(voix), en_parallele=3,
                                              arret=lambda: g["arret"], premiere=depuis_section or None))
                g["erreurs"] = r["erreurs"]
            except Exception as e:  # noqa: BLE001
                g["erreurs"] = [str(e)]
            finally:
                g["en_cours"] = False

        threading.Thread(target=travail, daemon=True).start()
        return {"lance": livre_id}

    def arreter_audio(self) -> bool:
        if self._generation:
            self._generation["arret"] = True
        return True

    def audio_section(self, livre_id: str, section_id: str, mode: str) -> dict:
        """MP3 assemblé de la section (blocs + silences) et minutage de tous les mots."""
        livre = self._livre(livre_id)
        s = next((x for x in livre.sections if x.id == section_id), None)
        if s is None:
            return {"erreur": "Section introuvable."}
        r = assembler(self._dossier(livre_id), livre, s, mode, self._voix(livre_id))
        if r is None:
            return {"pas_pret": True}
        return {"url": serveur_audio.adresse(r["mp3"]), "duree": r["duree"],
                "minutage": json.loads(r["minutage"].read_text(encoding="utf-8"))}

    def preparer_section(self, livre_id: str, section_id: str, mode: str) -> bool:
        """Assemble une section en arrière-plan (la suivante, pendant qu'on écoute) : passage sans attente."""
        def travail():
            try:
                livre = self._livre(livre_id)
                s = next((x for x in livre.sections if x.id == section_id), None)
                if s is not None:
                    assembler(self._dossier(livre_id), livre, s, mode, self._voix(livre_id))
            except Exception:  # noqa: BLE001 - sera refait (avec le message d'erreur) au moment de l'écouter
                pass
        threading.Thread(target=travail, daemon=True).start()
        return True

    # --- réglages (phase 4) --------------------------------------------------
    def _fichiers_perimes(self) -> list[Path]:
        """Audio qui ne sert plus, dans tous les livres : blocs et sections refaits, restes d'export."""
        res = []
        for info in bibliotheque.liste():
            try:
                livre, dossier = self._livre(info["id"]), self._dossier(info["id"])
            except Exception:  # noqa: BLE001 - livre illisible : on n'y touche pas
                continue
            voix = self._voix(info["id"])
            res += menage(dossier, livre, voix) + sections_perimees(dossier, livre, voix)
            export = dossier / "audio" / "export"
            if export.exists():
                res += [f for f in export.iterdir() if f.is_file()]
        return res

    def infos_reglages(self) -> dict:
        perimes = self._fichiers_perimes()
        c = bibliotheque.corrections()
        return {"version": __version__, "donnees": str(bibliotheque.racine()),
                "apprises": c.get("apprises", {}), "ignores": c.get("ignores", []),
                "menage": {"fichiers": len(perimes), "octets": sum(f.stat().st_size for f in perimes if f.exists())}}

    def oublier(self, apprise: str, ignore: str) -> bool:
        """Retire une correction retenue ou un mot gardé (Réglages). Ne touche pas aux livres déjà importés."""
        c = bibliotheque.corrections()
        if apprise:
            c.get("apprises", {}).pop(apprise, None)
        if ignore:
            c["ignores"] = [m for m in c.get("ignores", []) if m != ignore]
        bibliotheque.ecrire_corrections(c)
        return True

    def faire_menage(self) -> dict:
        """Met l'audio périmé à la corbeille Windows (récupérable)."""
        from send2trash import send2trash

        perimes = [f for f in self._fichiers_perimes() if f.exists()]
        octets = sum(f.stat().st_size for f in perimes)
        if perimes:
            send2trash([str(f) for f in perimes])
        return {"fichiers": len(perimes), "octets": octets}

    def ouvrir_donnees(self) -> bool:
        return self.ouvrir_dossier(str(bibliotheque.racine()))

    def durees_sections(self, livre_id: str, mode: str) -> list[float | None]:
        """Durée de chaque section (None si son audio n'est pas encore créé) : progression et temps restant."""
        livre = self._livre(livre_id)
        return [duree_section(self._dossier(livre_id), livre, s, mode, self._voix(livre_id)) for s in livre.sections]

    # --- export clé USB (phase 2.4) -------------------------------------------
    def cles_usb(self) -> list[dict]:
        return export_usb.cles_usb()

    def choisir_dossier(self) -> str | None:
        r = self._fenetre.create_file_dialog(webview.FOLDER_DIALOG)
        return (r[0] if isinstance(r, (list, tuple)) else r) if r else None

    def plan_export(self, livre_id: str, mode: str, vitesse: float) -> dict:
        livre, voix, dossier = self._livre(livre_id), self._voix(livre_id), self._dossier(livre_id)
        durees = [duree_section(dossier, livre, s, mode, voix) for s in livre.sections]
        fichiers = export_usb.plan(livre, durees, vitesse)
        prets = [f for f in fichiers if f["duree"]]
        duree = sum(f["duree"] for f in prets)
        return {"fichiers": fichiers, "prets": len(prets), "total": len(fichiers), "duree": duree,
                "octets": int(duree * 6000) + 4096 * len(prets),  # 48 kbit/s = 6 000 octets/s
                "dossier": export_usb.nom_fichier(livre.titre, 60), "cles": export_usb.cles_usb()}

    def exporter_usb(self, livre_id: str, destination: str, mode: str, vitesse: float) -> dict:
        if self._export and self._export["en_cours"]:
            return {"deja": True}
        livre, voix, dossier = self._livre(livre_id), self._voix(livre_id), self._dossier(livre_id)
        nom_voix = next((v.nom for v in liste_des_voix() if v.id == voix), "")
        x = {"en_cours": True, "arret": False, "fait": 0, "total": 0, "fichier": "", "resultat": None, "erreur": None}
        self._export = x
        self.enregistrer_reglages({"export": {"mode": mode, "vitesse": vitesse}})

        def progres(fait, total, fichier):
            x.update(fait=fait, total=total, fichier=fichier)

        def travail():
            try:
                x["resultat"] = export_usb.exporter(dossier, livre, Path(destination), mode, vitesse, voix, nom_voix,
                                                    progres, lambda: x["arret"])
            except Exception as e:  # noqa: BLE001 - clé retirée, pleine…
                x["erreur"] = f"La copie s'est arrêtée : {e}"
            finally:
                x["en_cours"] = False

        threading.Thread(target=travail, daemon=True).start()
        return {"lance": True}

    def etat_export(self) -> dict:
        x = self._export or {}
        return {k: v for k, v in x.items() if k != "arret"}

    def arreter_export(self) -> bool:
        if self._export:
            self._export["arret"] = True
        return True

    def ejecter_cle(self, lettre: str) -> bool:
        return export_usb.ejecter(lettre)

    def ouvrir_dossier(self, chemin: str) -> bool:
        p = Path(chemin)
        if p.exists() and p.is_dir():
            os.startfile(str(p))  # noqa: S606 - ouvre l'Explorateur sur le dossier exporté
            return True
        return False


def identite_windows() -> None:
    """Identité propre à Lecteur dans la barre des tâches (sinon Windows le regroupe avec « Python »)."""
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Alexis.Lecteur")
    except Exception:  # noqa: BLE001 - autre système que Windows
        pass


def appliquer_icone(titre: str) -> None:
    """Met l'icône de Lecteur sur la fenêtre et dans la barre des tâches (pywebview garde celle de Python)."""
    try:
        import ctypes

        from .icone import chemin_icone

        from ctypes import wintypes

        u = ctypes.windll.user32
        # Types 64 bits explicites : sinon les poignées sont tronquées et rien ne s'affiche.
        u.FindWindowW.restype = wintypes.HWND
        u.LoadImageW.restype = wintypes.HANDLE
        u.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        hwnd = u.FindWindowW(None, titre)
        if not hwnd:
            return
        f = str(chemin_icone())
        for taille, quel in ((32, 1), (16, 0)):  # ICON_BIG = 1, ICON_SMALL = 0
            h = u.LoadImageW(None, f, 1, taille, taille, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
            if h:
                u.SendMessageW(hwnd, 0x80, quel, h)  # WM_SETICON
    except Exception:  # noqa: BLE001 - l'icône est un plus, jamais une raison de ne pas démarrer
        pass


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
    fen.events.shown += lambda: appliquer_icone("Lecteur")
    identite_windows()
    webview.start(debug=bool(json.loads(str(r.get("debug", "false")).lower())), private_mode=False,
                  storage_path=str(bibliotheque.racine() / "webview"))
