# BandStudio · tutoriel de préparation et de correction

[English](BANDSTUDIO_TUTORIAL_en.md) · [Installation et guide](BANDSTUDIO.md) · [Site](https://herve8940.github.io/BandStudio/)

Mis à jour le 20 novembre 2026. Ce tutoriel concerne l’application autonome BandStudio sur macOS et Windows.

**Pour débuter : [ouvrir le tutoriel visuel en 8 étapes](https://herve8940.github.io/BandStudio/tutoriel.html)** — import, tempo, premier « 1 », régions, guides, validation et export REAPER. Utilise les boutons Précédent et Suivant pour avancer à ton rythme.

## 1. Importer et préparer

Ouvre un fichier audio de ton ordinateur. Pour plusieurs morceaux, utilise **File de préparation**, ajoute les fichiers puis clique sur **Démarrer la file**. La file ne démarre jamais seule après ouverture de l’application.

Dans **Séparer & analyser**, choisis les moteurs installés ou **Tout préparer**. Les résultats déjà présents sont réutilisés et les corrections protégées sont conservées. Les analyses locales disposent d’un cache pour éviter de refaire un calcul identique ; une modification de l’audio, du modèle ou des paramètres peut nécessiter un nouveau calcul.

À l’import, BandStudio tente de caler la grille avant de préparer les guides. Les paramètres de calage d’un autre morceau ne sont pas repris. Une indication « à vérifier » signifie que l’écoute reste nécessaire, particulièrement pour le premier « 1 ».

## 2. Vérifier le premier temps et le décompte

Ouvre **Click & cues** et écoute le début avec le métronome. Vérifie le premier temps, le nombre de temps par mesure et le mode de grille : détectée pour conserver les variations du morceau, fixe si tu imposes un tempo constant. Corrige les paramètres si le « 1 » ne tombe pas au bon endroit.

Le décompte suit la grille enregistrée, y compris ses variations. Il peut commencer pendant le silence initial et accompagner une levée ; l’audio du morceau reste entier. Écoute également une reprise au milieu du morceau. Si une intro automatique a été recalée, vérifie son départ ; les sections corrigées ou validées restent protégées.

Les nouvelles analyses corrigent les détections isolées faibles ou doublées de l’introduction quand la suite confirme un rythme régulier. Cette règle s’applique à tous les morceaux compatibles. Écoute le début, le milieu et la fin : un décalage constant invite à vérifier le premier « 1 » ; une dérive progressive invite à revoir le tempo ou la grille. N’impose pas un tempo fixe à un enregistrement qui varie. Après une correction juste à l’écoute, coche **Protéger le calage contre une nouvelle analyse**. Une grille déjà protégée n’est pas remplacée par une mise à jour.

## 3. Ajuster les sections et les cues

Dans **Pistes & structure**, choisis la vue **Pistes** pour le mix ou **Structure** pour parcourir les sections. La vue Structure affiche leur départ, leur fin, leur longueur et leur validation ; **Modifier** ouvre la section et **↻** la met en boucle. La vue d’ensemble colorée permet de rejoindre un passage.

La recherche filtre la vue courante. Dans Pistes, filtre **Instruments**, **Original** ou **Guides** ; **Compact** réduit la hauteur des pistes et **Masquer l’inspecteur** libère la largeur. Ces commandes ne changent pas le mix.

Pour affiner un repère :

1. Utilise **＋**, **−** et **Tout** pour zoomer. **Sélection** (touche **F**) cadre la section choisie. **L** active la boucle et **Alt + ← / →** parcourt les repères hors des champs de saisie. Le curseur **Parcourir le morceau** déplace la fenêtre visible ; **Suivre la lecture** garde la lecture à l’écran.
2. Choisis le calage **Mesure** ou **Temps**, puis fais glisser une frontière de section ou un cue. Tu peux aussi utiliser **−1 mesure**, **+1 mesure**, **−1 temps** et **+1 temps** dans le panneau **Un repère à la fois**.
3. Clique sur **Écouter autour** pour vérifier l’annonce et l’entrée. Le nom du repère ouvre son édition.
4. Clique sur **Valider et suivant** pour passer au repère suivant. Le compteur indique ce qui reste à écouter. Déplacer un repère annule sa validation.

Une frontière commune conserve la continuité des deux sections. Les corrections sont enregistrées avec le morceau et peuvent être annulées/rétablies. Cette validation par repère ne remplace pas la validation finale avant l’export REAPER.

### Utiliser « Vérifier et compléter »

Dans le même écran **Pistes & structure**, clique sur **Vérifier et compléter** pour comparer les sources disponibles avec l’audio et tes repères. Les étapes de préparation manquantes peuvent prendre du temps. Les sections et accords proposés ne remplacent ta préparation qu’après validation.

1. Lis le récapitulatif et ouvre **Sources consultées**. Une grille d’accords peut être disponible même si les repères minutés de DRUMY n’ont pas été récupérés. Une liste de sections sans horaires n’indique pas où elles commencent dans ton enregistrement.
2. Clique sur **Écouter les passages** lorsqu’il y en a. Vérifie les accords, leurs positions et les entrées proposées. « 0 passages à écouter » ne certifie pas tout le morceau ; écoute aussi le mix, la grille et les guides.
3. Si tu préfères ta préparation, clique sur **Garder le parcours actuel**. Si la proposition convient et que l’écoute finale est faite, **Valider et exporter vers REAPER** applique la proposition et crée le projet en une action. **Afficher l’export** permet de retrouver le fichier `.rpp`.

Le bandeau **Aucune amélioration proposée — préparation actuelle conservée** signifie qu’aucun changement n’a été proposé. Le bouton devient **Exporter la préparation actuelle vers REAPER**. Une préparation retrouvée pour le même enregistrement reste, elle aussi, à confirmer avant export. Cette aide ne marque pas automatiquement chaque repère comme vérifié à l’écoute ; le parcours classique reste disponible.

Les nouvelles analyses SongFormer compatibles bénéficient d’un ajustement fin appris sur des morceaux annotés : déplacement maximal de 250 ms, abstention en cas de désaccord. Il ne renomme pas les sections et ne retrouve pas les transitions manquantes. Il conserve les corrections manuelles et les sections validées. Il s’active uniquement avec les poids vérifiés, une fenêtre d’analyse de 60 secondes et un morceau de 2 à 10 minutes ; les autres analyses conservent leurs propositions initiales. Ce correcteur concerne les frontières de sections, pas le tempo ni l’anticipation des annonces vocales. [Résultats et protocole](CUE_CORRECTOR_TRAINING.md#résultats-du-lot-réservé-et-distribution).

## 4. Doser les guides

Dans **Pistes & structure**, ouvre **Mix des guides** pour afficher les réglages. Les quatre niveaux **Métronome**, **Appels**, **Cues** et **Décompte** se règlent séparément. **Muet** coupe ou rétablit le niveau de chaque guide. Modifier un volume ou cocher la validation d’un repère ne relance pas une analyse IA ni la fabrication des guides. Modifier le placement d’un repère peut demander leur régénération.

## 5. Corriger la fiche du morceau

**[Suivre le tuto visuel Fiche morceau → PDF](https://herve8940.github.io/BandStudio/fiche-morceau.html)** — 8 étapes pour corriger les accords, les paroles, leur placement et exporter la fiche.

Ouvre **Fiche morceau**. La fiche rassemble l’identité du morceau, la pochette disponible, le tempo, la tonalité, les sections, les accords et les paroles, mesure par mesure. Choisis un passage dans la liste ; clique sur une mesure ou un titre de section pour déplacer le curseur d’écoute.

- Clique sur un accord ou une ligne de paroles pour modifier le texte et sa position. **Détails** affiche les repères supplémentaires.
- Utilise les champs **Mesure de début**, **Temps**, **Mesure de fin**, **Temps**, les boutons de déplacement ou **Placer au curseur**. Déplacer une ligne conserve les décalages de ses mots synchronisés.
- **+ Accord** et **+ Paroles** ajoutent une annotation. Lorsqu’un accord en remplace d’autres sur une portion, les parties situées en dehors de cette portion restent conservées.
- **Importer des paroles** permet d’utiliser ton fichier. **Annuler** et **Rétablir** permettent de revenir sur les corrections.
- Dans **Séparer & analyser** ou **Paroles & accords**, lance la recherche de grille Internet. Vérifie d’abord le titre et l’artiste. Les sources trouvées restent séparées : **Ouvrir la grille** affiche la page d’origine, **Utiliser cette grille** choisit celle à caler. La recherche nécessite Internet et certaines sources peuvent être indisponibles.
- Les accords de la source sont proposés sur la grille rythmique du morceau. Écoute et corrige leur placement ; un calage proposé ne garantit ni la bonne version ni le bon accord. **Caler sur le temps / contretemps** aide au placement. Les corrections manuelles restent conservées.
- **Autres sources sur Internet** et les recherches de paroles ouvrent le navigateur. Les paroles de ces sites ne sont pas importées automatiquement.

Si aucune grille n’est trouvée, vérifie que l’artiste est bien le musicien ou le groupe, pas le nom d’une chaîne vidéo, puis relance la recherche. BandStudio nettoie les mentions telles que « HD Video » et reconnaît plusieurs séparateurs artiste/titre. Pour un résultat partiel, une nouvelle recherche après cinq minutes réessaie les sources manquantes tout en conservant les grilles trouvées. **Référence non récupérée** indique un problème d’accès à cette source, pas l’absence d’accords partout sur Internet. Vérifie toujours qu’il s’agit de la même version du morceau.

La fiche modifie les annotations du morceau ouvert. Les accords estimés et la transcription demandent une vérification à l’écoute ; une ligne sans synchronisation mot par mot reste entière à sa position de départ.

## 6. Exporter une fiche PDF et le projet

Clique sur **Exporter la fiche PDF**. La grille imprimable reprend les sections, les mesures, les accords, les paroles, les cues et les notes. Elle respecte le calage, la transposition et le capo pour les accords affichés. Choisis le nom et l’emplacement de la copie ; le PDF s’ouvre ensuite dans le lecteur de ton système. Si tu annules cette copie, le PDF généré reste dans le dossier **Exports** du morceau. **Afficher l’export** permet de le retrouver si l’ouverture automatique échoue.

Pour le parcours classique, dans **Valider & envoyer**, écoute et confirme le mix, la grille et les guides, puis exporte vers REAPER. Si tu as utilisé **Valider et exporter vers REAPER** dans l’aide de structure, l’export est déjà créé : retrouve-le avec **Afficher l’export**. Garde le `.rpp` et son dossier **Audio** ensemble. Pour bénéficier d’une correction dans un ancien projet REAPER, refais l’export.

## Mettre à jour ou demander de l’aide

Dans **Réglages**, utilise **Vérifier maintenant**. Avec les mises à jour automatiques activées, le paquet vérifié s’applique après fermeture. La distribution Windows et les mises à jour macOS ne sont publiées qu’après réussite des vérifications GitHub.

Sous **Windows x64**, extrais tout le ZIP avant d’ouvrir `BandStudio.exe` ; WebView2 est requis. Sous **macOS Intel ou Apple Silicon**, les archives de mise à jour sont destinées aux installations déjà préparées ; pour un Mac neuf, suis le [guide d’installation](BANDSTUDIO.md#macos). Après la mise à jour, relance la recherche des accords des anciens projets si les sources étaient manquantes. Les corrections manuelles et le calage protégé sont conservés.

Un décalage persiste ? Dans **Aide & Discord**, décris le passage, le tempo et le comportement attendu ; relis le rapport avant de le publier dans le salon des bugs. [Rejoindre la communauté](https://discord.gg/5UnQPdMUpR).
