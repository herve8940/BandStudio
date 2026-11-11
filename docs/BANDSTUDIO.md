# BandStudio · guide de préparation

1. **Importer** un morceau audio ou un lien autorisé. Le fichier original est conservé.
2. **Séparer & analyser** : choisir 4 ou 6 pistes, puis détecter tempo, structure, paroles et accords avec les composants installés.
3. **Pistes & structure** : choisir **Mon instrument**, écouter en solo ou sans cette partie ; modifier volumes, panoramiques, sections et repères. Play et Espace déclenchent la même commande. Les sous-pistes chant/batterie remplacent leur piste parente dans le mix pour éviter un doublage.
4. **Click & cues** : vérifier le premier temps, la mesure et le tempo. Régler click, annonces et décompte. **Paroles & accords** permet de corriger le texte, les horaires, la tonalité et le capo.
5. **Valider & envoyer** : écouter les passages importants, confirmer les trois points de validation, puis exporter/ouvrir le projet dans REAPER. Changer le mix, la vitesse, la hauteur ou les repères annule la validation précédente.

## Traitement du morceau

| Usage | BandStudio | Limites |
|---|---|---|
| Séparer les instruments | Demucs 4/6 pistes | Guitare et piano seulement avec le modèle 6 pistes ; résidus possibles |
| Sous-pistes | DrumSep, chant principal/chœurs | Moteurs facultatifs ; pas tous les instruments spécialisés de Moises Pro |
| Écouter sa partie | Original, mix, solo et sans l’instrument choisi | Seuls les instruments disponibles sont proposés |
| Vitesse et hauteur | 50–150 %, ±12 demi-tons | Artefacts possibles ; Windows prépare les changements dans le cache |
| Tempo, tonalité, structure | Détection et corrections | Résultats à vérifier musicalement |
| Boucles, métronome, décompte | Passage précis, progression, guides séparés | La carte audio et les voix système restent à tester sur chaque ordinateur |
| Accords et paroles | Détection, édition, capo, LRC/SRT | Modèles locaux facultatifs ; la transcription du chant est imparfaite |
| Exports | Mix, stems, MIDI batterie, PDF, projet REAPER | Les stems individuels restent au tempo et à la hauteur d’origine ; le projet REAPER applique les réglages validés |

Référence fonctionnelle : [traitement d’un morceau dans Moises](https://help.moises.ai/hc/en-us/articles/8583454469276-How-to-Upload-and-Edit-your-track-using-Moises). BandStudio est un projet indépendant. Le mastering et la génération musicale ne font pas partie de son atelier de préparation.

## Windows

Télécharger la version principale depuis les Releases, extraire le ZIP complet dans un dossier accessible en écriture et lancer `BandStudio.exe`. Installer les composants manquants depuis Réglages. Le paquet embarque Python et FFmpeg ; WebView2 et .NET Framework 4.8 sont nécessaires. Les essais CI utilisent Windows et un dossier avec accents/espaces, avec les bibliothèques marquées comme téléchargées par Windows. Le pilote de la carte son et les analyses IA demandent une vérification sur le PC cible.

### Erreur `Python.Runtime.Loader.Initialize` au démarrage

Windows peut transmettre aux DLL le marquage de provenance Internet du ZIP téléchargé. .NET refuse alors de charger `Python.Runtime.dll`, avant l’ouverture de l’interface. Le lanceur des nouveaux paquets prépare automatiquement les bibliothèques du moteur : il vérifie leur SHA-256 contre l’inventaire créé à la construction avant de retirer ce marquage. Les fichiers inconnus ou modifiés sont exclus ; aucune politique Windows n’est changée.

Pour une ancienne installation bloquée : télécharger le nouveau ZIP et l’extraire dans un nouveau dossier. Autre solution pour le ZIP officiel déjà téléchargé : clic droit → **Propriétés → Débloquer → Appliquer**, puis extraire à nouveau dans un nouveau dossier. Conserver les anciens projets. Une application qui ne démarre pas ne peut pas récupérer sa mise à jour automatique.

Si l’erreur persiste, joindre le fichier `%LOCALAPPDATA%/BandStudio/Logs/startup.log` au signalement, après vérification de son contenu. Le journal `application.log` indique aussi l’étape de démarrage et le nombre de bibliothèques préparées. Référence : [diagnostic du blocage des DLL téléchargées](https://github.com/pyinstaller/pyinstaller/issues/8294).

## macOS

Pour une installation de développement disposant déjà d’un moteur ReaCue local et de ses environnements Python, depuis la racine du dépôt :

```sh
python3 tools/build_studio_mac.py --prepare-runtime --source "$HOME/Documents/ReaCue"
python3 tools/install_studio_mac.py
```

Le programme de construction attend les environnements `.venv`, `.venv-demucs`, `.venv-structure`, `.venv-import`, `.venv-words`, `.venv-chords`, `.venv-drums` et leurs ressources, préparés par les installateurs existants. Il produit une copie indépendante du moteur. Ce chemin s’adresse aux installations déjà préparées, pas à un ordinateur neuf. L’application installée est `~/Applications/BandStudio.app` et les morceaux sont dans `~/Music/BandStudio`.

Les mises à jour `macos-x64` et `macos-arm64` ne contiennent que l’application et le code du moteur. Elles réutilisent les composants déjà installés. Aucun certificat Developer ID ni notarisation n’est fourni actuellement.

## Logs et signalement

- macOS : `~/Library/Logs/BandStudio/application.log`.
- Windows : `%LOCALAPPDATA%/BandStudio/Logs/application.log`, `webview.log` et `startup.log` (lancement par `BandStudio.exe`).
- Rotation : 1 Mo par fichier, trois archives. Actions, erreurs et traitements sont tracés sans les arguments contenant le morceau ou les paroles.
- **Réglages → Afficher les logs / Exporter le diagnostic / Signaler un bug sur GitHub**. L’export ne contient ni média ni projet. Les chemins personnels et URL sont masqués au mieux ; vérifier le fichier avant partage.
- Les journaux détaillés des moteurs restent dans `Analyses/<identifiant>/traitement.log` du projet et ne sont pas joints automatiquement.

## Mises à jour depuis main

Le workflow `BandStudio release` construit Windows, macOS Intel et Apple Silicon, vérifie l’interface Chromium/WebKit et le moteur portable. Après succès, il publie les archives immuables puis le manifeste `bandstudio-main/update.json`. Un ancien job ne remplace pas une version issue d’un main plus récent. Une panne crée un ticket CI, sans publier de nouveau manifeste.

Au démarrage, l’application vérifie ce manifeste sur GitHub. Le téléchargement HTTPS et le SHA-256 sont contrôlés ; les fichiers inattendus et chemins traversants sont refusés. La mise à jour est installée après fermeture, jamais pendant la lecture ou l’analyse. Une erreur de remplacement déclenche une restauration des fichiers déjà touchés. Les modèles, environnements Python, projets et préférences sont exclus du paquet. Une mise à jour des dépendances exige un installateur complet.

Désactiver **Mettre à jour automatiquement** avant une session sans changement souhaité. **Vérifier maintenant** permet un contrôle manuel ; si l’option automatique reste désactivée, l’application ne remplace pas ses fichiers à la fermeture. Réactiver l’option pour appliquer le paquet téléchargé à la prochaine fermeture.

Les sauvegardes sont dans `~/Library/Application Support/BandStudio/Updates` sur Mac et `%LOCALAPPDATA%/BandStudio/Updates` sous Windows. `last-update.json` identifie la sauvegarde de la dernière installation. Une installation manuelle initiale de la version 1.1 est nécessaire pour activer le système dans les anciennes versions.
