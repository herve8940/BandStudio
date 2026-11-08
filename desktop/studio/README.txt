BandStudio 0.2 — atelier autonome pour répéter et enregistrer

DÉMARRER
L’application est installée dans ~/Applications/BandStudio.app.
Après une mise à jour, quitte la fenêtre de l’ancienne version puis rouvre BandStudio.
Les morceaux sont conservés dans ~/Music/BandStudio, dans des dossiers .bandstudio.
L’ancienne version de l’application est conservée dans Application Support/BandStudio/PreviousVersions.

RETROUVER LES APPELS ET LES DÉCOMPTES
Ouvre Guidage. Par défaut : annonces activées, deux mesures avant la lecture, voix sur la
 dernière mesure et compte de quatre temps avant chaque région. L’anticipation minimale des
annonces est de huit temps. Une annonce est avancée si nécessaire pour ne pas chevaucher le compte.
Le métronome continu est désactivé par défaut. Chaque guide a son volume et son panoramique.
Choisis la voix macOS (Thomas en français), la langue des nombres, le débit et les temps par mesure.
Clique Appliquer au morceau. La préparation des fichiers vocaux peut prendre quelques instants.
Au prochain départ, le nombre de temps restant s’affiche aussi dans le prompteur.
Pour ne pas attendre de décompte au démarrage, règle Mesures avant le départ sur 0.
Un décompte après un saut et un décompte entre répétitions peuvent être activés séparément.
Le texte de chaque annonce et son activation se règlent en modifiant la section ou le repère.
Les réglages sont enregistrés par morceau. Utiliser pour les futurs imports en fait ton modèle.

STEMS ET STRUCTURE
Préparer propose trois modèles : htdemucs (4 pistes), htdemucs_ft (4 pistes affinées, plus lent),
htdemucs_6s (6 pistes, guitare et piano expérimentaux). Le piano peut contenir des fuites d’autres instruments.
Calcul rapide, équilibré ou approfondi. Aucun modèle ne garantit une séparation parfaite.
Les stems conservent leur niveau relatif. Le mode Mix ne superpose pas l’original et les stems.
Chaque piste possède un volume, mute, solo, pan, nom, rôle et position modifiables.
Le lecteur propose Original, Mix, Sans batterie et Batterie seule, vitesse 50–150 % et ±12 demi-tons.
La transposition ne change pas la hauteur des voix de guidage.
La structure SongFormer est une proposition. Les breaks courts et les corrections manuelles sont préservés.
Sections : modifier, protéger, scinder à la tête de lecture, fusionner avec la suivante, supprimer.
Repères : créer, déplacer, renommer, personnaliser l’annonce. Notes et historique d’annulation disponibles.
Boucle : section ou plage exacte, compte à chaque reprise en option, accélération par paliers configurable.

IMPORTER
Importer un morceau : conversion locale par FFmpeg, avec extraction de la piste audio des vidéos.
Formats usuels : WAV, MP3, AAC/M4A, AIFF/AIFC, FLAC, OGG/Vorbis, Opus, WMA, CAF, MP4, MOV, MKV, WebM…
La prise en charge dépend du codec réel ; les fichiers endommagés ou protégés peuvent être refusés.
Importer un lien : YouTube, liens audio directs et sites pris en charge par yt-dlp.
Un lien correspond à un morceau, pas à une playlist entière. Pas de cookies du navigateur ni de connexion
à un compte. Contenus publics, non protégés, pas de flux en direct ; limite d’import 1 Go et 3 heures.
Les changements des sites peuvent rendre certains liens indisponibles. Les fichiers importés restent locaux.

REAPER
Projet REAPER crée un dossier autonome avec un .rpp et des copies des médias WAV.
Les régions, repères, volumes, panoramiques et le mix écouté sont conservés. Les solos sont traduits en
états muet pour que les guides restent audibles. Les pistes restent indépendantes dans REAPER.
Le décompte initial, lorsqu’il est inclus, décale ensemble les médias, les régions et le tempo.
Le RPP garde le tempo et la tonalité d’origine. Le WAV du mix utilise la vitesse et la transposition du lecteur.
Afficher l’export révèle le fichier dans Finder. REAPER n’est pas lancé automatiquement.
Ouvrir accepte aussi les .rpp : les clips audio sont copiés, leurs offsets et vitesses sont appliqués,
les régions, repères et changements de tempo sont repris. Le projet source n’est jamais modifié.
Les effets de plug-ins, automations, routages complexes, prises alternatives et instruments MIDI ne sont pas
reproduits. Pour préserver leur son, rends les pistes en audio dans REAPER avant l’import.
Un fichier d’annotations accompagne les exports. Il permet de reprendre les paroles, accords et notes MIDI
si le RPP exporté n’a pas été modifié. Après modification du RPP, ces annotations doivent être resynchronisées.

