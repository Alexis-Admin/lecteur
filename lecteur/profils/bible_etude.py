"""Profil « Bible d'étude » : texte biblique en haut, notes en bas sur deux colonnes.

Zones ignorées : en-tête et numéro de page, renvois de marge, onglets des livres.
Produit deux pistes continues d'une page à l'autre : « texte » (versets) et « notes ».
Les notes commencent par leur référence (« 16.3 », « 5.1ss », « 4.19-26 »).

Repères utilisés (scans CZUR) : la Bible est en police à empattements (Times), les notes
et encadrés en police sans empattements (Arial), les renvois de marge en Arial gras.
Les numéros de verset sont plus petits que le texte ; les numéros de chapitre sont des lettrines.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

import pymupdf

from ..modele import Bloc, Livre, Section
from ..nettoyage import TRAIT_CONDITIONNEL, assembler, corriger_texte, nettoyer_mot
from ..pdf_mots import Mot, colle, grouper_en_lignes, mots_de_page, taille_corps, texte_ligne
from ..references import abreviation_de, analyser_etiquette, nom_affiche

NOM = "bible_etude"
_RE_NOTE_TRAD = re.compile(r"^([a-h])\s*(\d{1,3})\.(\d{1,3})\s+(.*)$")
_RE_ENTETE = re.compile(r"([A-ZÀ-Ü][A-ZÀ-Ü\- ]{2,})\s+(\d{1,3})\.(\d{1,3})")


@dataclass
class Evenement:
    y: float
    genre: str  # "partie", "intertitre", "chapitre", "ligne"
    texte: str = ""
    mots: list[Mot] = field(default_factory=list)
    numero: int = 0


@dataclass
class PageAnalysee:
    numero: int
    largeur: float
    hauteur: float
    corps: float
    entete_livre: str | None = None
    entete_ref: tuple[int, int] | None = None
    entete_premier_verset: bool = True  # en-tête à gauche = premier verset de la page
    bible: list[Evenement] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # lignes, dans l'ordre de lecture
    encadres: list[tuple[float, list[str]]] = field(default_factory=list)
    notes_trad: list[tuple[float, str]] = field(default_factory=list)
    zones: list[dict] = field(default_factory=list)  # pour l'aperçu


def _rect(genre: str, mots: list[Mot]) -> dict | None:
    if not mots:
        return None
    return {"genre": genre, "x0": min(m.x0 for m in mots), "y0": min(m.y0 for m in mots),
            "x1": max(m.x1 for m in mots), "y1": max(m.y1 for m in mots)}


def _percentile(valeurs: list[float], p: float) -> float:
    v = sorted(valeurs)
    if not v:
        return 0.0
    k = max(0, min(len(v) - 1, int(round(p / 100 * (len(v) - 1)))))
    return v[k]


def analyser_page(page: pymupdf.Page, numero: int) -> PageAnalysee:
    W, H = page.rect.width, page.rect.height
    mots = [m for m in mots_de_page(page, numero) if m.texte.strip()]
    corps = taille_corps([m for m in mots if not m.sans]) if any(not m.sans for m in mots) else taille_corps(mots)
    pa = PageAnalysee(numero, W, H, corps)

    haut, bas = H * 0.065, H * 0.97
    entete = [m for m in mots if m.y1 <= haut]
    pied = [m for m in mots if m.y0 >= bas]
    if entete:
        txt = texte_ligne(sorted(entete, key=lambda m: m.x0))
        if (me := _RE_ENTETE.search(txt)):
            pa.entete_livre = me.group(1).strip()
            pa.entete_ref = (int(me.group(2)), int(me.group(3)))
            premier = next((m for m in entete if m.texte.isalpha() and m.texte.isupper()), None)
            pa.entete_premier_verset = premier is None or premier.x0 < W / 2
        pa.zones.append(_rect("ignore", entete))
    if pied:
        pa.zones.append(_rect("ignore", pied))
    mots = [m for m in mots if haut < m.y1 and m.y0 < bas]

    # Colonne du texte biblique : mots à empattements de taille normale.
    corps_bible = [m for m in mots if not m.sans and 0.8 * corps <= m.taille <= 1.3 * corps
                   and len(m.texte) >= 2 and m.texte.strip(".,;:!?»«’'").isalpha()]
    if len(corps_bible) < 8:
        corps_bible = [m for m in mots if not m.sans]
    # Bords de la colonne : mots de taille normale seulement (les renvois de marge sont plus petits).
    col_x0 = min((m.x0 for m in corps_bible), default=0)
    col_x1 = max((m.x1 for m in corps_bible), default=W)

    bible: list[Mot] = []
    marge: list[Mot] = []
    sans: list[Mot] = []
    for m in mots:
        # Un mot de la colonne commence avant son bord droit et finit après son bord gauche.
        dans_col = m.x0 <= col_x1 and m.x1 >= col_x0
        if m.taille < 0.4 * corps and not m.texte.isalpha():
            marge.append(m)  # débris minuscules
        elif not m.sans:
            (bible if dans_col else marge).append(m)
        elif m.gras and not dans_col:
            marge.append(m)
        elif m.gras and dans_col and m.taille >= 1.5 * corps:
            bible.append(m)  # lettrine du numéro de chapitre
        else:
            sans.append(m)

    normaux = [m for m in bible if 0.7 * corps <= m.taille <= 1.35 * corps]
    bible_bas = max((m.y1 for m in normaux), default=0)

    # Texte sans empattements dans la zone biblique : titres de partie, notes de traduction.
    # Hors de la colonne et à la hauteur du texte biblique : ce sont des débris de marge.
    marge += [m for m in sans if m.y0 <= bible_bas and not (m.x0 <= col_x1 and m.x1 >= col_x0)]
    dans_bible = [m for m in sans if m.y0 <= bible_bas and m.x0 <= col_x1 and m.x1 >= col_x0]
    bas_page = [m for m in sans if m.y0 > bible_bas]
    if marge:
        pa.zones.append(_rect("ignore", marge))
    for ligne in grouper_en_lignes(dans_bible):
        txt = texte_ligne(ligne)
        # Morceaux de lettrine mal lus (« ■4 C » à gauche d'une ligne biblique) : numéro de chapitre ou débris.
        a_droite = [b for b in bible if b.x0 > ligne[-1].x1 and abs(b.yc - ligne[0].yc) < corps * 0.7
                    and 0.7 * corps <= b.taille <= 1.35 * corps]
        if all(m.gras for m in ligne) and a_droite and ligne[-1].x1 - col_x0 < 6 * corps:
            chiffres = re.sub(r"\D", "", txt)
            if chiffres:
                bible.append(Mot(chiffres, ligne[0].x0, ligne[0].y0, ligne[-1].x1, ligne[-1].y1, ligne[0].base,
                                 corps * 2, True, True, False, numero))
            pa.zones.append(_rect("ignore", ligne))
            continue
        if (mt := _RE_NOTE_TRAD.match(txt)):
            pa.notes_trad.append((ligne[0].y0, txt))
            pa.zones.append(_rect("notes", ligne))
        elif all(m.gras for m in ligne):
            pa.bible.append(Evenement(ligne[0].y0, "partie", txt))
        else:
            pa.encadres.append((ligne[0].y0, [txt]))
            pa.zones.append(_rect("encadre", ligne))

    # Flux biblique : lettrines, intertitres, lignes.
    lettrines = [m for m in bible if m.taille >= 1.6 * corps]
    reste = [m for m in bible if m.taille < 1.6 * corps]
    lignes_ev: list[tuple[float, float, Evenement]] = []
    for ligne in grouper_en_lignes(reste):
        txt = texte_ligne(ligne)
        y0 = statistics.median(m.y0 for m in ligne)
        y1 = statistics.median(m.y1 for m in ligne)
        if all(m.italique and not m.sans for m in ligne) and len(ligne) <= 14:
            ev = Evenement(y0, "intertitre", txt)
        elif all(m.sans and m.gras for m in ligne):
            ev = Evenement(y0, "partie", txt)
        else:
            ev = Evenement(y0, "ligne", mots=ligne)
        pa.bible.append(ev)
        lignes_ev.append((y0, y1, ev))
    for m in lettrines:
        chiffres = re.sub(r"\D", "", m.texte)
        if chiffres:
            # La lettrine couvre deux lignes : le chapitre commence à la première.
            touchees = [y0 for (y0, y1, ev) in lignes_ev if ev.genre == "ligne" and y1 > m.y0 and y0 < m.y1]
            pa.bible.append(Evenement((min(touchees) if touchees else m.y0) - 0.01, "chapitre", numero=int(chiffres)))
    pa.bible.sort(key=lambda e: e.y)
    if normaux:
        pa.zones.append({"genre": "bible", "x0": col_x0, "y0": min(m.y0 for m in normaux), "x1": col_x1, "y1": bible_bas})

    # Bas de page : notes de traduction, encadrés et notes sur deux colonnes.
    if bas_page:
        lignes = grouper_en_lignes(bas_page, tolerance=taille_corps(bas_page) * 0.55)
        # Débuts de segment : premier mot d'une ligne ou mot après un vrai blanc (gouttière).
        debuts: list[Mot] = []
        for ligne in lignes:
            for i, m in enumerate(ligne):
                if i == 0 or m.x0 - ligne[i - 1].x1 > 6:
                    debuts.append(m)
        bas = [m for m in debuts if m.y0 > H * 0.84] or debuts
        L = min(m.x0 for m in bas)
        if L > W * 0.4:
            L = min(m.x0 for m in debuts)
        droites = [round(m.x0 / 2) * 2 for m in bas if m.x0 > L + W * 0.3]
        R = min(droites, key=lambda x: (-droites.count(x), x)) if droites else None
        if R is not None:
            R = min(m.x0 for m in bas if abs(m.x0 - R) <= 3)
        milieu = (R - 4) if R else None
        gauche_l: list[list[Mot]] = []
        droite_l: list[list[Mot]] = []
        encadre_l: list[list[Mot]] = []
        for ligne in lignes:
            txt = texte_ligne(ligne)
            debut = ligne[0].x0
            if _RE_NOTE_TRAD.match(txt):
                pa.notes_trad.append((ligne[0].y0, txt))
                pa.zones.append(_rect("notes", ligne))
                continue
            pres_l = L - 4 <= debut <= L + 14
            pres_r = R is not None and R - 4 <= debut <= R + 14
            if pres_l or pres_r:
                if milieu is None:
                    gauche_l.append(ligne)
                else:
                    g = [m for m in ligne if m.x0 < milieu]
                    d = [m for m in ligne if m.x0 >= milieu]
                    if g:
                        gauche_l.append(g)
                    if d:
                        droite_l.append(d)
            else:
                encadre_l.append(ligne)
        for col in (gauche_l, droite_l):
            for ligne in col:
                pa.notes.append(texte_ligne(ligne))
        if gauche_l or droite_l:
            pa.zones.append(_rect("notes", [m for l in gauche_l + droite_l for m in l]))
        # Encadrés : lignes proches regroupées.
        groupe: list[list[Mot]] = []
        for ligne in encadre_l:
            if groupe and ligne[0].y0 - groupe[-1][0].y1 > 2.2 * corps:
                pa.encadres.append((groupe[0][0].y0, [texte_ligne(l) for l in groupe]))
                pa.zones.append(_rect("encadre", [m for l in groupe for m in l]))
                groupe = []
            groupe.append(ligne)
        if groupe:
            pa.encadres.append((groupe[0][0].y0, [texte_ligne(l) for l in groupe]))
            pa.zones.append(_rect("encadre", [m for l in groupe for m in l]))
    pa.zones = [z for z in pa.zones if z]
    return pa


# ---------------------------------------------------------------------------
# Assemblage du livre
# ---------------------------------------------------------------------------
class _Constructeur:
    def __init__(self, livre: Livre, apprises: dict[str, str] | None):
        self.livre = livre
        self.apprises = apprises
        self.journal: list[tuple[str, str, int]] = []
        self.ch = 0
        self.v: int | None = 0
        self.section: Section | None = None
        self.parties: list[str] = []
        self.lignes_verset: list[str] = []
        self.verset_ouvert = False
        self.verset_page: int | None = None
        self.n_bloc = 0
        self.corps = 10.0
        self.page = 0
        self.positions: list[tuple[float, int, int]] = []  # (y, ch, v) de la page courante

    # --- utilitaires ---
    def _id(self) -> str:
        self.n_bloc += 1
        return f"b{self.n_bloc:05d}"

    def _note_journal(self, paires: list) -> None:
        for avant, apres in paires:
            self.journal.append((avant, apres, self.page))

    def _texte(self, lignes: list[str]) -> str:
        j: list = []
        t = corriger_texte(assembler(lignes, j), j, self.apprises)
        self._note_journal(j)
        return t

    def _nouvelle_section(self, titre: str) -> Section:
        s = Section(f"s{len(self.livre.sections) + 1:03d}", titre)
        self.livre.sections.append(s)
        self.section = s
        for p in self.parties:
            s.blocs.append(Bloc(self._id(), "texte", "partie", p, page=self.page))
        self.parties = []
        return s

    def _section(self) -> Section:
        return self.section or self._nouvelle_section("Suite")

    def fermer_verset(self) -> None:
        if self.lignes_verset:
            t = self._texte(self.lignes_verset)
            # Lettre isolée qui n'est pas un mot (débris de lettrine) ; apostrophe orpheline en fin de verset.
            debris = re.findall(r"(?<![\w’'.-])[B-HJ-NP-Zb-xz](?![\w’'.-])", t)
            if debris:
                t = re.sub(r"(?<![\w’'.-])[B-HJ-NP-Zb-xz](?![\w’'.-])", "", t)
                t = re.sub(r"\s{2,}", " ", t).strip()
                self._note_journal([(d, "∅") for d in debris])
            t = re.sub(r"\s*['’]$", "", t)
            if t:
                if self.ch and self.v:
                    self._section().blocs.append(Bloc(self._id(), "texte", "verset", t, self.ch, self.v, page=self.verset_page))
                else:
                    self._section().blocs.append(Bloc(self._id(), "texte", "paragraphe", t, page=self.verset_page))
        self.lignes_verset = []
        self.verset_page = None

    def ouvrir_verset(self, n: int) -> None:
        self.fermer_verset()
        self.v = n
        self.verset_page = self.page

    # --- flux biblique ---
    def debut_page(self, pa: PageAnalysee) -> None:
        self.page = pa.numero
        self.corps = pa.corps
        self.positions = []
        if not pa.entete_ref:
            return
        # L'en-tête donne le premier verset de la page (en-tête à gauche) ou le dernier (à droite).
        hch, hv = pa.entete_ref
        lettrines = sum(1 for e in pa.bible if e.genre == "chapitre")
        if pa.entete_premier_verset:
            debut_ch, debut_v = hch, (hv - 1 if hv > 1 else None)
        else:
            debut_ch, debut_v = max(1, hch - lettrines), None
        if self.ch != debut_ch:
            # Pages sautées (ou premier import) : on se fie à l'en-tête.
            self.fermer_verset()
            self.ch, self.v = debut_ch, debut_v

    def _est_numero(self, mot: Mot, suivant: Mot | None) -> int | None:
        t = mot.texte.strip(".")
        if not t.isdigit() or len(t) > 3:
            return None
        n = int(t)
        petit = mot.taille < 0.88 * self.corps
        attendu = self.v is None or (self.v is not None and self.v < n <= self.v + 3)
        if self.v is None and petit and 1 <= n <= 180:
            return n
        if petit and attendu:
            return n
        # Retour à 2 ou 3 sans lettrine lisible : nouveau chapitre.
        if petit and self.v is not None and n in (2, 3) and self.v >= 6:
            return -n
        # Numéro de taille normale en début de paragraphe (« 6 A l'âge… »).
        if self.v is not None and n == self.v + 1 and suivant is not None and suivant.texte[:1].isupper():
            return n
        return None

    def ligne(self, ev: Evenement) -> None:
        mots = ev.mots
        courante = ""
        precedent: Mot | None = None
        for i, m in enumerate(mots):
            suivant = mots[i + 1] if i + 1 < len(mots) else None
            texte = m.texte
            # Numéro collé : « supportée.14 » ou « 21A »
            colle_fin = re.match(r"^(.*?[^\d\s])(\d{1,3})$", texte)
            colle_debut = re.match(r"^(\d{1,3})([A-ZÀ-Ü«].*)$", texte)
            n = self._est_numero(m, suivant)
            reste = ""
            if n is None and colle_fin and self.v is not None and int(colle_fin.group(2)) == self.v + 1:
                courante = self._ajouter(courante, colle_fin.group(1), precedent, m)
                n = int(colle_fin.group(2))
            elif n is None and colle_debut and self.v is not None and int(colle_debut.group(1)) == self.v + 1:
                n, reste = int(colle_debut.group(1)), colle_debut.group(2)
            if n is not None:
                if courante.strip():
                    self.lignes_verset.append(courante.strip())
                courante = ""
                if n < 0:  # retour à 2 ou 3 sans lettrine lisible : changement de chapitre
                    # Ce qui précède (depuis l'intertitre) devient le verset n-1 du nouveau chapitre.
                    n = -n
                    self.ch += 1
                    self.v = n - 1
                self.ouvrir_verset(n)
                self.positions.append((ev.y, self.ch, n))
                precedent = None
                if not reste:
                    continue
                texte = reste
            courante = self._ajouter(courante, texte, precedent, m)
            precedent = m
        if courante.strip():
            self.lignes_verset.append(courante.strip())
        if self.ch and self.v:
            self.positions.append((ev.y, self.ch, self.v))

    def _ajouter(self, courante: str, texte: str, precedent: Mot | None, m: Mot) -> str:
        j: list = []
        propre = nettoyer_mot(texte, j)
        self._note_journal(j)
        if not propre:
            return courante
        # Ponctuation isolée après une fin de phrase : débris.
        if propre in {":", ";", ",", "."} and re.search(r"[.!?»]$", courante.strip()):
            return courante
        if self.verset_page is None:
            self.verset_page = self.page
        if not courante or (precedent is not None and colle(precedent, m)) or propre in {"’", "'"} \
                or courante.endswith(("’", "'")):
            return courante + propre
        return courante + " " + propre

    def evenement(self, ev: Evenement) -> None:
        if ev.genre in ("partie", "intertitre"):
            j: list = []
            propre = " ".join(x for x in (nettoyer_mot(w, j) for w in ev.texte.split()) if x)
            self._note_journal(j)
            ev = Evenement(ev.y, ev.genre, propre)
        if ev.genre == "partie":
            self.fermer_verset()
            if ev.texte:
                self.parties.append(self._texte([ev.texte]))
        elif ev.genre == "intertitre":
            self.fermer_verset()
            s = self._nouvelle_section(self._texte([ev.texte]))
            s.blocs.append(Bloc(self._id(), "texte", "titre", s.titre, page=self.page))
        elif ev.genre == "chapitre":
            self.fermer_verset()
            n = ev.numero
            debut_de_chapitre = n == self.ch and (self.v is None or self.v <= 1)  # l'en-tête l'a déjà annoncé
            if not debut_de_chapitre:
                self.ch = n if (self.ch == 0 or n == self.ch + 1) else self.ch + 1
            self.v = 1
            self.verset_page = self.page
            self.positions.append((ev.y, self.ch, 1))
        else:
            self.ligne(ev)

    def ancre_a(self, y: float) -> tuple[int | None, int | None]:
        avant = [p for p in self.positions if p[0] <= y]
        p = avant[-1] if avant else (self.positions[0] if self.positions else None)
        return (p[1], p[2]) if p else (self.ch or None, self.v)


def _ref_section(abr: str, s: Section) -> str:
    vs = [b for b in s.blocs if b.genre == "verset"]
    if not vs:
        return ""
    a, b = vs[0], vs[-1]
    if (a.ch, a.v) == (b.ch, b.v):
        return f"{abr} {a.ch}.{a.v}"
    if a.ch == b.ch:
        return f"{abr} {a.ch}.{a.v}-{b.v}"
    return f"{abr} {a.ch}.{a.v}-{b.ch}.{b.v}"


def construire(doc: pymupdf.Document, pages: list[int], titre: str | None = None,
               apprises: dict[str, str] | None = None, livre_id: str = "") -> tuple[Livre, list[PageAnalysee]]:
    analyses = [analyser_page(doc[p - 1], p) for p in pages]
    nom_livre = next((a.entete_livre for a in analyses if a.entete_livre), None)
    nom = nom_affiche(nom_livre) if nom_livre else (titre or "Livre")
    abr = abreviation_de(nom) or ""
    livre = Livre(livre_id, titre or nom, NOM, "", pages, abr, refs_nues=True)
    c = _Constructeur(livre, apprises)

    notes_brutes: list[tuple[int, str]] = []  # (page, ligne)
    extras: list[Bloc] = []  # encadrés et notes de traduction, déjà ancrés
    for pa in analyses:
        c.debut_page(pa)
        for ev in pa.bible:
            c.evenement(ev)
        for y, lignes in pa.encadres:
            ch, v = c.ancre_a(y)
            t = c._texte([re.sub(r"^[-–]\s*", "– ", l) for l in lignes])
            if t:
                extras.append(Bloc(c._id(), "notes", "encadre", t, ch, v, ref="Encadré", page=pa.numero))
        for y, ligne in pa.notes_trad:
            m = _RE_NOTE_TRAD.match(ligne)
            t = c._texte([m.group(4)])
            extras.append(Bloc(c._id(), "notes", "note_trad", t, int(m.group(2)), int(m.group(3)),
                               ref=f"{m.group(2)}.{m.group(3)}", page=pa.numero))
        notes_brutes.extend((pa.numero, l) for l in pa.notes)
    c.fermer_verset()

    # Notes : une nouvelle note commence par sa référence, après une phrase terminée.
    notes: list[Bloc] = []
    courante: list[str] = []
    entete: tuple | None = None
    page_note = None

    def fermer():
        nonlocal courante
        if courante:
            t = c._texte(courante)
            if t:
                if entete:
                    etiq, ch, v, chf, vf = entete
                    ancre = (chf, vf) if (chf, vf) != (ch, v) else (ch, v)
                    notes.append(Bloc(c._id(), "notes", "note", t, ancre[0], ancre[1], ref=etiq, page=page_note,
                                      ch_fin=chf, v_fin=vf))
                else:
                    notes.append(Bloc(c._id(), "notes", "note", t, None, None, page=page_note))
        courante = []

    chapitres = {b.ch for s in livre.sections for b in s.blocs if b.genre == "verset"}

    def plausible(ch: int) -> bool:
        return not chapitres or (min(chapitres) - 1 <= ch <= max(chapitres) + 1)

    precedente = ""
    for page, ligne in notes_brutes:
        j: list = []
        ligne = " ".join(x for x in (nettoyer_mot(w, j) for w in ligne.split(" ")) if x)
        c._note_journal(j)
        e = analyser_etiquette(ligne)
        if e and not plausible(e[1]):
            # « 7 6.6- » lu « 76.6 » : on retire le chiffre de trop si ça redevient plausible.
            corrige = analyser_etiquette(ligne[1:]) if len(str(e[1])) > 1 else None
            if corrige and plausible(corrige[1]):
                c._note_journal([(e[0], corrige[0])])
                ligne, e = ligne[1:], corrige
            else:
                e = None
        fin_phrase = not precedente or re.search(r"[.!?»)…]\s*$", precedente.rstrip(TRAIT_CONDITIONNEL))
        if e and fin_phrase:
            fermer()
            entete = e
            page_note = page
            reste = re.sub(r"^[-–]\s*", "", ligne.strip()[len(e[0]):].strip())
            courante = [reste] if reste else []
        else:
            if page_note is None:
                page_note = page
            courante.append(ligne)
        precedente = ligne
    fermer()

    _ranger_notes(livre, notes + extras)
    for s in livre.sections:
        s.ref = _ref_section(abr, s) if abr else ""
    livre.corrections = [{"avant": a, "apres": b, "page": p} for a, b, p in c.journal if a != b]
    return livre, analyses


def _ranger_notes(livre: Livre, notes: list[Bloc]) -> None:
    """Place chaque note dans la section qui contient son verset d'ancrage."""
    if not livre.sections:
        livre.sections.append(Section("s001", "Notes"))
    index: list[tuple[tuple[int, int], int]] = []
    for i, s in enumerate(livre.sections):
        for b in s.blocs:
            if b.genre == "verset":
                index.append(((b.ch, b.v), i))
    for n in notes:
        cible = 0
        if n.ch is not None and n.v is not None and index:
            avant = [i for (cv, i) in index if cv <= (n.ch, n.v)]
            cible = avant[-1] if avant else index[0][1]
        elif index:
            cible = index[0][1]
        livre.sections[cible].blocs.append(n)
    # Dans chaque section : texte d'abord (ordre d'origine), puis notes dans l'ordre des versets.
    for s in livre.sections:
        texte = [b for b in s.blocs if b.piste == "texte"]
        nts = [b for b in s.blocs if b.piste == "notes"]
        nts.sort(key=lambda b: ((b.ch or 0), (b.v or 0), 0 if b.genre == "note" else 1))
        s.blocs = texte + nts
