# BandStudio · guide de préparation

Sur un morceau déjà importé, **Préparer** vérifie les départs de section avec la grille et les attaques de l’enregistrement. Les repères corrigés à la main restent prioritaires. Quand une section entre avant la mesure suivante, la fiche affiche ses premiers accords et ses premiers mots sur une ligne **Entrée**, avec le numéro de mesure et le temps exact.

Dans **Éditeur du morceau → Accords**, tu peux ouvrir une grille publiée, comparer les accords à jouer et choisir celle à utiliser. La palette suit la transposition du lecteur et le capo. Quand tu places un accord, l’éditeur affiche sa valeur d’origine et l’accord à jouer. La fiche et le prompteur suivent le même réglage.

Pour les paroles, BandStudio essaie le titre du fichier puis une forme simplifiée, par exemple « Mon époque » pour un clip intitulé « Mon époque (Chap. II) ». Après LRCLIB et lyrics.ovh, la recherche peut consulter Paroles.net et Paroles2Chansons, retrouver le morceau dans le catalogue de l’artiste ou chercher sa page sur le Web. BandStudio compare le texte au chant et recale les mots sur l’enregistrement. Quand plusieurs passages concordent avec une édition synchronisée, ses repères aident à retrouver les répétitions. **Écoute ciblée** permet de réécouter les mots dont le placement reste incertain. Si un site est indisponible, BandStudio peut réutiliser sa référence déjà enregistrée pour ce morceau.

1. **Importer** un fichier audio. La préparation complète démarre automatiquement avec les moteurs installés, sans diminuer leur qualité. L’option peut être désactivée dans **Mes morceaux**. Le fichier original est conservé.
2. **Éditeur du morceau** regroupe les pistes, sections, paroles, accords et réglages du métronome. Une correction utilise le même document et le même historique d’annulation partout. La fiche et le prompteur renvoient vers cet éditeur.
3. **Écouter et corriger** : **Écoute ciblée** rassemble les mesures incertaines, sections ajustées, lignes de paroles à recaler et accords signalés. Choisir un passage ouvre le bon onglet ; **Écouter** joue son extrait puis restaure la boucle précédente ; **Modifier** ouvre l’éditeur existant. Écouter ne marque jamais automatiquement un passage comme validé. Les alertes de paroles sont conservées par ligne sur Mac, Windows et dans la préparation par lots, avec la même règle d’affichage dans l’éditeur et la fiche. **Préparer** reprend les étapes manquantes ; **Préparation détaillée** permet de relancer une analyse précise.
4. **Métronome** : la grille détectée suit les pulsations de l’enregistrement, complète les trous et prolonge les débuts/fins. Le tempo fixe reste un choix explicite. Lecture, décompte, mesures, fiche et REAPER utilisent cette même grille. Les pulsations extrapolées restent des estimations, à écouter lorsque l’enregistrement est ambigu.
5. **Exporter vers REAPER** : un clic vérifie les médias et la préparation actuelle, puis exporte ou ouvre le projet. Aucun export ne prétend avoir été validé à l’oreille automatiquement. La liste de vérification personnelle reste disponible. Chaque export crée un dossier distinct.

Sans changement de vitesse ni de hauteur, l’export conserve les WAV à l’identique et évite la copie audio intermédiaire. Les annonces vocales identiques sont réutilisées entre traitements ; un cache absent ou endommagé est reconstruit. Les réglages de qualité des moteurs restent inchangés. Les modifications non appliquées doivent être enregistrées avant une préparation ou un export.

## Nouveautés du 21 novembre 2026

Dans **Pistes & structure**, **Tout préparer** effectue la séparation disponible, les sous-pistes de batterie et de chant, les analyses manquantes, les paroles, puis la révision des sections et des accords Internet. Les améliorations automatiques sont enregistrées avant les guides. **Avant / Préparée** montre le résultat ; sélectionne un changement pour l’écouter. Un nouveau clic reprend les étapes manquantes. Les moteurs facultatifs doivent être installés dans **Réglages → Analyses locales**.

