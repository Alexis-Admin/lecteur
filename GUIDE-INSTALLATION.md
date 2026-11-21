# Guide d'installation — Lecteur

Pour un PC Windows 10 ou 11. Compte environ 15 minutes la première fois.
L'app n'a pas besoin des droits d'administrateur.

---

## 1. Ce qu'il faut

- **Python 3.12** (le langage dans lequel l'app est écrite).
- **FFmpeg** (l'outil qui assemble les fichiers audio).
- **Internet** pour la voix Sylvie (la voix « Siwis » fonctionne sans Internet).
- Environ **1 Go** d'espace pour l'app, plus environ **22 Mo par heure d'audio** pour tes livres.

---

## 2. Installer Python (une seule fois)

1. Va sur **python.org** → menu **Downloads** → clique sur **Download Python 3.12** (ou plus récent).
2. Ouvre le fichier téléchargé.
3. **Important :** coche la case **« Add python.exe to PATH »** en bas de la première fenêtre, puis clique sur **Install Now**.
4. Vérifie : touche **Windows**, tape `cmd`, **Entrée**, puis tape :
   ```
   python --version
   ```
   Tu dois voir `Python 3.12.…`. Ferme la fenêtre.

## 3. Installer FFmpeg (une seule fois)

1. Touche **Windows**, tape `Terminal`, **Entrée**.
2. Tape cette commande, puis **Entrée** :
   ```
   winget install Gyan.FFmpeg
   ```
   Réponds `O` (ou `Y`) si on te demande d'accepter les conditions.
3. **Ferme le Terminal** (FFmpeg n'est reconnu qu'après l'avoir rouvert).

## 4. Télécharger l'app

1. Va sur la page **Releases** du dépôt GitHub de Lecteur et télécharge le fichier **`Lecteur-….zip`** de la version tout en haut (la plus récente, ex. `Lecteur-1.0.1.zip`).
2. Clic droit sur le fichier → **Extraire tout…** → choisis un dossier, par exemple `Documents\Lecteur-app`.

## 5. Installer les composants

1. Dans le dossier extrait, double-clique sur **`installer.bat`**.
2. Si Windows affiche « Windows a protégé votre ordinateur » : clique sur **Informations complémentaires**, puis **Exécuter quand même**. C'est normal : l'app n'est pas signée.
3. Attends la fin (2 à 5 minutes). Le message **« Installation terminée »** apparaît. Appuie sur une touche.

## 6. Lancer l'app

1. Double-clique sur **`Lecteur.bat`**.
2. Pour l'avoir sur le bureau : clic droit sur `Lecteur.bat` → **Afficher d'autres options** → **Envoyer vers** → **Bureau (créer un raccourci)**.

---

## 7. Premier livre, de A à Z

1. **Importer** : clique sur **PDF**, **Captures**, **Texte** ou **Page web** (ou fais **Ctrl+O**).
   - PDF scanné d'une Bible d'étude : choisis la mise en page **Bible d'étude**.
   - Tu peux limiter aux pages voulues : `15-17, 29`.
2. **Vérifier** : l'écran **Aperçu** montre la page scannée, le texte nettoyé et les mots **à vérifier**. Corrige ce qui est faux (un mot corrigé l'est partout dans le livre).
3. **Créer l'audio** : bouton **« 3 Créer l'audio › »** en haut de l'aperçu, ou **Créer l'audio** en bas de la lecture.
4. **Écouter** : ▶ (ou **Espace**). Clique sur une phrase pour y sauter. La vitesse se règle de 0,75x à 3x.
5. **Clé USB** : branche la clé, clique sur **Clé USB** en bas à gauche, choisis la vitesse, puis **Copier** et **Éjecter la clé**.

## 8. Captures d'écran : la langue française

La reconnaissance de texte des captures utilise celle de Windows. Si l'app dit qu'elle manque :
**Paramètres** → **Heure et langue** → **Langue et région** → **Français (Canada)** → **…** → **Options de langue** → installe **Reconnaissance optique de caractères**.

---

## 9. Où sont mes données ?

Dans **`Documents\Lecteur`** : tes livres, l'audio, tes corrections apprises et tes réglages.
Elles sont **séparées de l'app** : tu peux supprimer ou remplacer le dossier de l'app sans rien perdre.
Bouton ⚙ **Réglages** → **Ouvrir le dossier** pour y aller.

## 10. Mettre à jour vers une nouvelle version

1. Télécharge le nouveau `.zip` dans **Releases**.
2. Extrais-le **à la place** de l'ancien dossier de l'app (tes données dans `Documents\Lecteur` ne bougent pas).
3. Double-clique sur **`installer.bat`**, puis sur **`Lecteur.bat`**.

## 11. Problèmes fréquents

| Ce que tu vois | Quoi faire |
|---|---|
| « Python n'est pas installé » | Refais l'étape 2 en cochant bien **Add python.exe to PATH**. |
| « FFmpeg n'est pas installé » | Refais l'étape 3, puis **ferme et rouvre** l'app. |
| « La voix en ligne ne répond pas » | Vérifie Internet, réessaie plus tard, ou choisis la voix **Siwis (hors ligne)**. |
| La clé USB n'apparaît pas | Clique sur **Actualiser** dans la fenêtre Clé USB, ou **Choisir un dossier…**. |
| Windows refuse d'éjecter la clé | Ferme les fenêtres de l'Explorateur ouvertes sur la clé, puis réessaie. |
| Un livre supprimé par erreur | Il est dans la **corbeille Windows** : clic droit → **Restaurer**. |