PROMPTEUR, PAROLES, ACCORDS ET BATTERIE
Whisper fournit des lignes et mots synchronisés. Utilise de préférence le stem de chant.
Les paroles et accords peuvent être ajoutés, corrigés ou supprimés avec leurs heures exactes.
Les corrections manuelles restent prioritaires lors d’une nouvelle analyse.
Le prompteur affiche la section actuelle, la prochaine, les paroles, le mot actuel et l’accord transposé.
ADTOF transcrit la batterie en cinq familles : grosse caisse, caisse claire, toms, charleston, cymbales.
La grille de la mesure courante permet d’ajouter ou retirer une frappe. L’export MIDI utilise le canal GM 10.
Ces analyses sont des propositions. Leurs essais techniques ne prouvent pas leur justesse sur tous les morceaux.
Les setlists, dans Morceaux, organisent la bibliothèque et l’ordre de répétition. Chaque morceau s’arrête à sa fin.

ENREGISTRER
Choisis l’entrée dans les réglages audio du Mac. Toutes les entrées du périphérique choisi deviennent des pistes.
Enregistre à 100 %, sans transposition et sans boucle. Le retour logiciel est désactivé.
Le décompte est entendu avant le morceau et sa durée est soustraite au placement de la prise.
La latence de l’interface reste à contrôler et à corriger avec le champ Départ de la prise.
L’enregistrement sur une console XR dépend de son choix comme périphérique audio dans macOS.
Le contrôle des paramètres de la console et la liaison directe des analyses avec BandPilot ne sont pas intégrés.

ÉTAT RÉEL DE CETTE VERSION
Ce n’est pas une reproduction de l’ensemble de la gamme Moises. Voir capabilities.json pour l’inventaire
recherché et son statut. Pas de génération de musique ou de voix, mastering automatique, vidéo synchronisée,
séparation dialogue/effets, plug-in de DAW, synchronisation cloud ou séparation de l’audio système en direct.
Le mode scène sur téléphone, les télécommandes réseau, les lumières grandMA3 et le timecode LTC/MTC de
l’outil précédent ne sont pas encore portés dans cette application autonome. Les projets REAPER existants
et leur environnement sont conservés. Le lanceur BandPilot est présent ; sa liaison directe reste à développer.
La reconnaissance de tonalité, le capo, le PDF de partition et l’édition fine des mots restent à intégrer.

VALIDATION
Tests Python : frontières des sections, appels et décomptes réellement audibles dans les WAV, subdivisions,
import de huit formats, URL, export MIDI, RPP portable et aller-retour avec offsets/vitesse et annotations.
Tests navigateur : commandes liées au bon projet, édition des réglages/pistes/annotations/setlists et affichage
aux largeurs 960, 1024 et 1360 px. Les captures sont des essais web locaux, pas une validation de la fenêtre native.
Tests AVAudioEngine hors ligne : modes d’écoute, ralentissement, durée de décompte, voix identique à +12 demi-tons.
Essais de modèles : Demucs 4/6/affiné, SongFormer, rythme, Whisper, accords et batterie sur un extrait réel.
Import YouTube : Big Buck Bunny, chaîne officielle Blender. Aucune garantie sur tous les liens futurs.
La lecture physique, les entrées de ta console et l’ouverture du RPP dans REAPER restent à confirmer à l’usage.

DÉVELOPPEMENT
python3 tools/build_studio_mac.py --prepare-runtime
python3 tools/install_studio_mac.py --update
PLAYWRIGHT_BROWSERS_PATH=/private/tmp/reacue-test-browsers .venv-test/bin/python -m pytest -q tests/test_standalone_studio.py tests/test_studio_services.py
La compilation copie les runtimes locaux existants ; aucune dépendance à l’installation précédente à l’exécution.
Les moteurs de modèles gardent leurs licences d’origine, notamment les restrictions non commerciales de
SongFormer et ADTOF. Examiner THIRD_PARTY_NOTICES.md avant redistribution de modèles ou commercialisation.
