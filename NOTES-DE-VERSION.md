# Notes de version — Lecteur

## 1.1.0 — 21 novembre 2026

Audit sur 15 livres différents (romans, essais, Bibles, commentaires, livres en anglais).

**Sections et texte**
- Vrais chapitres dans les romans : « Chapitre 2 · Rhys » (le numéro de chapitre n'est plus jeté), et plus d'en-têtes répétés (« ANA HUANG », « LE BUT 13 ») pris pour des chapitres.
- Paragraphes recollés quand une page, un en-tête ou une colonne les coupait au milieu d'une phrase.
- Encadrés sur le côté de la page (ex. Ze bible) lus à part, à la fin de la section, au lieu d'être mélangés ligne par ligne au texte.
- Bible d'étude : plus de sections faites d'un titre seul (Psaumes), plus de citations en italique prises pour des titres, plus de renvois de marge (« 2Co ») au milieu des mots.
- Mots coupés en fin de ligne sans trait d'union recollés (« maî trisait »), appels de note retirés (« décennie2 »), nombres collés séparés (« 3ans »).
- Pages de garde et de copyright réunies au lieu de faire 10 petites sections.
- Mise en page choisie toute seule d'après le contenu du PDF (Bible d'étude ou livre).

**Livres en anglais**
- Langue détectée à l'import : voix anglaise (Clara, Liam, Aria, Guy), pas de faux « mots à vérifier » français.

**Écoute**
- Un clic sur une section ouvre toujours sa lecture, même depuis l'aperçu.
- La création de l'audio commence par la section ouverte : on peut l'écouter tout de suite.

**Révision**
- Un clic sur un mot l'encadre en jaune sur la page scannée et dans le texte.
- Changements sûrs beaucoup plus prudents (plus de « fugué » → « fugue », « mantra » → « montra »), et nouveaux cas sûrs : mots collés (« lesyeux » → « les yeux »), majuscule sans accent (« Etes-vous » → « Êtes-vous »).
- Noms propres regroupés avec un bouton « Tous ces noms sont bons ».
- Beaucoup moins de faux mots à vérifier : un mot qui revient 3 fois ou plus, ou un mot rare bien formé, n'est plus signalé.
- La révision est facultative : on peut créer l'audio quand on veut.

## 1.0.1 — 21 novembre 2026

Premiers retours d'usage.

- **Écoute plus fluide** : les longs silences au début et à la fin de chaque verset sont retirés (environ 1,4 s de trou avant, 0,15 à 0,5 s maintenant selon la ponctuation). La section suivante se prépare pendant l'écoute. Les encadrés sont lus à la fin de la section, sans couper le récit.
- **Vitesse par pas de 0,05x** avec les boutons − et + (ou [ et ]). L'export clé USB propose aussi ta vitesse exacte.
- **Révision plus claire** : « Changements sûrs » à cocher et appliquer en un clic, « À décider » avec des choix nommés (« Remplacer par », « C'est bon », « Écrire… »), progression, et « Déjà corrigé automatiquement » regroupé par sorte.
- **Réglages** : liste des corrections retenues et des mots gardés, avec ✕ pour les oublier.
- **Romans scannés** : les lignes grossies ou mises en gras par la reconnaissance de texte ne deviennent plus de faux chapitres. Il faut réimporter le livre pour en profiter.
- **Barre de gauche** : la bibliothèque reste visible même avec beaucoup de sections, et la section en cours reste à l'écran.

## 1.0.0 — 21 novembre 2026

Première version complète.

**Importer**
- PDF scannés (texte OCR) et PDF normaux, lus par zones : « Bible d'étude » (texte et notes en deux pistes, notes rattachées à leur verset), « Commentaire 2 colonnes », « Livre simple ».
- Captures d'écran (reconnaissance de texte de Windows, Ctrl+V pour coller), texte collé, page web (seul l'article est gardé).
- Correction automatique des erreurs de scan fréquentes, références bibliques lues au long (« Gn 4.7 » → « Genèse, chapitre 4, verset 7 »).
- Aperçu : page scannée avec ses zones (et loupe), texte modifiable, mots à vérifier, corrections retenues pour les livres suivants.

**Écouter**
- Voix Sylvie, Antoine, Jean, Thierry (Québec) ou Siwis (hors ligne), avec un extrait pour choisir.
- Création de l'audio en arrière-plan, avec pause et reprise ; seul un passage corrigé est refait.
- Lecteur : mot en cours surligné, phrase en cours mise en avant, défilement automatique, clic sur une phrase pour y sauter, vitesse de 0,75x à 3x, ±15 s, reprise exacte, sections écoutées cochées, temps restant.
- Modes d'écoute : texte, notes, ou texte + notes (chaque note après son verset).

**Clé USB**
- Un MP3 par section, numérotés dans l'ordre (« 01 - Gn 4.17-24 Titre.mp3 »), titres dans les métadonnées, vitesse intégrée aux fichiers, copie vérifiée, éjection de la clé.

**Confort**
- Mode jour et mode nuit, tout est mémorisé, polices incluses (belle même sans Internet), Réglages (dossier des données, ménage de l'audio, raccourcis clavier).
