"""Petit serveur local (127.0.0.1 seulement) qui sert les MP3 de la bibliothèque à la fenêtre de l'app.

Il comprend les requêtes « Range » : le lecteur peut avancer ou reculer dans l'audio sans tout recharger.
Un jeton secret dans l'adresse empêche les autres programmes d'y lire au hasard.
"""
from __future__ import annotations

import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import bibliotheque

JETON = secrets.token_urlsafe(16)
_serveur: ThreadingHTTPServer | None = None


class _Gestionnaire(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        m = re.fullmatch(rf"/{re.escape(JETON)}/([a-z0-9\-]+)/audio/(sections|blocs)/([\w\-.]+\.mp3)", self.path.split("?")[0])
        if not m:
            return self.send_error(404)
        racine = bibliotheque.dossier_livres().resolve()
        f = (racine / m.group(1) / "audio" / m.group(2) / m.group(3)).resolve()
        if racine not in f.parents or not f.exists():
            return self.send_error(404)
        taille = f.stat().st_size
        debut, fin = 0, taille - 1
        plage = self.headers.get("Range")
        if plage and (r := re.match(r"bytes=(\d*)-(\d*)", plage)):
            if r.group(1):
                debut = int(r.group(1))
            if r.group(2):
                fin = min(int(r.group(2)), taille - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {debut}-{fin}/{taille}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(fin - debut + 1))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with open(f, "rb") as fh:
            fh.seek(debut)
            reste = fin - debut + 1
            try:
                while reste > 0:
                    morceau = fh.read(min(65536, reste))
                    if not morceau:
                        break
                    self.wfile.write(morceau)
                    reste -= len(morceau)
            except (ConnectionResetError, BrokenPipeError):
                pass  # le lecteur a demandé une autre partie


def demarrer() -> int:
    """Lance le serveur (une fois) et retourne son port."""
    global _serveur
    if _serveur is None:
        _serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Gestionnaire)
        threading.Thread(target=_serveur.serve_forever, daemon=True).start()
    return _serveur.server_address[1]


def adresse(chemin: Path) -> str:
    """Adresse http d'un MP3 de la bibliothèque."""
    rel = chemin.resolve().relative_to(bibliotheque.dossier_livres().resolve()).as_posix()
    return f"http://127.0.0.1:{demarrer()}/{JETON}/{rel}"