**Vérifier et compléter** reste un parcours facultatif : ses frises **Actuelle / Proposée** précèdent une application explicite. Les notes et réglages en cours doivent être enregistrés. Les modifications manuelles et repères protégés restent prioritaires ; les choix automatiques ne constituent pas une validation humaine. La validation finale de l’export se trouve dans **Projet REAPER**.

[Guide français](BANDSTUDIO_TUTORIEL_fr.md) · [English guide](BANDSTUDIO_TUTORIAL_en.md) · [Notes FR / EN](RELEASE_2026-11-21.md).

## Préparer une série

Dans **Préparer une série**, choisis le modèle de séparation, la qualité et la langue des paroles, puis ajoute plusieurs fichiers audio de ton ordinateur. Chaque fichier crée un morceau distinct. Les choix de préparation sont conservés avec chaque ajout. Utilise uniquement des morceaux que tu as le droit d’utiliser.

Clique sur **Démarrer la file** lorsque ta liste est prête. L’application traite un morceau à la fois : import, instruments, batterie détaillée, chant/chœurs, tempo, tonalité, structure et paroles selon les moteurs installés, révision finale des sections/accords, puis click et annonces. Le moteur de séparation doit être installé. Un échec est affiché sur la tâche concernée et les morceaux suivants continuent. **Réessayer** conserve les étapes déjà terminées.

Le morceau ouvert dans l’atelier reste indépendant de la file. Une lecture ou un autre traitement dans BandStudio met la file en attente ; elle reprend ensuite. **Pause** arrête l’étape en cours, qui sera relancée avec **Reprendre la file**. Les étapes terminées sont enregistrées sur disque. Après fermeture ou interruption de l’application, la file attend un nouveau clic : elle ne redémarre jamais seule. Laisse BandStudio ouvert et l’ordinateur éveillé pendant le traitement ; ce n’est pas un service fonctionnant application fermée.

Les morceaux entièrement préparés apparaissent dans **Mes morceaux**, prêts à écouter et à corriger avant validation. La file ne valide ni n’exporte automatiquement dans REAPER. **Retirer** annule une tâche inachevée ; retirer une tâche terminée de la liste conserve son morceau dans la bibliothèque. Les fichiers d’origine restent inchangés et doivent rester accessibles jusqu’à leur import.

## Traitement du morceau

| Usage | BandStudio | Limites |
|---|---|---|
| Séparer les instruments | Demucs 4/6 pistes | Guitare et piano seulement avec le modèle 6 pistes ; résidus possibles |
| Sous-pistes | DrumSep, chant principal/chœurs | Moteurs facultatifs ; pas tous les instruments spécialisés de Moises Pro |
| Écouter sa partie | Original, mix, solo et sans l’instrument choisi | Seuls les instruments disponibles sont proposés |
| Vitesse et hauteur | 50–150 %, ±12 demi-tons | Artefacts possibles ; Windows prépare les changements dans le cache |
| Tempo, tonalité, structure | Détection et corrections | Résultats à vérifier musicalement |
| Boucles, métronome, décompte | Passage précis, progression, guides séparés | La carte audio et les voix système restent à tester sur chaque ordinateur |
| Accords et paroles | Grilles Internet avec calage proposé, transcription locale, édition, capo, LRC/SRT | Recherche d’accords en ligne ; placement et transcription à vérifier |
| Exports | Mix, stems, MIDI batterie, PDF, projet REAPER | Les stems individuels restent au tempo et à la hauteur d’origine ; le projet REAPER applique les réglages validés |

