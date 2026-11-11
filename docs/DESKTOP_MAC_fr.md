# ReaCue Desktop — aperçu Mac

Cette branche ajoute une application Mac au ReaCue existant, avec la palette et la navigation de BandPilot. Elle part du `main` GitHub `de701dc13f8979379e17c184ef803339f05b29be` (7 novembre 2026). Les moteurs audio, les outils REAPER et les écrans Studio sont conservés.

## Lancer sur le Mac de développement

1. Ouvrir `desktop-build/ReaCue Desktop.app`.
2. Ouvrir REAPER. Dans **Actions → Show action list → New action → Load ReaScript**, charger le fichier indiqué dans la fenêtre Desktop : `ReaCue Desktop.runtime/engine/reaper/ReaCue_Desktop_Bridge.lua`, à côté de l’application. Le bouton **Afficher le fichier du pont** le révèle dans Finder.
3. Sélectionner l’action **ReaCue_Desktop_Bridge.lua**, puis **Run/close**. Le projet ouvert apparaît automatiquement.

Le pont Desktop doit tourner pendant l’utilisation. Après un redémarrage de REAPER, relancer cette action. Relancer une action Desktop déjà active la redémarre proprement. Le pont ReaCue original, installé au démarrage de REAPER, reste nécessaire aux analyses existantes.

Pour ouvrir les **Outils complets**, fermer auparavant une éventuelle ancienne fenêtre ReaCue. La version incluse dans Desktop dispose des nouvelles commandes d’import. Les projets restent ouverts.

Une boîte de dialogue REAPER (choix de fichier, confirmation…) suspend ses scripts : terminer ce choix dans REAPER pour retrouver la connexion.

## Ce qui fonctionne directement dans Desktop

- Lecture, pause, arrêt, positionnement précis et décompte avant le passage.
- Sections REAPER, sélection d’un passage, boucle de section ou plage de mesures ; grille de tempo réelle, y compris les changements de tempo.
- Modification du nom et des limites, découpe, fusion, suppression, annulation/rétablissement via REAPER. Les limites exactes sont conservées lors d’un simple renommage.
- Pistes réelles : volume, mute, solo, click, annonces, transposition, ralentissement avec préservation de la hauteur.
- Écoute batterie seule ou sans batterie, puis retour aux mutes/solos précédents avec **Original**. Ce bouton restaure le mix précédant l’isolement ; il ne recharge pas le fichier source.
- Forme d’onde issue du cache audio publié. Aucune forme d’onde fictive n’est affichée. Les données publiées d’un autre projet sont refusées.
- Bibliothèque de morceaux et ouverture dans un nouvel onglet REAPER.
- Création de pistes d’enregistrement sur une entrée mono, armement, lancement/arrêt de la prise et repérage des prises existantes. Les entrées proviennent du périphérique configuré dans REAPER ; pour le multicanal/stéréo et le routage avancé, utiliser REAPER/BandPilot.
- Lancement des traitements de préparation, publication, bibliothèque et timecode.

Les numéros des mesures de l’écran de travail suivent **la grille REAPER**. Le prompteur conserve la numérotation musicale publiée, qui peut exclure le décompte. Après une correction des sections, utiliser **Synchroniser click, annonces & prompteurs**.

## Fonctions existantes reprises

| Fonctions du ReaCue actuel | Accès dans Desktop |
| --- | --- |
| Import fichier, dossier de stems, lien, reprise des imports | Préparer / Nouveau morceau → outils REAPER inclus |
| Séparation des stems, modèles, caches, récupération | Préparer → Séparer / Tout préparer |
| Tempo, grille, structure, click et annonces | Préparer / Structure / Outils complets → Morceau |
| Paroles automatiques, mots, accords, batterie/MIDI, grille PDF | Préparer / Outils complets → Morceau et Réglages |
| Mixer Studio, formes d’onde, exports audio et téléchargements | Travailler → Console complète |
| Prompteurs musiciens, batterie, paroles, PIN, QR et téléphones | Batterie & prompteur / Groupe / Scène |
| Bibliothèque, notes, suivi de répétition, présence et état « prêt » | Morceaux → Bibliothèque complète / Groupe |
| Répétition progressive, profils d’instruments et exceptions | Outils complets → Scène |
| Setlists, construction en lot, concerts portables, sauvegarde/restauration | Concert → Setlists & préparation |
| Régie et verrouillage de scène | Concert → Régie |
| grandMA3, patch, séquences, exports lumière, LTC/MTC | Lumière / outils REAPER inclus |
| Historique, reprise et annulation des traitements | Préparer → Historique |
| Tous les réglages, diagnostic et informations de licences | Réglages → Tous les réglages ReaCue |

