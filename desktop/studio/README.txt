BandStudio 0.5.0 DEV — atelier autonome pour répéter et enregistrer

DÉMARRER
L’application est installée dans ~/Applications/BandStudio.app.
Après une mise à jour, quitte la fenêtre de l’ancienne version puis rouvre BandStudio.
Les morceaux sont conservés dans ~/Music/BandStudio, dans des dossiers .bandstudio.
L’ancienne version de l’application est conservée dans Application Support/BandStudio/PreviousVersions.

RETROUVER LES APPELS ET LES DÉCOMPTES
Ouvre Guidage. Par défaut : annonces activées, deux mesures avant la lecture, voix sur la
 dernière mesure et compte de quatre temps avant chaque région. L’anticipation minimale des
annonces est de huit temps. Une annonce est avancée si nécessaire pour ne pas chevaucher le compte.
Premier temps de mesure sert de repère pour le clic accentué et le comptage du prompteur.
En mode détecté, sa position choisit le temps le plus proche comme « 1 » ; les pulsations restent en place.
La détection simple trouve les pulsations. Détecter les temps et mesures utilise Beat This en local.
Le premier temps est proposé seulement si plusieurs mesures régulières concordent. Les introductions
sans pulsation et changements de signature restent à contrôler. Les anciennes grilles sont protégées
par défaut : déverrouille le calage dans Guidage pour lancer une nouvelle analyse.
Placer le « 1 » à la tête de lecture et Taper le tempo permettent de corriger le repère ou le tempo fixe.
Le métronome continu est désactivé par défaut. Chaque guide a son volume et son panoramique.
Choisis la voix macOS (Thomas en français), la langue des nombres, le débit et les temps par mesure.
Clique Appliquer au morceau. La préparation des fichiers vocaux peut prendre quelques instants.
Le décompte des régions suit les clics de la grille, même quand une frontière de région tombe entre deux temps.
Il utilise les temps disponibles avant la région ; il ne crée pas de temps après la fin de la détection.
Actualiser les guides force leur recalcul. Les guides des versions précédentes sont régénérés avant la lecture.
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

ENREGISTRER ET PILOTER DEPUIS BANDPILOT
Prises : crée une session vide pour toute la répétition, ou ouvre un morceau pour jouer dessus.
Choisis explicitement l’interface audio USB, arme les entrées voulues et nomme-les. Appliquer mémorise
ce plan par projet. Capture mono WAV 24 bits par entrée, à la fréquence de l’interface, jusqu’à 32
entrées armées et 128 pistes par projet. La XR18 doit être reliée en USB à l’ordinateur ; sa connexion
réseau sert au contrôle dans BandPilot, pas au transport des pistes audio.
Modes : répétition entière sans lecture, prise sur morceau, ou plage de punch avec lecture avant.
Le punch conserve la capture complète et ajoute des pistes découpées aux limites de la plage.
Les prises utilisent une référence d’horloge audio ; la compensation manuelle en ms avance la prise
quand elle est positive. Vérifier la latence réelle avec l’interface. Retour d’écoute sur la console,
pas de monitoring logiciel. Vitesse 100 %, transposition 0 et boucle désactivée pendant la capture.

Active Relier BandPilot dans Prises, puis utilise Enregistrement → BandStudio dans BandPilot
2.3.4 DEV compatible. Le plan de la console peut fournir les noms et numéros USB ; vérifie ensuite
l’interface et les entrées avant REC. Lecture, pause, navigation, REC, arrêt et repères passent par
un canal local distinct du pont REAPER. Aucun changement de routage ou de gain XR n’est appliqué.
La liaison est locale à cet ordinateur, désactivée à chaque démarrage et protégée contre les requêtes
périmées, les changements de projet et les répétitions de commande. Les comptes BandPilot autres que
l’administrateur n’y ont pas accès. Ne pas lancer deux fenêtres BandStudio pour la même session.
Un arrêt perdu n’est pas répété automatiquement : vérifier l’état réel dans BandStudio.

LECTEUR
Début/fin, repère précédent/suivant, déplacement d’une mesure et position exacte en secondes.
Raccourcis : Début/Fin, flèches gauche/droite pour une mesure, Maj+flèches pour les repères, M pour
un repère, Espace pour lecture/pause. Les boucles, ralentissement et transposition restent présents.
Outils → Extension REAPER exporte un ReaScript de télécommande, à charger dans les Actions REAPER.
Il pilote BandStudio, sans synchroniser les deux horloges audio ni remplacer un plug-in VST3/AU.

ÉTAT RÉEL DE CETTE VERSION
Ce n’est pas une reproduction de l’ensemble de la gamme Moises. Voir capabilities.json pour l’inventaire
recherché et son statut. Pas de génération de chant intelligible ou conversion vocale, mastering automatique par référence, vidéo synchronisée,
séparation dialogue/effets, plug-in de DAW, synchronisation cloud ou séparation de l’audio système en direct.
Le prompteur en lecture seule est accessible sur téléphone via le même réseau local. La télécommande sur un autre ordinateur, les lumières grandMA3 et le timecode LTC/MTC ne sont pas encore disponibles. Les projets REAPER existants
et leur environnement sont conservés. La liaison de transport/enregistrement BandPilot est disponible ; la correction automatique de la XR ne l’est pas.
La tonalité estimée, le capo, les horaires des mots et la fiche PDF sont disponibles. La fiche PDF
n’est pas une partition musicale gravée. Le mastering manuel propose égalisation, compression et largeur stéréo avant la normalisation.
La comparaison et l’égalisation automatiques par référence restent absentes.

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

