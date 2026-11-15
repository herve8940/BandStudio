# BandStudio · tutoriel de préparation et de correction

[English](BANDSTUDIO_TUTORIAL_en.md) · [Installation et guide](BANDSTUDIO.md) · [Site](https://herve8940.github.io/BandStudio/)

Mis à jour le 15 novembre 2026. Ce tutoriel concerne l’application autonome BandStudio sur macOS et Windows.

**Pour débuter : [ouvrir le tutoriel visuel en 8 étapes](https://herve8940.github.io/BandStudio/tutoriel.html)** — import, tempo, premier « 1 », régions, guides, validation et export REAPER. Utilise les boutons Précédent et Suivant pour avancer à ton rythme.

## 1. Importer et préparer

Ouvre un fichier audio de ton ordinateur. Pour plusieurs morceaux, utilise **File de préparation**, ajoute les fichiers puis clique sur **Démarrer la file**. La file ne démarre jamais seule après ouverture de l’application.

Dans **Séparer & analyser**, choisis les moteurs installés ou **Tout préparer**. Les résultats déjà présents sont réutilisés et les corrections protégées sont conservées. Les analyses locales disposent d’un cache pour éviter de refaire un calcul identique ; une modification de l’audio, du modèle ou des paramètres peut nécessiter un nouveau calcul.

À l’import, BandStudio tente de caler la grille avant de préparer les guides. Les paramètres de calage d’un autre morceau ne sont pas repris. Une indication « à vérifier » signifie que l’écoute reste nécessaire, particulièrement pour le premier « 1 ».

## 2. Vérifier le premier temps et le décompte

Ouvre **Click & cues** et écoute le début avec le métronome. Vérifie le premier temps, le nombre de temps par mesure et le mode de grille : détectée pour conserver les variations du morceau, fixe si tu imposes un tempo constant. Corrige les paramètres si le « 1 » ne tombe pas au bon endroit.

Le décompte suit la grille enregistrée, y compris ses variations. Il peut commencer pendant le silence initial et accompagner une levée ; l’audio du morceau reste entier. Écoute également une reprise au milieu du morceau. Si une intro automatique a été recalée, vérifie son départ ; les sections corrigées ou validées restent protégées.

## 3. Ajuster les sections et les cues

Dans **Pistes & structure** :

1. Utilise **＋**, **−** et **Tout** pour zoomer. Le curseur **Parcourir le morceau** déplace la fenêtre visible ; **Suivre la lecture** garde la lecture à l’écran.
2. Choisis le calage **Mesure** ou **Temps**, puis fais glisser une frontière de section ou un cue. Tu peux aussi utiliser **−1 mesure**, **+1 mesure**, **−1 temps** et **+1 temps** dans le panneau **Un repère à la fois**.
3. Clique sur **Écouter autour** pour vérifier l’annonce et l’entrée. Le nom du repère ouvre son édition.
4. Clique sur **Valider et suivant** pour passer au repère suivant. Le compteur indique ce qui reste à écouter. Déplacer un repère annule sa validation.

Une frontière commune conserve la continuité des deux sections. Les corrections sont enregistrées avec le morceau et peuvent être annulées/rétablies. Cette validation par repère ne remplace pas la validation finale avant l’export REAPER.

## 4. Doser les guides

Les quatre niveaux **Métronome**, **Appels**, **Cues** et **Décompte** se règlent séparément. **Muet** coupe ou rétablit le niveau de chaque guide. Modifier un volume ou cocher la validation d’un repère ne relance pas une analyse IA ni la fabrication des guides. Modifier le placement d’un repère peut demander leur régénération.

## 5. Corriger la fiche du morceau

**[Suivre le tuto visuel Fiche morceau → PDF](https://herve8940.github.io/BandStudio/fiche-morceau.html)** — 8 étapes pour corriger les accords, les paroles, leur placement et exporter la fiche.

Ouvre **Fiche morceau**. La fiche rassemble l’identité du morceau, la pochette disponible, le tempo, la tonalité, les sections, les accords et les paroles, mesure par mesure. Choisis un passage dans la liste ; clique sur une mesure ou un titre de section pour déplacer le curseur d’écoute.

- Clique sur un accord ou une ligne de paroles pour modifier le texte et sa position. **Détails** affiche les repères supplémentaires.
- Utilise les champs **Mesure de début**, **Temps**, **Mesure de fin**, **Temps**, les boutons de déplacement ou **Placer au curseur**. Déplacer une ligne conserve les décalages de ses mots synchronisés.
- **+ Accord** et **+ Paroles** ajoutent une annotation. Lorsqu’un accord en remplace d’autres sur une portion, les parties situées en dehors de cette portion restent conservées.
- **Importer des paroles** permet d’utiliser ton fichier. **Annuler** et **Rétablir** permettent de revenir sur les corrections.
- Les recherches d’accords/paroles ouvrent une recherche dans ton navigateur à partir du titre et de l’artiste. Compare la version et la tonalité, puis corrige toi-même : aucun contenu de ces sites n’est importé automatiquement.

La fiche modifie les annotations du morceau ouvert. Les accords estimés et la transcription demandent une vérification à l’écoute ; une ligne sans synchronisation mot par mot reste entière à sa position de départ.

## 6. Exporter une fiche PDF et le projet

Clique sur **Exporter la fiche PDF**. La grille imprimable reprend les sections, les mesures, les accords, les paroles, les cues et les notes. Elle respecte le calage, la transposition et le capo pour les accords affichés. Choisis le nom et l’emplacement de la copie ; le PDF s’ouvre ensuite dans le lecteur de ton système. Si tu annules cette copie, le PDF généré reste dans le dossier **Exports** du morceau. **Afficher l’export** permet de le retrouver si l’ouverture automatique échoue.

Enfin, dans **Valider & envoyer**, écoute et confirme le mix, la grille et les guides, puis exporte vers REAPER. Pour bénéficier des corrections du décompte dans un projet REAPER déjà exporté, refais l’export.

## Mettre à jour ou demander de l’aide

Dans **Réglages**, utilise **Vérifier maintenant**. Avec les mises à jour automatiques activées, le paquet vérifié s’applique après fermeture. La distribution Windows et les mises à jour macOS ne sont publiées qu’après réussite des vérifications GitHub.

Un décalage persiste ? Dans **Aide & Discord**, décris le passage, le tempo et le comportement attendu ; relis le rapport avant de le publier dans le salon des bugs. [Rejoindre la communauté](https://discord.gg/5UnQPdMUpR).
