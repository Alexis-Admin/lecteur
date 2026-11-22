"""Essai automatique dans la VRAIE fenêtre (pywebview), avec un dossier de données de test.

    set LECTEUR_DONNEES=<dossier de test>
    .venv\\Scripts\\python.exe -m outils.essai_fenetre <scenario.js> [sortie.json]

Le scénario est un fichier JS (corps d'une fonction async) qui a accès à toute l'interface ; ce qu'il retourne,
plus les erreurs JavaScript attrapées, est écrit dans sortie.json, puis la fenêtre se ferme.
Sert à trouver les bogues qui n'arrivent que dans l'app (pont pywebview, boîtes de dialogue…).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import webview

from lecteur import app as appli
from lecteur import bibliotheque


class ApiEssai(appli.Api):
    def fin_essai(self, resultat) -> bool:
        self._resultat = resultat
        threading.Thread(target=lambda: (time.sleep(0.3), self._fenetre.destroy()), daemon=True).start()
        return True

    def repondre_dialogue(self, chemin: str) -> bool:
        """Remplit la prochaine boîte « Ouvrir » de Windows avec ce chemin et clique sur Ouvrir (comme Alexis)."""
        def travail():
            import ctypes
            from ctypes import wintypes

            u = ctypes.WinDLL("user32", use_last_error=True)
            u.FindWindowW.restype = wintypes.HWND
            u.FindWindowExW.restype = wintypes.HWND
            u.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
            u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR]
            u.GetDlgItem.restype = wintypes.HWND
            u.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
            for _ in range(100):
                dlg = u.FindWindowW("#32770", None)
                if dlg:
                    time.sleep(0.8)
                    combo = u.FindWindowExW(dlg, None, "ComboBoxEx32", None)
                    champ = u.FindWindowExW(u.FindWindowExW(combo, None, "ComboBox", None), None, "Edit", None) if combo else None
                    if champ:
                        u.SendMessageW(champ, 0x000C, 0, chemin)  # WM_SETTEXT
                        time.sleep(0.3)
                        lu = ctypes.create_unicode_buffer(600)
                        u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
                        u.GetWindowTextW(champ, lu, 600)
                        u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
                        u.PostMessageW(dlg, 0x0111, 1, 0)  # WM_COMMAND IDOK : « Ouvrir »
                        time.sleep(1.0)
                        self._dialogue = f"rempli ({lu.value[-20:]}), encore ouverte: {bool(u.FindWindowW('#32770', None))}"
                    else:
                        self._dialogue = "champ introuvable"
                    return
                time.sleep(0.1)
            self._dialogue = "aucune boîte ouverte"

        self._dialogue = None
        threading.Thread(target=travail, daemon=True).start()
        return True

    def etat_dialogue(self):
        return self._dialogue


def main() -> None:
    if not os.environ.get("LECTEUR_DONNEES"):
        sys.exit("Définis LECTEUR_DONNEES (dossier de test) : jamais les vraies données.")
    scenario = Path(sys.argv[1]).read_text(encoding="utf-8")
    sortie = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("essai-fenetre.json")
    api = ApiEssai()
    api._resultat = None
    fen = webview.create_window("Lecteur (essai)", str(appli.UI), js_api=api, width=1280, height=820)
    api._fenetre = fen

    def lancer_scenario():
        time.sleep(2.5)
        code = ("window.__erreurs = []; window.addEventListener('error', (e) => __erreurs.push(e.message + ' @' + e.lineno));"
                "window.addEventListener('unhandledrejection', (e) => __erreurs.push(String(e.reason && (e.reason.stack || e.reason.message) || e.reason)));"
                "(async () => { let r; try { r = await (async () => {" + scenario + "})(); } catch (e) { r = 'EXCEPTION ' + (e.stack || e); }"
                " await pywebview.api.fin_essai({ resultat: r, erreurs: window.__erreurs }); })();")
        fen.evaluate_js(code)

    fen.events.loaded += lambda: threading.Thread(target=lancer_scenario, daemon=True).start()
    # Comme la vraie app : icône et identité Windows (un bogue de la 1.2.0 venait de là).
    fen.events.shown += lambda: appli.appliquer_icone("Lecteur (essai)")
    appli.identite_windows()
    threading.Timer(240, lambda: fen.destroy()).start()  # sécurité
    webview.start(private_mode=True, storage_path=str(bibliotheque.racine() / "webview"))
    sortie.write_text(json.dumps(api._resultat, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(api._resultat, ensure_ascii=False)[:3000])
    os._exit(0)


if __name__ == "__main__":
    main()