Référence fonctionnelle : [traitement d’un morceau dans Moises](https://help.moises.ai/hc/en-us/articles/8583454469276-How-to-Upload-and-Edit-your-track-using-Moises). BandStudio est un projet indépendant. Le mastering et la génération musicale ne font pas partie de son atelier de préparation.

## Windows

Télécharger la version principale depuis les Releases, extraire le ZIP complet dans un dossier accessible en écriture et lancer `BandStudio.exe`. Installer les composants manquants depuis Réglages. Le paquet embarque Python et FFmpeg ; WebView2 et .NET Framework 4.8 sont nécessaires. Les essais CI utilisent Windows et un dossier avec accents/espaces, avec les bibliothèques marquées comme téléchargées par Windows. Le pilote de la carte son et les analyses IA demandent une vérification sur le PC cible.

### Erreur `Python.Runtime.Loader.Initialize` au démarrage

Windows peut transmettre aux DLL le marquage de provenance Internet du ZIP téléchargé. .NET refuse alors de charger `Python.Runtime.dll`, avant l’ouverture de l’interface. Le lanceur des nouveaux paquets prépare automatiquement les bibliothèques du moteur : il vérifie leur SHA-256 contre l’inventaire créé à la construction avant de retirer ce marquage. Les fichiers inconnus ou modifiés sont exclus ; aucune politique Windows n’est changée.

Pour une ancienne installation bloquée : télécharger le nouveau ZIP et l’extraire dans un nouveau dossier. Autre solution pour le ZIP officiel déjà téléchargé : clic droit → **Propriétés → Débloquer → Appliquer**, puis extraire à nouveau dans un nouveau dossier. Conserver les anciens projets. Une application qui ne démarre pas ne peut pas récupérer sa mise à jour automatique.

Si l’erreur persiste, joindre le fichier `%LOCALAPPDATA%/BandStudio/Logs/startup.log` au signalement, après vérification de son contenu. Le journal `application.log` indique aussi l’étape de démarrage et le nombre de bibliothèques préparées. Référence : [diagnostic du blocage des DLL téléchargées](https://github.com/pyinstaller/pyinstaller/issues/8294).

## NVIDIA et réparation des analyses Windows

La séparation des pistes (Demucs / DrumSep) et le rythme avancé (Beat This) utilisent CUDA lorsque PyTorch réussit un calcul de contrôle sur la carte. Sur une GTX 1650 de 4 Go, la séparation traite des segments de 4 secondes en gardant le morceau complet en mémoire CPU. Une erreur CUDA ou un manque de mémoire déclenche une reprise sur le processeur ; ce choix apparaît dans la progression et les logs. Les tests sans GPU vérifient la sélection et la reprise, mais ne mesurent pas les performances d’une GTX 1650 physique. Les autres outils utilisent leurs propres moteurs et peuvent rester sur le processeur.

Dans **Réglages → Analyses locales**, installer/vérifier **Séparer les stems** prépare la version CUDA de PyTorch lorsqu’une NVIDIA est détectée. Un pilote NVIDIA compatible est nécessaire. La présence de la carte seule ne prouve pas que l’environnement Python sait l’utiliser : les logs `analysis.environment` et `analysis.compute` indiquent le matériel détecté, les versions et le périphérique réellement sélectionné.

L’erreur `numpy.core.multiarray failed to import` peut venir de NumPy 2 avec soxr 0.3.7 dans l’environnement rythmique. Après la mise à jour de BandStudio, relancer **Installer / vérifier → Rythme avancé** remet NumPy 1.26.4, vérifie les imports et conserve les modèles et les morceaux. Attendre la fin d’une installation et fermer sa fenêtre avant d’en lancer une autre. Les nouveaux environnements de séparation utilisent aussi cette version compatible de NumPy.

## macOS

### Évaluer les analyses sans corrections manuelles

`tools/check_studio_automatic.py` rejoue les analyses dans une **nouvelle bibliothèque isolée**. Il copie les fichiers audio et l’identité titre/artiste, puis recrée un document vierge : aucun tempo corrigé, décalage de piste, repère, parole, accord, réglage de morceau, référence choisie, cache d’analyse ou validation n’est repris. Les pistes séparées existantes sont réutilisées ; ce contrôle ne mesure donc pas la qualité de séparation. Les originaux sont contrôlés par SHA-256 avant et après l’essai.

Exemple avec un moteur local déjà préparé et son Python disposant de NumPy et SoundFile :

```sh
python tools/check_studio_automatic.py --engine /chemin/Engine --library /chemin/BandStudio --output /chemin/nouvel-essai --song Apocalypse --song Hysteria --song Tostaky
```

Le dossier de sortie doit être nouveau. Chaque étape utilise le vrai worker ; les modèles restent locaux et les recherches de références Internet utilisent le titre et l’artiste. L’option `--reuse-raw-structure` autorise uniquement les segments bruts SongFormer dont la clé audio/modèles/code/environnement/paramètres et le checksum sont identiques. Elle ne reprend aucune section du document : toutes les corrections et comparaisons ultérieures sont rejouées. La réutilisation est déclarée dans le rapport ; une incompatibilité déclenche une nouvelle inférence.

`report.json` conserve les durées, erreurs, avertissements, provenance audio et résultats techniques. Sans annotations de référence indépendantes ou écoute comparative, ces résultats ne constituent pas une mesure de précision musicale. Les tests sur des projets corrigés restent utiles pour vérifier la conservation des modifications, mais ne servent pas de vérité terrain aux analyses automatiques.

Pour une installation de développement disposant déjà d’un moteur ReaCue local et de ses environnements Python, depuis la racine du dépôt :

```sh
python3 tools/build_studio_mac.py --prepare-runtime --source "$HOME/Documents/ReaCue"
python3 tools/install_studio_mac.py
```

Le programme de construction attend les environnements `.venv`, `.venv-demucs`, `.venv-structure`, `.venv-words`, `.venv-chords`, `.venv-drums` et leurs ressources, préparés par les installateurs existants. Il produit une copie indépendante du moteur. Ce chemin s’adresse aux installations déjà préparées, pas à un ordinateur neuf. L’application installée est `~/Applications/BandStudio.app` et les morceaux sont dans `~/Music/BandStudio`.

Les mises à jour `macos-x64` et `macos-arm64` ne contiennent que l’application et le code du moteur. Elles réutilisent les composants déjà installés. Aucun certificat Developer ID ni notarisation n’est fourni actuellement.

## Communauté Discord

[Rejoindre le serveur BandStudio](https://discord.gg/5UnQPdMUpR) · [Guide de support](../SUPPORT.md). Ce serveur est indépendant de BandPilot.

**Aide & Discord** ouvre les salons d’entraide, de démarrage, de suggestions et des nouveautés. Pour un bug : saisir le résumé, les étapes et le résultat attendu, cocher si utile le diagnostic compact, relire l’aperçu puis utiliser **Copier le rapport et ouvrir Discord**. Coller et envoyer le message dans `#rapports-de-bugs`. Première visite : rejoindre le serveur avant de rouvrir le salon.

Le diagnostic compact ne retient que les métadonnées techniques des six derniers événements (650 caractères maximum), sans messages d’erreur libres, chemins, noms de morceaux ou données du projet. Le message est limité à 2 000 caractères. Rien n’est publié automatiquement. Le diagnostic détaillé reste exportable pour être joint manuellement après vérification.

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


### Pochettes automatiques

À l’ouverture de BandStudio et après un import, les morceaux sans pochette sont recherchés en arrière-plan dans MusicBrainz et Cover Art Archive. Les tags titre/artiste/album du fichier sont conservés avant la conversion audio ; les anciens projets utilisent leur nom, avec les conventions « Artiste - Titre » et « Titre - Artiste ». Une correspondance exacte titre + artiste sur un album officiel permet l’ajout automatique. Les pochettes déjà présentes sont conservées.

Dans **Mes morceaux**, cliquer sur la pochette permet de corriger le titre et l’artiste, rechercher puis choisir un album, ou sélectionner une image locale. **Rechercher les pochettes manquantes** relance aussi les recherches précédemment infructueuses. **Suspendre** arrête la file après la recherche en cours ; la lecture et les analyses restent disponibles. Les résultats ne sont pas garantis pour tous les morceaux : un titre seul, un fichier mal nommé ou un album absent du catalogue peut nécessiter un choix manuel.

Seuls le titre et l’artiste sont envoyés au catalogue ; aucun audio ni chemin de fichier n’est transmis. `Artwork.jpg` et les métadonnées `Artwork.json` restent dans le projet, utilisables hors ligne. Les recherches infructueuses sont mémorisées sept jours (une heure en cas d’indisponibilité réseau), sauf relance manuelle. Le service est appelé avec un identifiant BandStudio, des requêtes espacées et des téléchargements bornés. Aucun compte ni clé API n’est nécessaire. Documentation : [recherche MusicBrainz](https://musicbrainz.org/doc/MusicBrainz_API/Search), [Cover Art Archive](https://musicbrainz.org/doc/Cover_Art_Archive/API).
