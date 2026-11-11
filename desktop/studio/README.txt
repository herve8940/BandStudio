BandStudio 1.1.0 — préparer les morceaux pour REAPER

DÉMARRER
Ouvre BandStudio dans Applications. Importe un fichier audio ou une vidéo, ou ouvre
un morceau existant. Les fichiers du morceau sont copiés dans un dossier .bandstudio.
Les projets existants sont conservés, y compris leurs anciennes pistes enregistrées.

LE PARCOURS
1. Importer : fichier local, dossier de projet, ou lien public pris en charge.
2. Séparer & analyser : stems, temps, mesures, structure, paroles et accords.
3. Pistes & structure : écouter, régler le mix, corriger les sections et les repères.
4. Click & cues : régler le premier temps, le métronome, les annonces et les décomptes.
5. Valider & envoyer : confirmer l’écoute, le calage et les guides, puis valider.
6. Ouvrir dans REAPER : créer un dossier autonome et ouvrir son projet .rpp.

Les analyses proposent un résultat ; l’écoute et les corrections manuelles restent
prioritaires. Les calculs sont locaux. Les modèles facultatifs nécessitent un premier
 téléchargement ; la séparation peut prendre plusieurs minutes sur un Mac Intel.

BIBLIOTHÈQUE ET PRÉPARATION COMPLÈTE
Mes morceaux affiche une liste avec pochette. Les images intégrées aux fichiers et
les miniatures des liens sont récupérées à l’import ; clique sur l’image pour choisir
une pochette lorsqu’elle manque. Supprimer déplace le projet et ses médias dans la
corbeille BandStudio (.Trash dans la bibliothèque). Restaurer le dernier morceau
supprimé permet de les récupérer ; une restauration ne remplace jamais un autre projet.

Tout préparer est disponible dans Séparer & analyser et Pistes & structure. Les étapes
prévues sont affichées : analyses installées, puis click et annonces. Les stems déjà
présents, le calage protégé, la tonalité renseignée et les corrections manuelles sont
conservés. Une erreur ou une annulation arrête la suite et conserve les étapes terminées.
Installe les moteurs manquants dans Réglages avant de recommencer. La validation finale
se fait après écoute.

Sous Windows, choisis Français ou English dans Click & cues. Système utilise une voix
locale OneCore, ou une voix de bureau de la même langue si nécessaire. Réglages → Voix
Windows ouvre l’installation des voix françaises et anglaises. Aucun texte n’est envoyé
à un service en ligne. Un débit de 180 mots/minute convient aux annonces.

STEMS ET ÉCOUTE
Demucs : 4 pistes, 4 pistes affinées, ou 6 pistes (guitare et piano expérimentaux).
DrumSep : grosse caisse, caisse claire, toms, cymbales/charleston. Chant principal et
chœurs : UVR, à partir du stem de chant. Aucun modèle ne garantit une isolation parfaite.
Les pistes gardent leur niveau relatif. Original et stems ne sont pas superposés dans
le mix. Mute, solo, volume, panoramique et départ de chaque piste restent modifiables.
Le lecteur propose Original, Mix, Sans mon instrument et Mon instrument seul ; vitesse 50–150 %,
transposition ±12 demi-tons. Les voix des guides conservent leur hauteur.
Espace : lecture/pause. Flèches : mesure précédente/suivante. Maj + flèches : repères.
M : ajouter un repère. Les boucles permettent de vérifier un passage avant validation.

STRUCTURE ET GUIDES
Sections : renommer, protéger, scinder, fusionner, modifier les limites. Les corrections
manuelles sont conservées lors d’une nouvelle analyse. Repères : position exacte,
nom et annonce personnalisée. Les guides ont chacun leur volume et leur panoramique.
Vérifie le premier temps dans Click & cues. Pour un morceau quantisé, choisis le tempo
fixe. La grille détectée suit les pulsations de l’enregistrement. Une grille absente
ou incorrecte doit être réglée avant validation. Applique les réglages modifiés.
Paroles & accords permet de relire et corriger le texte, les horaires et la tonalité.

VALIDATION ET REAPER
Les trois confirmations de l’écran Valider & envoyer valident ton écoute. BandStudio
vérifie aussi les médias, la grille et les limites des sections. La validation et les
réglages de vitesse, transposition et mode d’écoute sont enregistrés dans le projet.
Une correction des pistes, du mix, des repères ou des réglages demande une nouvelle
validation. L’export vérifie encore que la préparation et les médias correspondent.

Chaque envoi crée un nouveau dossier dans Exports, sans remplacer un ancien export.
Le projet contient des pistes audio indépendantes, les états muet/solo du mix, les
volumes, panoramiques, régions, repères, le tempo et les guides choisis. Vitesse et
transposition sont appliquées aux médias exportés ; les repères et annotations suivent
la même échelle de temps. Les sources du morceau ne sont pas modifiées.
Le décompte initial laisse aux musiciens le temps de se préparer avant le départ.
Il décale ensemble les pistes, le tempo et les régions. Son nombre de mesures et
son inclusion dans les exports se règlent dans Click & cues.
Un fichier d’annotations conserve paroles, accords et batterie ; validation.json décrit
la préparation exportée. Ces fichiers accompagnent le .rpp et son dossier Audio.
Sans REAPER installé, l’export reste disponible avec Afficher le dernier export.
Les changements faits ensuite dans REAPER restent dans cette session REAPER : aucun
contrôle à distance ni synchronisation permanente ne relie les applications.

EXPORTS COMPLÉMENTAIRES
Mix WAV à la vitesse et transposition écoutées ; stems WAV/FLAC/MP3/AAC au tempo et
à la hauteur d’origine, avec pistes.json ; paroles LRC/SRT, sections et repères CSV,
batterie MIDI, fiche PDF et ZIP du projet. Ces exports ne remplacent pas l’envoi validé.

INSTALLATION ET CONSERVATION
Mac : ~/Applications/BandStudio.app ; bibliothèque : ~/Music/BandStudio.
Une mise à jour conserve l’application précédente et son moteur dans
~/Library/Application Support/BandStudio/PreviousVersions et les dossiers Engine-*.
Quitte l’ancienne application avant de lancer la version mise à jour.
Windows : décompresse le dossier complet et lance BandStudio.exe. Les moteurs
facultatifs s’installent dans Réglages → Analyses locales. La bibliothèque existante
BandStudioDev est conservée pour éviter de perdre l’accès aux morceaux précédents.

BandPilot reste indépendant et consacré à la console. Les commandes croisées,
l’enregistreur intégré et la télécommande REAPER ont été retirés du parcours.
L’enregistrement, le montage final et le mixage se poursuivent dans REAPER.

DIAGNOSTICS ET MISES À JOUR
Réglages permet de consulter les logs locaux, exporter un diagnostic et ouvrir un
signalement GitHub. Vérifie le diagnostic avant de le partager : aucun audio ni
projet n’y est inclus. Les mises à jour publiées depuis main sont téléchargées
automatiquement puis appliquées à la fermeture, après vérification de leur empreinte.
Les modèles, projets et préférences sont conservés. Désactivation possible dans Réglages.