NOUVEAUTÉS 0.4 — OUTILS LOCAUX
Préparer → Comprendre la batterie → Séparer les éléments de batterie : DrumSep fournit grosse caisse,
caisse claire, toms et cymbales/charleston. Le charleston n’est pas isolé des cymbales par ce modèle.
La batterie complète reste dans le projet pour la transcription et la comparaison : utilise son Solo.
Le mix normal utilise ses quatre sous-pistes sans superposer la batterie complète. Sans batterie coupe
aussi ces quatre pistes. La qualité reste dépendante du morceau ; une fuite est toujours possible.

Prompteur : détecter ou corriger la tonalité et régler le capo. Le capo change uniquement les accords
affichés, y compris les basses d’accords ; la transposition du lecteur agit sur le son. Les mots et
leurs horaires se corrigent dans Modifier une entrée → Modifier les horaires de chaque mot.
Répartir les mots fournit des horaires approximatifs, à corriger à l’écoute.

Outils : exports séparés WAV 24 bits, FLAC, MP3 320 kbit/s et AAC 256 kbit/s ; chaque stem garde son
tempo et sa hauteur d’origine. pistes.json documente les offsets et le mix. Import et export SRT/LRC,
ZIP portable du projet et fiche PDF (structure, cues, accords, paroles, notes). L’import de paroles
préserve les plages existantes par défaut ; Remplacer les lignes existantes permet de les remplacer.
La fiche applique transposition et capo aux accords tout en gardant les horaires d’origine.

Niveau final : normalisation EBU R128 en deux passes et plafond de crête vraie, sortie WAV 24 bits /
48 kHz. Utilise le mode d’écoute, les niveaux et la transposition du lecteur, sur le morceau entier,
sans guides ni décompte. Les sources restent inchangées. mesures.json conserve les mesures avant/après.
Rapport audio : crête, RMS, dynamique crête/RMS, offset continu et échantillons proches du plein niveau.
Ce rapport ne diagnostique pas à lui seul une saturation et ne règle aucun paramètre sur la XR.

Prompteur téléphone : Activer le prompteur local, puis scanner le QR code depuis le même Wi-Fi.
Le lien affiche uniquement l’état du prompteur, sans pistes audio, fichiers ni télécommande. Il change
à chaque nouvelle session. Arrêter le partage ou quitter l’application ferme le service. Un pare-feu
ou un réseau isolant les appareils peut empêcher l’accès. Le Wi-Fi ajoute une latence d’affichage ;
ce prompteur n’est pas une source de synchronisation audio. Aucun partage réseau au démarrage.

MODÈLES AJOUTÉS
Beat This 1.1.0 / final0 : MIT, https://github.com/CPJKU/beat_this
DrumSep 49469ca8 : dépôt MIT, https://github.com/inagoy/drumsep
Empreintes SHA-256 vérifiées par les installateurs et avant l’inférence. Téléchargement initial depuis
les auteurs ; traitement ensuite hors ligne. Sur ce Mac, les deux modèles sont inclus dans le moteur
installé. Sur Windows, installer Séparer les stems puis Rythme avancé / Éléments de batterie.
Cette version ne prétend pas reproduire toute la gamme Moises. Consulter capabilities.json.

NOUVEAUTÉS CRÉATIVES 0.5
Outils → Séparer le chant et les chœurs : UVR MDX Karaoke 2 travaille sur le stem de chant existant.
Les deux pistes reprennent son gain, pan et offset ; le chant complet est exclu du mix tant que les
sous-pistes sont présentes, sauf Solo. Des fuites restent possibles, aucune garantie de séparation
parfaite. La somme des deux sous-pistes reconstitue la source sans normalisation indépendante.

Outils → Créer un accompagnement : MusicGen Small, modèle officiel fixé à la révision
4c8334b02c6ec4e8664a91979669a501ec497792. Description, durée de 2 à 20 secondes et variation (seed).
Le modèle travaille hors ligne. Il ne garantit ni tempo exact, ni respect parfait du texte, ni chant
intelligible. Sur le Mac Intel de développement : environ 64 secondes pour un premier extrait de
2 secondes, chargement compris. La piste est muette si le projet possède déjà de l’audio ; Solo pour
l’écouter. Métadonnées dans Analyses/generation.json du traitement. Modèle CC-BY-NC 4.0 : usage non
commercial. Ce n’est pas un générateur de chanson complète. Aucune voix de personne n’est clonée.

Mastering local : égalisation grave/médium/aigu, compression à seuil/ratio/attaque/relâchement
réglables, largeur stéréo, normalisation LUFS et plafond de crête vraie. Les sources restent intactes.
Les réglages et mesures avant/après accompagnent le WAV exporté ; juger le résultat à l’écoute.

VALIDATION 0.5
Tests de canaux synthétiques (18 entrées, sélection 1/3/18), fichiers mono 24 bits synchronisés,
punch à l’échantillon, commandes locales périmées/rejouées, projet changé, contrôle d’accès BandPilot,
UI, mastering réel et régressions. MusicGen et UVR exécutés réellement en local. Aucune capture
physique XR18 ni mesure de latence matérielle n’a été faite : à vérifier lors de la première prise.
