"""Reconnaissance de texte (OCR) des captures d'écran avec le moteur intégré à Windows (français).

Rien à installer : Windows 10/11 inclut l'OCR ; la langue « fr-CA » ou « fr-FR » doit être présente
(Paramètres › Heure et langue › Langue). Retourne des « Mot » avec leur position, comme pour un PDF.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from .pdf_mots import Mot


def langues_disponibles() -> list[str]:
    try:
        from winrt.windows.media.ocr import OcrEngine

        return [l.language_tag for l in OcrEngine.available_recognizer_languages]
    except Exception:  # noqa: BLE001 - pas de Windows ou paquet absent
        return []


def _moteur():
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine

    for tag in ("fr-CA", "fr-FR", "fr"):
        try:
            if OcrEngine.is_language_supported(Language(tag)):
                return OcrEngine.try_create_from_language(Language(tag))
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("La reconnaissance de texte en français n'est pas installée dans Windows "
                       "(Paramètres › Heure et langue › Langue › Français › Options › Reconnaissance optique).")


async def _ocr(chemin: Path, numero: int) -> tuple[list[Mot], float, float]:
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage import FileAccessMode, StorageFile

    fichier = await StorageFile.get_file_from_path_async(str(chemin.resolve()))
    flux = await fichier.open_async(FileAccessMode.READ)
    decodeur = await BitmapDecoder.create_async(flux)
    image = await decodeur.get_software_bitmap_async()
    resultat = await _moteur().recognize_async(image)
    mots: list[Mot] = []
    for ligne in resultat.lines:
        for w in ligne.words:
            r = w.bounding_rect
            mots.append(Mot(w.text, r.x, r.y, r.x + r.width, r.y + r.height, r.y + r.height, r.height,
                            False, False, False, numero))
    return mots, float(image.pixel_width), float(image.pixel_height)


def lire_image(chemin: Path, numero: int = 1) -> tuple[list[Mot], float, float]:
    """Mots de l'image (avec positions en pixels), largeur, hauteur."""
    return asyncio.run(_ocr(Path(chemin), numero))