Les fonctions avancées conservent leur interface complète dans REAPER ou Studio ; elles ne sont pas toutes réécrites dans les nouveaux panneaux. Les écrans Studio intégrés adoptent la palette BandPilot. Les modèles optionnels disponibles sont ceux installés sur ce Mac.

## BandPilot et XR

L’écran BandPilot ouvre l’application installée et positionne REAPER sur le passage sélectionné. Les deux applications utilisent le projet REAPER ouvert. L’Atelier du son et les analyses/réglages XR restent dans BandPilot. Cette preview n’envoie aucun réglage à la console et n’ajoute pas encore de synchronisation automatique des résultats d’analyse entre les applications.

## Construction et isolation

```sh
python3 tools/build_desktop_mac.py --runtime "$HOME/Documents/ReaCue" \
  --output "desktop-build/ReaCue Desktop.app"
```

Nécessite macOS avec les outils de développement Apple (`swiftc`), une installation ReaCue fonctionnelle et Python déjà installé. `--update` reconstruit uniquement un bundle portant l’identifiant de cette preview ; fermer l’application avant cette opération.

Le lanceur Mac est signé localement. Le code et les ressources sont copiés dans le dossier compagnon `ReaCue Desktop.runtime`, qui réutilise, par liens locaux, les environnements Python/modèles de l’installation existante. Garder **l’application et son dossier `.runtime` ensemble**. **Ce build est destiné à ce Mac ; ce n’est pas encore un installateur autonome à distribuer.** Garder l’installation ReaCue actuelle en place.

Le service écoute uniquement `127.0.0.1` sur un port aléatoire, avec session locale authentifiée. Le pont Desktop possède une boîte de messages séparée (`ReaCueDesktop`). Les commandes de modification portent l’identité du projet et une expiration. Le simple démarrage n’enregistre, ne lit et ne modifie aucun projet.

Les actions demandées depuis Desktop modifient réellement le projet ouvert dans REAPER. L’enregistrement nécessite une piste armée. Une piste nouvellement créée possède son retour logiciel désactivé. Les moteurs existants continuent d’utiliser les réglages, caches, bibliothèques et publications ReaCue habituels.

Pour revenir à l’interface habituelle : quitter Desktop puis ouvrir ReaCue depuis REAPER. Aucun remplacement de l’installation principale n’est nécessaire.

## Vérifications du 8 novembre 2026

- Application native compilée pour ce Mac Intel ; signature locale vérifiée avec `codesign --verify --deep --strict`.
- Lancement réel et connexion au projet Dani California : 10 pistes, 13 régions et forme d’onde publiée affichées. Aucun enregistrement audio matériel n’a été lancé pour cette vérification.
- 83 tests ciblés réussis : API locale, authentification, commandes Lua, changements de projet, contrôles de l’interface et outils REAPER conservés.
- Suite générale : 913 réussis, 26 ignorés, un échec de synchronisation dans un test existant du prompteur anglais. Ce test lisait l’afficheur avant la première réponse du transport ; l’attente a été corrigée et les deux variantes français/anglais ont ensuite réussi.
- Les tests audio lourds dépendant de modèles absents restent ignorés selon les règles de la suite existante. Les essais d’enregistrement matériel et de console XR restent à réaliser avec le périphérique choisi.
