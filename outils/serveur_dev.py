"""Serveur de développement : ouvre l'interface dans un navigateur (http://localhost:8765) avec la vraie API Python.

Sert seulement à tester l'interface pendant le développement (sans fenêtre pywebview).
Utilise un dossier de données à part (variable LECTEUR_DONNEES) pour ne jamais toucher aux vraies données.

    $env:LECTEUR_DONNEES = "…\\donnees-dev"; $env:LECTEUR_DEV_PDF = "…\\fichier.pdf"
    .venv\\Scripts\\python.exe -m outils.serveur_dev
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if not os.environ.get("LECTEUR_DONNEES"):
    sys.exit("Définis LECTEUR_DONNEES (dossier de données de test) avant de lancer le serveur de développement.")

from lecteur.app import Api  # noqa: E402

UI = Path(__file__).resolve().parent.parent / "ui"
PONT = """
window.pywebview = { api: new Proxy({}, { get: (_, nom) => (...args) =>
  fetch('/api/' + nom, { method: 'POST', body: JSON.stringify(args) })
    .then(r => r.ok ? r.json() : r.text().then(t => Promise.reject(new Error(t)))) }) };
setTimeout(() => window.dispatchEvent(new Event('pywebviewready')), 0);
"""


class ApiDev(Api):
    def choisir_pdf(self):
        chemin = os.environ.get("LECTEUR_DEV_PDF")
        return self.infos_pdf(chemin) if chemin else None

    def choisir_images(self):
        chemins = [c for c in os.environ.get("LECTEUR_DEV_IMAGES", "").split(";") if c]
        return [{"chemin": c, "nom": Path(c).name} for c in chemins]


API = ApiDev()


class Gestionnaire(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silencieux
        pass

    def _envoyer(self, code: int, corps: bytes, type_: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)

    def do_GET(self):
        nom = self.path.split("?")[0].lstrip("/") or "index.html"
        fichier = (UI / nom).resolve()
        if UI not in fichier.parents or not fichier.exists():
            return self._envoyer(404, b"introuvable", "text/plain")
        corps = fichier.read_bytes()
        if nom == "index.html":
            corps = corps.replace(b'<script src="app.js">', f"<script>{PONT}</script><script src=\"app.js\">".encode())
        types = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "application/javascript"}
        self._envoyer(200, corps, types.get(fichier.suffix, "application/octet-stream"))

    def do_POST(self):
        nom = self.path.removeprefix("/api/")
        longueur = int(self.headers.get("Content-Length", 0))
        args = json.loads(self.rfile.read(longueur) or b"[]")
        try:
            res = getattr(API, nom)(*args)
            self._envoyer(200, json.dumps(res, ensure_ascii=False).encode(), "application/json")
        except Exception as e:  # noqa: BLE001
            self._envoyer(500, str(e).encode(), "text/plain; charset=utf-8")


if __name__ == "__main__":
    print("Interface de développement : http://localhost:8765")
    ThreadingHTTPServer(("127.0.0.1", 8765), Gestionnaire).serve_forever()
