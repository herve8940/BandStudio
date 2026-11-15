# Tutoriel ReaCue — pas à pas

> **Application autonome BandStudio :** les nouvelles fonctions de correction, de fiche morceau et de PDF sont expliquées dans le [tutoriel BandStudio](BANDSTUDIO_TUTORIEL_fr.md). Le tutoriel ci-dessous concerne les scripts ReaCue dans REAPER.

*[English version: TUTORIAL_en.md](TUTORIAL_en.md)*

Ce tutoriel t'emmène de l'installation jusqu'à la répétition avec le groupe. Il suppose que tu sais lancer
REAPER et lire un morceau, rien de plus. Chaque étape dit **où cliquer**, **ce que tu dois voir** et **quoi
faire si ça ne marche pas**.

À la fin, pour chaque morceau, tu auras dans REAPER :

- une carte de tempo calée sur le morceau, des régions nommées et colorées (Intro, Couplet 1, Refrain…) ;
- une piste **CLICK** avec 2 mesures de décompte, une piste **VOIX** qui annonce « Refrain » avant chaque
  section et compte « one two three four » ;
- un **prompteur** sur le téléphone de chaque musicien : structure, accords, paroles (mot par mot si le
  composant est installé), batterie, plus une **Régie** (télécommande) et un rôle **Lumière** ;
- une **grille PDF** à imprimer (accords et paroles, mesure par mesure) dans le dossier du morceau ;
- les fichiers d'un show pour console **grandMA3** (un cue par section) et, si tu le veux, des pistes qui
  envoient le **timecode** à la console.

Tout se fait depuis **une seule fenêtre, « ReaCue »**, en cinq onglets : **Morceau** (préparer un
morceau), **Concert** (composer et construire un concert, préparer plusieurs morceaux d'un coup), **Scène**
(jouer : transport, instruments, répétition, Régie), **Lumière** (console grandMA3 : cues, timecode, test) et
**Réglages**.

Des **composants facultatifs**, qui tournent eux aussi sur ton ordinateur, améliorent l'analyse : séparation
de stems (Demucs), analyse de structure (SongFormer), accords et batterie par modèle entraîné, paroles mot par
mot et paroles automatiques (Whisper). Sans eux, tout marche avec la détection de ReaCue
([chapitre 20](#20-composants-facultatifs)).

**Le principe pour chaque morceau tient en deux clics** : **+ Nouveau morceau**, puis **Tout faire**. Un grand
bouton te donne toujours l'étape suivante, une ligne en bas de la fenêtre explique le bouton survolé, et une
erreur te dit quoi faire avec un bouton qui le fait.

La durée dépend de la machine et des composants : les téléchargements initiaux et les modèles IA
peuvent prendre plusieurs minutes ou davantage par morceau, notamment sur un Mac Intel.

> **Interfaces web Studio Pro :** console [17.3](#173-reacue-studio--lécran-travail),
> régie concert/lumière [17.5](#175-reacue-studio--écrans-concert-et-lumière), prompteur [13.1](#131-prompteur--mode-scène-et-détails).
> Après mise à jour du dépôt, relance l'installateur pour recopier les ressources web, puis recharge les pages.
> Les fenêtres natives ReaCue dans REAPER et les pages web Studio/Prompteur sont deux interfaces distinctes.

---

## Sommaire

1. [Ce qu'il te faut](#1-ce-quil-te-faut)
2. [Télécharger ReaCue](#2-télécharger-reacue)
3. [Préparer REAPER pour l'installation](#3-préparer-reaper-pour-linstallation)
4. [Lancer l'installateur](#4-lancer-linstallateur)
5. [Vérifier dans REAPER](#5-vérifier-dans-reaper)
6. [Activer l'interface web de REAPER (une seule fois)](#6-activer-linterface-web-de-reaper-une-seule-fois)
7. [Créer le projet d'un morceau](#7-créer-le-projet-dun-morceau)
8. [Importer l'audio : des stems ou un seul MP3](#8-importer-laudio--des-stems-ou-un-seul-mp3)
9. [Séparer un MP3 en stems](#9-séparer-un-mp3-en-stems)
10. [Préparer le morceau](#10-préparer-le-morceau-avec-tout-faire)
11. [Vérifier la structure](#11-vérifier-la-structure)
12. [Ajouter les paroles](#12-ajouter-les-paroles)
13. [Ouvrir le prompteur sur les téléphones](#13-ouvrir-le-prompteur-sur-les-téléphones)
14. [Régler le click, les annonces et les in-ears](#14-régler-le-click-les-annonces-et-les-in-ears)
15. [Relier Claude Desktop (facultatif)](#15-relier-claude-desktop-facultatif)
16. [Mode concert : plusieurs morceaux dans un projet](#16-mode-concert--plusieurs-morceaux-dans-un-projet)
17. [En répétition](#17-en-répétition)
18. [Dépannage](#18-dépannage)
19. [Pense-bête : un nouveau morceau, un concert](#19-pense-bête--un-nouveau-morceau-un-concert)
20. [Composants facultatifs](#20-composants-facultatifs)
21. [Annexe : tous les réglages](#21-annexe--tous-les-réglages)

---

## 1. Ce qu'il te faut

| Élément | Détail |
|---|---|
| Ordinateur | Mac (macOS 12 ou plus, Intel ou Apple Silicon) ou PC Windows 10/11 (Windows : version bêta) |
| REAPER | Version 7 ou plus récente, déjà installé ([reaper.fm](https://www.reaper.fm/)) |
| Espace disque | 1,5 Go pour ReaCue ; en plus pour chaque composant facultatif installé (de quelques centaines de Mo à environ 5 Go, voir le [chapitre 20](#20-composants-facultatifs)) |
| Internet | Seulement pendant l'installation |
| Audio | Les stems d'un morceau (un fichier par instrument), **ou** un seul MP3/WAV |
| Téléphones | Sur le **même Wi-Fi** que l'ordinateur, avec un navigateur (Safari, Chrome…) |

> Les stems donnent les meilleurs résultats. Si tu n'as que le MP3, ReaCue peut le séparer en stems sur
> ton ordinateur (étape 9).

---

## 2. Télécharger ReaCue

1. Sur la page GitHub du projet, clique sur le bouton vert **Code**, puis **Download ZIP**.
2. Ouvre le fichier ZIP téléchargé : un dossier `reacue-main` apparaît.
3. **Déplace ce dossier à son emplacement définitif**, par exemple dans *Documents*, et renomme-le `ReaCue`.

**Tu dois voir** dans le dossier `ReaCue` : `README.md`, `LISEZMOI.md`, les dossiers `reacue_mcp`, `reaper`,
`install`, `docs`, et les installateurs (`.command` pour Mac, `.bat` pour Windows) :

| Fichier | Rôle |
|---|---|
| `Install ReaCue` | ReaCue lui-même ; propose aussi la séparation de stems et l'analyse de structure (étape 4) |
| `Install ReaCue Stems` | séparation d'un MP3 en stems (Demucs) |
| `Install ReaCue Structure` | analyse de structure (SongFormer) |
| `Install ReaCue Chords` | accords par modèle entraîné |
| `Install ReaCue Drums` | batterie par modèle entraîné (ADTOF) |
| `Install ReaCue Words` | paroles mot par mot et paroles automatiques (Whisper) |
| `Uninstall ReaCue` | désinstallation |

Les cinq composants facultatifs sont décrits au [chapitre 20](#20-composants-facultatifs).

> ⚠️ Ne déplace plus ce dossier après l'installation. Si tu dois le déplacer, relance l'installateur depuis
> le nouvel emplacement.

---

## 3. Préparer REAPER pour l'installation

1. **Lance REAPER une fois**, puis **quitte-le** (macOS : *REAPER → Quit REAPER* ; Windows : *File → Quit*).

Pourquoi : au premier lancement, REAPER crée son dossier de réglages ; et l'installateur ne peut enregistrer
les actions ReaCue que si REAPER est **fermé**.

---

## 4. Lancer l'installateur

### Sur Mac

1. Dans le dossier `ReaCue`, **double-clique sur `Install ReaCue.command`**.
2. Si macOS affiche « impossible d'ouvrir … développeur non identifié » : clique sur **OK**, puis
   **clic droit** (ou Ctrl + clic) sur `Install ReaCue.command` → **Ouvrir** → **Ouvrir**.
   Sur les versions récentes de macOS, il peut falloir aller dans *Réglages Système → Confidentialité et
   sécurité*, tout en bas, et cliquer sur **Ouvrir quand même**.
3. Une fenêtre Terminal s'ouvre.

### Sur Windows

1. Dans le dossier `ReaCue`, **double-clique sur `Install ReaCue.bat`**.
2. Si Windows affiche « Windows a protégé votre ordinateur » (SmartScreen) : clique sur **Informations
   complémentaires**, puis **Exécuter quand même**.
3. Une fenêtre noire (console) s'ouvre.

### Les questions (Mac et Windows)

| Question | Quoi répondre |
|---|---|
| `Langue / Language [fr/en]` | `fr` puis Entrée |
| `Déclarer ReaCue dans Claude Desktop … ? [o/N]` | `n` si tu n'utilises pas Claude Desktop (tu pourras le faire plus tard) |
| `Installer la séparation de stems … ? [o/N]` | `o` si tu as des morceaux en MP3 seulement (environ 1 Go à télécharger, 5 à 15 minutes) ; sinon `n` |
| `Installer l'analyse de structure … ? [O/n]` | **Entrée** (= oui, proposé par défaut) : de meilleures sections avec SongFormer (IA, environ 3 Go à télécharger, 10 à 40 minutes, 8 Go de RAM conseillés, **usage non commercial**) ; `n` pour s'en passer |
| `Pour installer, tape exactement « J'accepte »` (après le résumé des licences) | Lis le résumé : les poids du modèle MuQ sont réservés à un **usage non commercial** (CC BY-NC 4.0). Si ça te convient, tape `J'accepte` puis Entrée ; sinon Entrée seule (rien n'est installé). Détails : [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) |

**Tu dois voir** défiler 6 étapes (`== 1/6 Vérifications` … `== 6/6 Analyse de structure`) :

- à la fin de l'étape 4 : une ligne `Adresse(s) IP probable(s) de cet ordinateur : …` → **note cette
  adresse** (ex. `192.168.1.20`), elle servira pour les téléphones ; puis `Installation terminée. Redémarre
  REAPER…` (ReaCue est installé) ;
- à l'étape 5, si tu as répondu `o` : le téléchargement de PyTorch et Demucs, deux lignes `modèle … prêt`,
  deux lignes `vitesse … environ N min pour un morceau de 4 min`, puis `Séparation de stems installée` ;
- à l'étape 6 (sauf si tu as répondu `n`) : le résumé des licences et la demande « J'accepte », puis le
  téléchargement de SongFormer, MuQ et MusicFM, puis de PyTorch ; `modèle réutilisé : …` pour chaque modèle
  déjà présent sur l'ordinateur (par exemple dans `Documents/ReaCue-labo` ou le cache Hugging Face : il n'est
  pas retéléchargé), puis les modèles manquants (jusqu'à 2 Go), une ligne `vitesse : environ N min pour un morceau de 4 min`, `STRUCTURE_OK` et
  `Analyse de structure installée`.

Appuie sur Entrée pour fermer la fenêtre.

**Si ça ne marche pas :**

| Message | Solution |
|---|---|
| `dossier REAPER introuvable` | Lance REAPER une fois, quitte-le, relance l'installateur |
| `installation de uv impossible (internet ?)` | Vérifie la connexion internet, relance l'installateur |
| `REAPER est ouvert : les actions ne peuvent pas être enregistrées` | Pas grave : quitte REAPER et relance l'installateur, ou charge les actions à la main (étape 5) |
| `séparation de stems non installée` | Le reste de ReaCue marche. Réessaie plus tard avec `Install ReaCue Stems.command` / `.bat` |
| `analyse de structure non installée` | ReaCue garde sa propre détection. Réessaie plus tard avec `Install ReaCue Structure.command` / `.bat` (il reprend là où il s'est arrêté) |

> L'installateur peut être relancé autant de fois que tu veux : il répare l'installation et garde tes réglages.

**Suite complète de modèles d'IA :** En **Mode Automatique** (choix 1 ou *Entrée*), l'installateur configure automatiquement tous les modèles adaptés à votre machine (Stems Demucs, Structure SongFormer, Accords ISMIR, Batterie ADTOF, et Paroles Whisper). En **Mode Personnalisé**, chaque modèle vous est proposé avec son descriptif détaillé. Chaque composant dispose également de son propre installateur autonome (`Install ReaCue Chords`, `Install ReaCue Drums`, `Install ReaCue Words`), relançable à tout moment.

---

## 5. Vérifier dans REAPER

1. Lance REAPER.
2. Menu **Actions → Show action list…**
3. Dans le champ **Filter** en haut, tape `ReaCue`.

**Tu dois voir** sept actions :

- `Custom: ReaCue` — **la fenêtre principale**, c'est celle dont tu te serviras tout le temps
- `Custom: ReaCue - Préparer le morceau`
- `Custom: ReaCue - Republier le prompteur`
- `Custom: ReaCue - Séparer les stems`
- `Custom: ReaCue - Concert` (la même fenêtre, ouverte sur l'onglet Scène)
- `Custom: ReaCue - Morceau suivant` et `Custom: ReaCue - Morceau précédent`

**Mets l'action « ReaCue » dans la barre d'outils.** Clic droit sur la barre d'outils principale (en haut à
gauche) → **Customize toolbar…** → **Add…** → filtre `ReaCue` → choisis **`ReaCue`** → **Select/close** →
**Save**. Un clic sur ce bouton ouvre la fenêtre ReaCue (un 2e clic la ferme).

**Au premier lancement**, la fenêtre ReaCue ouvre un **assistant** qui vérifie tout : pont, interface web
(port), adresse IP, programme ReaCue, séparation de stems, analyse de structure, dossier des projets. Chaque
point vert est prêt ; pour un point orange ou rouge, le bouton à droite le règle (*Démarrer*, *Préférences*,
*Installer*, *Créer*…). **Terminer** ferme l'assistant ; tu le retrouves dans *Réglages → Vérifier
l'installation*.

<img src="images/window_assistant_fr.png" width="420">

**La fenêtre ReaCue** s'ouvre toute seule sur le bon onglet : **Scène** si le projet est un concert,
**Morceau** si c'est un morceau, sinon le dernier utilisé. Clic droit dans la fenêtre : l'ancrer dans
REAPER ou la détacher (ancrée en bas, elle devient une barre de transport compacte). En haut à droite, deux
pastilles : **pont** (ReaCue répond dans REAPER) et **web** (prompteur disponible) — vertes quand tout va bien.
En bas, la **ligne d'aide** explique ce que fait l'élément sous la souris.

<img src="images/window_song_fr.png" width="420">

**Si les actions n'apparaissent pas** (REAPER était ouvert pendant l'installation) :

1. Dans la liste des actions, clique sur **New action… → Load ReaScript…**
2. Va dans le dossier des scripts : menu *Options → Show REAPER resource path in explorer/finder*, puis
   `Scripts` → `ReaCue`.
3. Choisis `ReaCue.lua` → **Ouvrir**. Recommence avec `ReaCue_Preparer.lua`, `ReaCue_Republier_prompteur.lua`,
   `ReaCue_Separer_stems.lua`, `ReaCue_Concert.lua`, `ReaCue_Morceau_suivant.lua` et `ReaCue_Morceau_precedent.lua`.

---

## 6. Activer l'interface web de REAPER (une seule fois)

Le prompteur des téléphones passe par le petit serveur web intégré à REAPER.

1. Mac : menu **REAPER → Settings…** ; Windows : menu **Options → Preferences…**
2. Dans la liste de gauche, tout en bas : **Control/OSC/web**.
3. Clique sur **Add**.
4. **Control surface mode** : choisis **Web browser interface**.
5. **Port** : `8080` (garde cette valeur si possible).
6. Laisse le reste tel quel, clique **OK**, puis **OK** pour fermer les préférences.

**Pour vérifier :** sur l'ordinateur, ouvre un navigateur à l'adresse `http://localhost:8080/` : une page
de REAPER doit s'afficher.

**Si ça ne marche pas :** un autre programme utilise peut-être le port 8080 → recommence avec `8081` (et
utilise ce port partout dans la suite). Sous Windows, si le pare-feu demande l'autorisation pour REAPER,
coche **Réseaux privés** et clique **Autoriser**.

---

## 7. Créer le projet d'un morceau

**Un projet REAPER par morceau.** ReaCue remplace les régions, le tempo et les pistes CLICK / CUES / VOIX à
chaque préparation : ne mets pas plusieurs morceaux dans le même projet.

### Le plus simple : « + Nouveau morceau »

1. Ouvre la fenêtre **ReaCue** (action **ReaCue**). Le bouton **+ Nouveau morceau** est en haut de l'onglet
   **Morceau** (et sous la liste des morceaux de l'onglet **Concert**).
2. Clique dessus et choisis :
   - **Un fichier (MP3, WAV…)** : choisis le fichier du morceau ;
   - **Des stems (un dossier)** : choisis **un des fichiers de stems** — tous les fichiers audio du même
     dossier sont pris (si l'extension *js_ReaScriptAPI* est installée, tu choisis directement le dossier).
3. ReaCue propose un **titre** déduit du nom (sans « -Bass- », la tonalité, le BPM, « Official Video »…) :
   corrige-le si besoin, **OK**. Si un morceau de ce titre existe déjà, ReaCue te demande un autre titre :
   rien n'est jamais écrasé.
4. ReaCue **copie** les fichiers dans `Documents/REAPER Media/<Titre>/` (la progression s'affiche dans
   l'onglet ; les noms des fichiers sont gardés), ouvre un **nouvel onglet de projet** (ton projet ouvert
   n'est pas touché), place **un fichier par piste** au début, et **enregistre** le projet
   `<Titre>/<Titre>.RPP`.

**Tu dois voir** l'onglet **Morceau** du nouveau projet avec le bandeau **« Morceau créé. Tout préparer
maintenant ? »** : clique **Tout faire** (étape 10) — ou **Plus tard**. Le grand bouton indique l'étape
suivante : **Séparer les stems** (un seul fichier, étape 9) ou **Analyser et préparer** (stems). Le morceau apparaît aussi
dans la liste de l'onglet **Concert** (en orange tant qu'il n'est pas préparé ; un clic sur son nom l'ouvre).

<img src="images/window_newsong_fr.png" width="420">

> Copier les fichiers évite le problème des fichiers « OFFLINE » laissés dans *Téléchargements* sur Mac.
> Après **Tout faire**, **Séparer les stems**, **Analyser et préparer** ou **Appliquer** réussis depuis la
> fenêtre, le projet du morceau est **enregistré automatiquement** (pastille « Enregistré ✓ ») : le concert retrouvera toujours ses
> sections et son tempo.

### Autre méthode (à la main)

1. Crée un dossier pour le morceau, par exemple `Documents/REAPER Media/Demo Song/`.
2. **Copie dedans les fichiers audio du morceau** (stems ou MP3).
   > ⚠️ Sur Mac, évite de laisser les fichiers dans *Téléchargements* : macOS peut empêcher REAPER de les
   > lire (l'item affiche alors « OFFLINE »).
3. Dans REAPER : **File → New project**.
4. **File → Save project as…**, choisis le dossier du morceau, nomme le projet (`Demo Song`), et coche
   **Copy all media into project directory** si l'option est proposée. **Save**.
5. Importe l'audio (étape 8).

---

## 8. Importer l'audio : des stems ou un seul MP3

*Inutile si tu as utilisé **+ Nouveau morceau** (étape 7) : lis seulement le tableau des noms de fichiers.*

### Cas A : tu as les stems

1. Sélectionne tous les fichiers de stems dans le Finder / l'Explorateur.
2. **Glisse-les ensemble** dans la zone des pistes de REAPER, tout au début (à gauche).
3. Si REAPER demande comment placer plusieurs fichiers, choisis **« One per track »** (un par piste).

**Tu dois voir** une piste par stem, tous les items commençant au même endroit.

Les noms de fichiers comptent : ReaCue reconnaît le rôle de chaque stem grâce à des mots dans le nom :

| Rôle | Mots reconnus dans le nom du fichier |
|---|---|
| Batterie | `drum`, `batterie`, `kick`, `perc` |
| Basse | `bass`, `basse` |
| Guitare | `guitar`, `guitare`, `gtr` (`lead` ou `solo` = guitare solo) |
| Chant | `vocal`, `voice`, `vox`, `chant`, `voix` |
| Autre | tout le reste (claviers…) |

> Bonus : la tonalité et le tempo dans le nom (ex. `Demo Song-A minor-112bpm-drums.wav`) améliorent les
> accords et évitent les erreurs de tempo double/moitié.

Passe directement à l'**étape 10**.

### Cas B : tu n'as qu'un MP3 (ou un WAV)

1. Glisse le fichier dans la zone des pistes de REAPER, tout au début.

Tu peux préparer directement le morceau (étape 10), mais avec moins de détails (pas de vue batterie, pas
d'entrées/sorties par instrument, accords et sections moins sûrs). **Mieux : sépare-le d'abord en stems
(étape 9).**

---

## 9. Séparer un MP3 en stems

*Nécessite la séparation de stems installée (réponse `o` à l'étape 4, ou `Install ReaCue Stems`).*

1. **Clique sur l'item du MP3** dans REAPER pour le sélectionner (il devient plus clair).
2. Dans la fenêtre **ReaCue**, onglet **Morceau**, clique le grand bouton **Séparer les stems** (ou lance
   l'action **ReaCue - Séparer les stems**). *Tout faire* (étape 10) le fait aussi, puis enchaîne la suite.
3. L'onglet affiche **« Séparation des stems : N % »** avec une barre de progression.
   - Compte **5 à 8 minutes pour un morceau de 4 minutes** sur un Mac Intel, moins sur un Mac récent.
   - Tu peux changer d'onglet et continuer à travailler : l'import se fera tout seul à la fin.
   - Ne ferme pas REAPER pendant la séparation.
4. À la fin, un message **« Stems importés »** s'affiche.

**Tu dois voir** six nouvelles pistes sous la piste d'origine : **Chant, Batterie, Basse, Guitare, Piano,
Autres**, calées exactement comme le MP3. L'item du MP3 a été retiré du projet (le fichier, lui, est toujours
sur le disque ; *Edit → Undo* le remet).

Les fichiers des stems sont rangés à côté du MP3, dans `<nom du morceau>-stems/htdemucs_6s/`.
> 💡 **Guide complet Stems & Matériel :** Pour comprendre en détail les différences entre les modèles Demucs (`htdemucs_6s`, `htdemucs_ft`, `htdemucs`), les exigences matérielles (GPU NVIDIA RTX 50 Blackwell, Apple Silicon, CPU) et les bonnes pratiques de découpe, consultez le **[Guide Bonnes Pratiques & Matériel](BONNES_PRATIQUES_ET_MATERIEL.md)**.
 Si tu relances
l'action sur le même MP3, l'import est immédiat (pas de nouvelle séparation).

> Écoute les pistes en solo (bouton **S**) : voix, batterie et basse sont en général très propres ; guitare
> et piano peuvent garder un peu des autres instruments. C'est normal et suffisant pour ReaCue. Une piste
> presque vide (par exemple Piano dans un morceau sans clavier) n'est pas un problème.

**Si ça ne marche pas :**

| Message | Solution |
|---|---|
| « Sélectionne l'item audio du morceau » | Clique sur l'item du MP3, puis relance l'action |
| « Fichier audio introuvable… OFFLINE » | Le fichier n'est pas lisible : voir [Dépannage](#18-dépannage) |
| « La séparation de stems n'est pas installée » | Double-clic sur `Install ReaCue Stems.command` / `.bat` dans le dossier ReaCue |
| « La séparation a échoué » | Lis la fin du journal affichée ; le journal complet est `…-stems/demucs.log` |
| La progression reste longtemps à 0 % | Normal pendant la première minute (chargement du modèle) |

---

## 10. Préparer le morceau avec Tout faire

1. Fenêtre **ReaCue**, onglet **Morceau** : clique **Tout faire** (à droite du grand bouton). Pas besoin de
   sélectionner quoi que ce soit.
2. Une liste montre les étapes et leur durée :

   | Étape | Ce qu'elle fait |
   |---|---|
   | Séparer les stems | seulement pour un MP3/WAV seul (« déjà fait » sinon) |
   | Analyser et préparer | tempo, mesures, **structure** (SongFormer s'il est installé), régions, click, annonces, prompteur |
   | Mettre à jour les téléphones | paroles, accords, batterie et structure pour le prompteur |
   | Enregistrer le projet | pour que le concert retrouve sections et tempo |

   **Arrêter** s'arrête après l'étape en cours. En cas d'échec, la cause et **que faire** s'affichent avec un
   bouton (par ex. *Démarrer le pont*) ; **Reprendre** repart de l'étape en échec.
3. À la fin : **« Morceau prêt ✓ »** (*Résumé* : tempo, mesures, structure, ce qui a été publié). **Fermer**.
   Le grand bouton indique maintenant **Prêt ✓** et les **pastilles** sont vertes : Stems ✓ · Structure :
   SongFormer ✓ · 120 BPM · Accords ✓ · Batterie ✓ · Paroles · Grille PDF ✓ · Prompteur publié ✓ · Enregistré ✓.

<img src="images/window_doall_fr.png" width="420">

Étape par étape, c'est pareil avec le grand bouton (**Séparer les stems** → **Analyser et préparer** → **Prêt
✓**) ; dessous : *Re-préparer* (refait tout en gardant ta structure), *Réanalyser depuis zéro* (tempo et
structure recalculés, tes corrections sont remplacées), *Mettre à jour les téléphones*. L'action **ReaCue -
Préparer le morceau** fait *Analyser et préparer*.

**Tu dois voir** dans le projet :

- des **régions** colorées en haut (Intro, Couplet 1, Refrain 1…) ;
- des marqueurs **« → Refrain »** avant chaque section ;
- trois nouvelles pistes : **CUES**, **VOIX**, **CLICK** ;
- l'audio décalé de 2 mesures pour laisser la place au décompte.

> **Avec SongFormer** (analyse de structure, installée par défaut) : la première préparation d'un morceau
> prend quelques minutes de plus ; la liste affiche **« Analyse de structure (SongFormer)… N s »**. Les
> préparations suivantes du même morceau sont immédiates (résultat mémorisé). Si SongFormer échoue, le
> message dit « Analyse SongFormer impossible : … → structure ReaCue utilisée » et la pastille indique
> **Structure : ReaCue**. Pour comparer : *Réglages* → *Détection de structure* → **ReaCue seul**, puis
> *Réanalyser depuis zéro*.

> **Accords, batterie, paroles** : pendant la préparation ou *Mettre à jour les téléphones*, la liste peut afficher **« Accords
> (modèle)… N s »**, **« Paroles mot par mot… N s »** ou **« Paroles automatiques (Whisper)… N s »** : ce sont
> les composants facultatifs du [chapitre 20](#20-composants-facultatifs), utilisés tout seuls quand ils sont
> installés (la batterie par ADTOF n'affiche pas de ligne à part). Chacun ne coûte ce temps qu'une fois par
> morceau (résultat mémorisé). S'il échoue, le *Résumé* le dit (par ex. « Modèle d'accords indisponible : … →
> détection d'accords de ReaCue utilisée ») et le morceau est prêt quand même.

Appuie sur **Espace** : tu entends 2 mesures de click avec « one two three four », puis le morceau, le click
et les annonces.

**Si ça ne marche pas :** la fenêtre affiche la cause, que faire et un bouton. En résumé :

| Message | Solution |
|---|---|
| « Le pont ReaCue ne tourne pas dans REAPER » | Bouton **Démarrer le pont** ; sinon redémarre REAPER, ou relance l'installateur (REAPER fermé) |
| « Programme ReaCue introuvable » | Le dossier ReaCue a été déplacé : relance l'installateur depuis son nouvel emplacement |
| « Une préparation est déjà en cours » | Attends la fin de la précédente (1 minute max) |
| Le tempo est le double ou la moitié du vrai | Ajoute le tempo dans le nom des fichiers (ex. `-94bpm`) et *Réanalyser depuis zéro* |

### La grille PDF du morceau

À chaque publication du prompteur (*Analyser et préparer*, *Re-préparer*, *Tout faire*, *Mettre à jour les
téléphones*, *Appliquer*), ReaCue écrit aussi une **grille à imprimer** (A4) dans le **dossier du morceau** :
celui des fichiers audio, ou le dossier du MP3 d'origine quand les stems sont dans `…-stems/`. Elle s'appelle
**`Grille - <Titre>.pdf`** (`Chart - <Titre>.pdf` quand la langue est l'anglais) et est remplacée à chaque
publication.

| On y trouve | Détail |
|---|---|
| En-tête | titre, tempo, mesure (4/4…), décompte, tonalité (« estimée » quand elle est déduite des accords) |
| Une ligne par groupe de 4 mesures | chaque section avec son nom, sa couleur et son nombre de mesures |
| Accords | l'accord de chaque mesure ; une case coupée en deux s'il y en a deux |
| Paroles | le bout de texte chanté dans chaque mesure (case colorée) ; avec les paroles mot par mot, chaque mot est dans la mesure où il est vraiment chanté ; sans paroles, les cases colorées montrent les mesures où la voix chante |
| Bas de page | « accords et paroles détectés automatiquement, à vérifier » (ou « paroles transcrites automatiquement (brouillon) » avec des paroles automatiques), numéro de page |

Dans l'onglet **Morceau**, la pastille **Grille PDF ✓** l'ouvre (**Grille PDF —** : clic = la créer en mettant à
jour les téléphones). La grille ne bloque jamais la préparation : en cas de problème, un avertissement
« Grille PDF non créée : … » s'affiche et tout le reste est prêt. Un concert n'a pas de grille à lui :
imprime celles de ses morceaux.

---

## 11. Vérifier la structure

Lis la structure dans l'onglet **Morceau** : la **bande colorée** (une case par section, largeur
proportionnelle au nombre de mesures) et la liste dessous (première mesure, longueur). Les cases **orange**
sont **à vérifier** — survole-les, la ligne d'aide dit pourquoi :

- **longueur inhabituelle** : une section qui ne fait pas 4, 8 ou 16 mesures est souvent une erreur (deux
  sections collées, ou une section coupée en deux) ;
- **frontière déplacée par le calage** ou **entre deux mesures** : SongFormer hésitait sur le début.

Regarde aussi **les noms** (couplet et refrain inversés, pré-refrain collé au refrain) et la fin (une longue
« Outro » peut contenir un dernier refrain ou un solo).

Écoute : **clique sur une case** de la bande (ou sur un nom de la liste) — la section est choisie et la
lecture part de son début.

**Pour corriger, trois méthodes (tu peux les mélanger) :**

**Méthode 1 — dans l'onglet Morceau** (le plus simple)

<img src="images/window_structure_fr.png" width="420">

Choisis une section (clic sur sa case) ; ses outils s'affichent sous la bande :

| Bouton | Effet |
|---|---|
| **Renommer** (ou **Nom** dans la liste) | renommer (« Pré-refrain », « Solo »…) |
| **◀** / **▶** | avancer / reculer le début d'**une mesure** (la fin de la section précédente suit) |
| **Fusionner →** | réunir la section avec la suivante |
| **Couper en deux** | couper la section au milieu (sur une mesure) ; tu nommes la 2e partie |
| **Supprimer** (ou **✕**) | supprimer (la section précédente s'allonge jusqu'à la suivante) |
| **+ Section au curseur** | ajouter une section qui commence à la mesure du curseur d'édition |
| **Annuler** / **Rétablir** | revenir en arrière / refaire, autant de fois que tu veux |

Le grand bouton devient **Appliquer les modifications** (et un bandeau « Structure modifiée » propose
**Appliquer**) : clique-le. Click, annonces, couleurs et prompteur suivent ; la pastille indique **Structure :
manuelle**.

**Méthode 2 — à la main dans REAPER, puis « Appliquer »**

1. Corrige les régions dans la barre des régions (en haut de la fenêtre) :
   - **renommer** ou **changer le début** : double-clique sur la région → change *Name* ou *Start* → **OK** ;
   - **déplacer le début** : tu peux aussi faire glisser le bord gauche de la région ;
   - **ajouter** : fais une sélection de temps (glisser dans la règle) qui commence au début de la nouvelle
     section, puis menu *Markers → Insert region from time selection* (raccourci par défaut Maj+R), et
     nomme-la ;
   - **supprimer** : clic droit sur la région → *Remove region*.
2. Clique **Appliquer les modifications** / **Re-préparer** dans l'onglet Morceau (ou lance **ReaCue - Préparer
   le morceau**).
3. La fenêtre de fin commence par **« Structure reprise de tes régions REAPER »**, avec le nouveau tableau.
   Les régions sont recolorées, et les marqueurs « → », les annonces, le click et le prompteur suivent.

Bon à savoir :

- seul le **début** de chaque région compte : une section dure jusqu'au début de la région suivante (pas
  besoin d'ajuster les fins) ;
- un début placé entre deux mesures est recalé sur la barre de mesure la plus proche (un avertissement le
  signale s'il était à plus d'un quart de mesure) ;
- le nom choisit la couleur et l'annonce : « Refrain 2 » ou « Chorus 2 » donne un refrain, « Solo » un solo… ;
- une région avant la mesure 1, après la fin du morceau ou sur la même mesure qu'une autre est ignorée
  (avertissement) ;
- si tu n'as rien changé, *Re-préparer* garde la structure enregistrée, comme avant ;
- *Mettre à jour les téléphones* ne reprend pas les régions modifiées : un avertissement te demande de
  cliquer *Appliquer*.

**Méthode 3 — avec Claude Desktop** (facultatif, voir [l'étape 15](#15-relier-claude-desktop-facultatif))

Dis simplement « le refrain 1 commence mesure 37 » ou « renomme la section 6 en Solo » : tout est
reconstruit (régions, click, annonces, prompteur). Ce que tu dis à Claude remplace les régions modifiées à
la main.

---

## 12. Ajouter les paroles

ReaCue ne télécharge jamais de paroles : **c'est toi qui fournis le texte**.

1. Ouvre un éditeur de texte :
   - Mac : **TextEdit**, puis menu **Format → Convertir au format texte** (important : texte brut) ;
   - Windows : **Bloc-notes**.
2. Écris (ou colle) les paroles : **une ligne = une phrase chantée**, une ligne vide entre les blocs
   (couplet, refrain…). Les lignes comme `[Refrain]` ou `Couplet 2 :` sont ignorées, ainsi que les lignes qui
   commencent par `#` (commentaires). `(x2)` ou `bis` en fin de ligne la répète. Un refrain écrit une seule
   fois est retrouvé tout seul quand il est rechanté (stem voix nécessaire).
3. Enregistre le fichier sous le nom **`paroles.txt`** (encodage **UTF-8**), **dans le dossier des stems**.
   Tout nom qui commence par `paroles`, `parole` ou `lyrics`, en `.txt` ou `.rtf`, convient aussi. Pour un MP3
   séparé par ReaCue, tu peux le mettre **à côté du MP3 d'origine** (ou dans le dossier
   `…-stems/htdemucs_6s/`).
4. Onglet **Morceau** : la pastille affiche **Paroles : N lignes** (clic dessus, ou **Ouvrir le dossier**,
   pour retrouver l'emplacement). Clique **Mettre à jour les téléphones** (ou action **ReaCue - Republier
   le prompteur**) : rien n'est modifié dans le projet.

**Tu dois voir** dans le résultat : `Prompteur publié : … N lignes de paroles`. Sur le téléphone, en vue **Chant**, les lignes
défilent avec le morceau.

Les lignes sont calées automatiquement sur le stem de voix. Si une ligne tombe mal, tu peux la caler à la
main avec un fichier d'ancres `paroles_calage.json` (voir la section *Paroles* du LISEZMOI).

**Mot par mot** (composant facultatif `Install ReaCue Words`, [chapitre 20.5](#205-paroles-mot-par-mot-et-paroles-automatiques)) :
chaque mot est placé à son vrai moment, à l'intérieur des lignes déjà calées. Sur le téléphone (vue
**Chant**), le **mot en cours est surligné** et les mots déjà chantés sont estompés ; dans la grille PDF,
chaque mot va dans sa mesure. Une ligne mal reconnue garde simplement le calage par ligne.

**Pas de texte sous la main ?** Si les *paroles automatiques* sont installées (Whisper, avec le même
`Install ReaCue Words`) et que le morceau a un **stem voix**, ReaCue transcrit ce stem et écrit un brouillon
**`paroles (auto).txt`** dans le dossier du morceau ; la pastille devient orange : **Paroles : auto (N
lignes)**. Clique dessus pour ouvrir le brouillon, corrige-le à l'oreille (sur place, ou renomme-le
`paroles.txt`), puis **Mettre à jour les téléphones**. Les lignes en tête qui commencent par `#` sont des
commentaires (ignorés).

| Règle | Détail |
|---|---|
| Ton fichier d'abord | un `paroles.txt` (ou `lyrics.txt`…) à toi est toujours prioritaire : le brouillon n'est alors plus utilisé |
| Une seule fois | le brouillon est créé une fois et **jamais écrasé** ; pour en refaire un, supprime-le |
| C'est un brouillon | la reconnaissance du chant fait des erreurs : relis-le avant la répétition ; la grille PDF le signale en bas de page |
| Jamais bloquant | si la transcription échoue ou ne trouve pas de chant, le morceau est prêt sans paroles, comme avant |
| Désactiver | réglage `lyrics_auto` = `"off"` ([annexe](#21-annexe--tous-les-réglages)) |

### 12.1 Conserver les temps des paroles automatiques

Quand Whisper génère les paroles, ReaCue conserve maintenant le début et la fin des lignes dans
**`paroles (auto).timing.json`**, à côté du brouillon texte. Ces temps sont repris à la publication,
au lieu de replacer les lignes par estimation des syllabes. Les corrections manuelles de calage restent
prioritaires. Si le texte ou le stem voix change, des temps périmés ne sont pas réutilisés.

Pour un ancien brouillon sans ce fichier : ouvre le morceau, garde le composant Paroles/Whisper installé,
puis **republie le prompteur**. ReaCue peut transcrire à nouveau une fois pour récupérer les temps si le
texte correspond ; prévois plusieurs minutes. Le brouillon existant n'est pas écrasé. Si tu as modifié
le texte et qu'il ne correspond plus, le placement suit la procédure d'alignement des lignes.

Un fichier `paroles.txt` importé n'est pas une transcription Whisper et garde son propre alignement.
Les avertissements de publication distinguent maintenant le composant mot à mot manquant, un échec
et un calage partiel. Vérifie les lignes concernées à l'écoute : un résultat automatique n'est pas
une garantie de synchronisation parfaite sur tous les chants.

---

## 13. Ouvrir le prompteur sur les téléphones

1. Connecte le téléphone au **même Wi-Fi** que l'ordinateur.
2. Trouve l'adresse IP de l'ordinateur (si tu ne l'as pas notée à l'étape 4) :
   - Mac : *Réglages Système → Wi-Fi → Détails…* (à côté du réseau connecté) → **Adresse IP** ;
   - Windows : *Paramètres → Réseau et Internet → Wi-Fi → propriétés du réseau* → **Adresse IPv4**.
3. Sur le téléphone, ouvre le navigateur et tape : **`http://<adresse IP>:8080/prompteur.html`**
   (exemple : `http://192.168.1.20:8080/prompteur.html`). Attention : `http`, pas `https`.
4. Choisis ton rôle : **Batterie**, **Basse**, **Guitare rythm.**, **Guitare solo**, **Chant**, **Général**,
   **Régie** ou **Lumière** (le choix est mémorisé sur ce téléphone ; le bouton **Rôle** permet d'en changer).
5. Lance la lecture dans REAPER : le prompteur suit la position (section, mesure, temps).

**Tu dois voir** le voyant vert en haut à droite (liaison avec REAPER active ; rouge = liaison perdue), les trois
afficheurs **MESURE · TEMPO · TON**, la section en cours (voyants verts = temps de la mesure, « 3/16 » = mesure
dans la section) et, en bas, **ENSUITE / DANS n mes** au-dessus de la mini-structure du morceau (touche-la pour
afficher ou masquer la liste des sections).

<img src="images/prompter_drums_fr.png" width="200"> <img src="images/prompter_vocals_fr.png" width="200">

<img src="images/prompter_vocals_fr_tablet.png" width="600">

| Rôle | Ce qu'il montre |
|---|---|
| **Batterie** | groove de la section, grille de la mesure en cours (16 pas, ou triolets pour un morceau shuffle), fills, crashs, arrêts et reprises ; une ligne par élément : Crash, Ride, Charley, **Charley ouv.**, Caisse cl., Tom 1, Tom 2, Tom bas, Gr. caisse |
| **Basse**, **Guitare rythm.** | accord en cours (carte claire ; Basse : note de basse) et suivant avec décompte, grille de la section (mesure en cours en orange), tonalité, entrées et sorties ; transposés si les stems le sont dans ReaCue Studio |
| **Guitare solo** | solos, accords, entrées |
| **Chant** | paroles défilantes, ligne suivante et décompte avant chaque entrée ; avec les paroles mot par mot, le **mot en cours surligné** |
| **Général** | structure et accords |
| **Régie** | télécommande du concert, protégée par un code PIN ([16.5](#165-piloter-depuis-un-téléphone-régie)) |
| **Lumière** | cues grandMA3, cue en cours, timecode, fichiers à importer ([16.9](#169-lumière--grandma3)) |

Quand une section a une **note** (champ `notes` des données publiées, modifiable plus tard dans ReaCue Studio),
elle s'affiche dans un cadre rose sous la grille, pour tous les rôles.

Sur une tablette à l'horizontale, la vue Batterie met la position (section, mesure, fill à venir) et la grille de la mesure côte à côte ; seules les lignes des éléments joués s'affichent :

<img src="images/prompter_drums_fr_tablet.png" width="600">

La vue Batterie est plus précise si la **transcription ADTOF** est installée, les accords si le **modèle
d'accords** l'est ([chapitre 20](#20-composants-facultatifs)) ; sinon ReaCue utilise ses propres règles.

Conseils :

- **Écran d'accueil** : iPhone : bouton *Partager → Sur l'écran d'accueil* ; Android : menu **⋮ → Ajouter à
  l'écran d'accueil**. La page s'ouvre alors en plein écran, comme une application.
- **Mise en veille** : touche le bouton **⛶** (plein écran), qui demande au téléphone de rester allumé. Si
  l'écran s'éteint quand même, désactive le verrouillage automatique pendant la répétition (iPhone :
  *Réglages → Luminosité et affichage → Verrouillage automatique → Jamais* ; Android : *Affichage → Mise en
  veille de l'écran*).
- **Adresse qui change** : la box peut donner une autre adresse IP à l'ordinateur d'un jour à l'autre, et les
  favoris des téléphones ne marchent plus. Dans l'interface de ta box ou de ton routeur, cherche
  **« Réservation DHCP »** (ou « bail statique », « IP fixe ») et réserve l'adresse actuelle pour
  l'ordinateur. En concert, un petit routeur de voyage dédié au groupe évite toute surprise.
- Le bouton **FR/EN** change la langue du prompteur sur ce téléphone.

### 13.1 Prompteur : mode Scène et détails

<img src="images/design_prompter.png" width="300" alt="Prompteur guitare en mode Scène">

Sur le prompteur, touche **SCÈNE** : la liste détaillée des sections et certaines commandes secondaires
s'effacent, tandis que la section, les accords/paroles/batterie du rôle, les notes et le prochain changement
restent disponibles. **DÉTAILS** rétablit la vue complète. Le rôle et le voyant de liaison restent visibles,
et ce choix est mémorisé sur cet appareil. Le mode Scène ne change pas le calage ni le son.

Pour changer de langue ou accéder au bouton plein écran, repasse par **DÉTAILS**. Le plein écran et le
maintien de l'écran allumé dépendent du navigateur ; teste le téléphone avant le concert. La mise en
page a été vérifiée dans Chromium à 390 × 844 ; les essais Safari/iPhone restent nécessaires.

---

## 14. Régler le click, les annonces et les in-ears

Fenêtre **ReaCue**, onglet **Réglages**. Chaque changement est enregistré tout de suite (« enregistré »
s'affiche) et **s'applique à la prochaine préparation** : clique **Re-préparer** dans l'onglet Morceau
(la structure validée est gardée), ou **Reconstruire le concert**. La vue est **simple** par défaut (langue,
décompte, annonces, voix, sorties, détection de structure, licences) ; **Réglages avancés** ajoute PIN,
annonce avant la section, langue / voix / débit du décompte, volumes, tempo, modèle de séparation et dossiers.

<img src="images/window_settings_fr.png" width="420">

Exemples courants :

| Je veux… | Dans l'onglet Réglages | Clé du fichier |
|---|---|---|
| 1 seule mesure de décompte | *Décompte avant le morceau* : ◀ jusqu'à **1 mes.** | `"count_in_bars": 1` |
| Le décompte en français | *Décompte* : **un deux trois quatre** | `"count_lang": "fr"` |
| Pas d'annonces vocales, seulement le click | *Annonces vocales* : **non** | `"voice_cues": false` |
| Click plus fort | *Volume du click* : ▶ | `"click_volume": 0.8` |
| Click et voix seulement dans les in-ears (sorties 3/4), pas en façade | *Sortie click + voix* : **sorties 3/4**, *Aussi en façade* : **non** | `"click_hw_output": 2` et `"click_to_master": false` |
| Séparation en 4 stems au lieu de 6 | *Séparation de stems* : **4 stems** | `"stems_model": "htdemucs"` |
| Sections par ReaCue seul (sans SongFormer) | *Détection de structure* : **ReaCue seul** | `"structure_engine": "reacue"` |
| Accords par la détection de ReaCue, même si le modèle est installé | (fichier seulement) | `"chords_engine": "reacue"` |
| Batterie par les règles de ReaCue, même si ADTOF est installé | (fichier seulement) | `"drums_engine": "reacue"` |
| Paroles calées par ligne seulement (pas mot par mot) | (fichier seulement) | `"words_engine": "off"` |
| Forcer la langue chantée (mot par mot, paroles automatiques) | (fichier seulement) | `"words_language": "fr"` |
| Pas de brouillon de paroles automatiques | (fichier seulement) | `"lyrics_auto": "off"` |

<img src="images/window_settings_advanced_fr.png" width="420">

L'onglet montre aussi la **version installée**. Les réglages sont dans le fichier **`reacue_settings.json`**
(dossier des ressources de REAPER, menu *Options → Show REAPER resource path in explorer/finder* → dossier
**`ReaCueMCP`**) : tu peux aussi l'éditer avec TextEdit ou le Bloc-notes, en respectant la syntaxe JSON.
Pour `click_hw_output` : `0` = sorties 1/2, `2` = sorties 3/4, `4` = sorties 5/6, etc.

Pour les voix des annonces (`announce_voice`), voir la section *Réglages* du LISEZMOI. La liste complète des
clés, avec leur valeur par défaut, est dans l'[annexe (chapitre 21)](#21-annexe--tous-les-réglages) ; les
réglages lumière se font dans l'onglet **Lumière** ([16.9](#169-lumière--grandma3)).

### 14.1 Performances : Standard, Rapide et threads CPU

Dans **Réglages → Réglages avancés**, choisir **Standard** pour conserver la qualité initiale ou
**Rapide** pour réduire le travail de Demucs, SongFormer et Whisper. Rapide peut modifier les résultats :
compare les stems, la structure et les paroles avant de valider un morceau. Le modèle de stems sélectionné
reste le même. **Threads CPU** propose auto / 1 / 2 / 4 / 8 ; plus de threads ne signifie pas toujours plus vite.

Sur Mac, après installation du composant Structure, double-clique sur **Optimize ReaCue Mac.command**.
L'outil compare des inférences SongFormer sur CPU (modèles chargés une seule fois, échauffement puis deux
mesures par réglage) et enregistre le meilleur nombre de threads sur cet extrait. Prévois plusieurs minutes.
Cela ne modifie pas le profil de qualité. Le résultat n'est pas une garantie pour les autres modèles.
Pour mesurer sur un extrait réel plutôt que sur le signal synthétique de 20 s :

```bash
.venv-structure/bin/python reacue_structure.py benchmark --input "/chemin/extrait.wav" --threads 1,2,4 --save
```

Les Mac sans MPS fonctionnel utilisent le CPU. Sur une série M compatible, les moteurs adaptés utilisent
Metal/MPS, avec reprise sur CPU en cas d'échec ; l'étalonnage ci-dessus force le CPU, mais pas les analyses
normales. Reviens à **Standard** et **auto** pour retrouver les réglages initiaux.

---

## 15. Relier Claude Desktop (facultatif)

Tout ReaCue marche sans Claude. Relier [Claude Desktop](https://claude.ai/download) permet en plus de
piloter ReaCue en français courant : corriger la structure, changer un réglage, naviguer dans le morceau.

**Prérequis**

- Claude Desktop installé sur **le même ordinateur** que REAPER, et connecté à ton compte Claude (un
  abonnement peut être nécessaire selon l'offre : vérifie les conditions actuelles sur claude.ai) ;
- ReaCue installé (étape 4) et REAPER ouvert, avec le pont qui tourne.

**Relier ReaCue à Claude Desktop**

1. Si tu as répondu `o` à la question « Déclarer ReaCue dans Claude Desktop » à l'étape 4, c'est déjà fait.
   Sinon, **relance l'installateur** (`Install ReaCue.command` / `.bat`) et réponds `o` à cette question.
   L'installateur ajoute le serveur `reacue` à la configuration de Claude Desktop (une copie de sauvegarde
   de l'ancienne configuration est gardée).
2. **Quitte complètement Claude Desktop** puis relance-le (Mac : menu *Claude → Quitter*, pas seulement
   fermer la fenêtre ; Windows : clic droit sur l'icône Claude près de l'horloge → *Quitter*, si elle y est).
3. **Ouvre une nouvelle conversation.**

**Vérifier que les outils ReaCue sont là**

Selon ta version de Claude Desktop, les outils des serveurs reliés se trouvent derrière une icône d'outils
ou un menu « connecteurs » / « outils » près de la zone de saisie. Tu dois y voir **reacue** avec ses outils
(`prepare_song`, `set_sections`, `reaper_status`…). Le plus simple pour tester : écris « vérifie que REAPER
répond ». Claude utilise `reaper_status` (il peut te demander l'autorisation la première fois) et doit
répondre que REAPER et le pont sont connectés.

**Exemples de phrases**

| Tu dis | Ce qui se passe |
|---|---|
| « Prépare le morceau ouvert dans REAPER » | Nouveau morceau : analyse complète. Morceau déjà préparé dont tu as modifié les régions : tes régions sont reprises. Morceau déjà préparé sans modification : **nouvelle analyse** (la structure validée est remplacée) — pour seulement reconstruire, utilise plutôt le bouton *Re-préparer* |
| « Le refrain 1 commence mesure 37 » | Structure corrigée, tout est reconstruit |
| « Renomme la section 6 en Solo » | Région renommée, recolorée, annonce changée |
| « Republie seulement le prompteur » | Prompteur mis à jour, rien ne change dans REAPER |
| « Va au refrain 2 » | Le curseur de REAPER se place au début de la région |
| « Une seule mesure de décompte » | Réglage changé, click et annonces reconstruits |

**Ce qui se met à jour tout seul** : après chaque demande de ce type, les régions, marqueurs, pistes CUES /
VOIX / CLICK dans REAPER et le prompteur des téléphones (qui relit ses données toutes les 2 secondes). Rien à
relancer.

**Si ça ne marche pas**

| Problème | Solution |
|---|---|
| reacue n'apparaît pas dans les outils | Relance l'installateur en répondant `o`, puis quitte complètement Claude Desktop et relance-le |
| Claude dit que REAPER ne répond pas | REAPER doit être ouvert ; redémarre-le pour relancer le pont ; une fenêtre restée ouverte dans REAPER bloque aussi le pont |
| Les nouveautés de ReaCue ne sont pas visibles | Les outils sont chargés au début d'une conversation : après une mise à jour de ReaCue, **ouvre une nouvelle conversation** (et relance Claude Desktop) |
| « le projet ouvert ne contient plus les pistes du dernier morceau » | Tu as changé de projet (ou consolidé) : demande « prépare le morceau ouvert » pour l'analyser |

---

## 16. Mode concert : plusieurs morceaux dans un projet

Pour un concert (ou une répétition générale), ReaCue enchaîne tes morceaux **déjà préparés** dans un seul
projet REAPER. Chaque morceau garde tout ce que tu as validé : stems, tempo, structure, annonces, click.

**Avant de commencer :** chaque morceau doit avoir été préparé (étape 10) **et son projet enregistré**
(**Cmd+S** / **Ctrl+S**). Un projet enregistré avant la préparation entre dans le concert sans sections.

### 16.1 Construire le concert

**Dans la fenêtre ReaCue, onglet Concert :**

<img src="images/window_concert_fr.png" width="420">

1. À gauche, **Morceaux** : les projets trouvés dans `Documents/REAPER Media` (réglage *Dossier des
   projets*), avec leur tempo ; **✓** = préparé, *à préparer* en orange sinon. **Actualiser** relit le dossier.
2. Clique **+** sur chaque morceau, dans l'ordre du concert : ils s'ajoutent à droite, dans la **Setlist**.
   **▲ ▼** changent l'ordre, **✕** retire un morceau.
3. **Renommer** : donne un nom au concert (par ex. « Samedi 15 »).
4. **Construire**. Un morceau pas préparé est signalé avant (tu peux construire quand même). La construction
   prend quelques secondes ; le concert **s'ouvre tout seul dans un nouvel onglet** de REAPER.

**Plusieurs morceaux à préparer ?** Sous les boutons, **Préparer tous les morceaux non préparés** (ou coche
des morceaux dans la liste → **Préparer la sélection**). ReaCue les prépare **l'un après l'autre en
arrière-plan** : chaque projet est ouvert dans un onglet, *Tout faire*, enregistré, puis l'onglet est
refermé. La progression s'affiche (✓ prêt, ● en cours avec l'étape, ✗ échec avec la raison) ; **Arrêter**
s'arrête après le morceau en cours.

<img src="images/window_batch_fr.png" width="420">

Depuis l'onglet **Morceau**, le bouton **Ajouter à un concert** ajoute le morceau ouvert à une setlist
(nouvelle ou existante) sans quitter le morceau.

En bas de l'onglet Concert, **Concerts existants** : **Modifier** recharge sa setlist dans l'éditeur,
**Ouvrir** l'ouvre dans un nouvel onglet. Après une modification, le bouton devient **Reconstruire**.

**Avec Claude Desktop** (étape 15) : écris par exemple

> Construis un concert « Samedi 15 » avec : Demo Song, Second Demo, Third Demo

Claude trouve les projets par leur nom dans `Documents/REAPER Media` (réglage `projects_dir`) et répond avec
le tableau du concert : début, tempo, mesures et sections de chaque morceau. Les avertissements (morceau sans
régions…) s'affichent dans sa réponse.

**Sans Claude** (ligne de commande, depuis le dossier `ReaCue`) :

- Mac : `.venv/bin/python -m reacue_mcp.cli concert --name "Samedi 15" --songs "Demo Song" "Second Demo"`
- Windows : `.venv\Scripts\python reacue_cli.py concert --name "Samedi 15" --songs "Demo Song" "Second Demo"`

**Tu dois voir** dans `Documents/REAPER Media/Concerts/` (réglage `concert_dir`) : `Samedi 15.RPP`,
`Samedi 15.setlist.json`, `Samedi 15.concert.lua` et `Samedi 15.prompteur.json`. Ne les modifie pas à la main.

La construction prend quelques secondes ; les accords, paroles et batterie du prompteur sont ensuite calculés
en arrière-plan (quelques minutes la première fois, puis c'est gardé).

### 16.2 Ouvrir le concert

1. Fenêtre **ReaCue**, onglet **Concert** → **Concerts existants** → **Ouvrir** à côté de **Samedi 15**
   (ou, juste après la construction, il est déjà ouvert).
2. Le concert s'ouvre dans un **nouvel onglet** (ton projet en cours reste ouvert dans le sien), et la
   fenêtre passe toute seule sur l'onglet **Scène**.

**Tu dois voir** une piste par instrument pour tout le concert (Chant, Batterie, Basse, Guitares…), une couleur
par morceau, les pistes CLICK / VOIX / CUES en bas, des régions « Demo Song · Refrain 1 », et en haut une
ligne **Morceaux** avec « 1 · Demo Song », « 2 · Second Demo »… L'onglet Scène affiche **1 / 3 · Demo Song**.

<img src="images/window_stage_fr.png" width="420">

> Astuce : **clic droit dans la fenêtre** pour l'ancrer en bas de REAPER (elle devient une barre de transport
> compacte) ou la détacher.

### 16.3 Jouer

1. Appuie sur **Espace** (ou sur le gros bouton vert **Lecture** de la fenêtre) : décompte, puis le morceau.
2. À la fin du morceau, la lecture **s'arrête toute seule** et le curseur se place sur le décompte du suivant.
   La fenêtre affiche **2 / 3 · Second Demo**.
3. Quand le groupe est prêt : **Espace**.

L'onglet Scène montre la section en cours, « mesure x / N », le temps restant du morceau et du concert, et
le morceau suivant. Ses boutons :

| Bouton | Effet |
|---|---|
| **Précédent** | début du morceau en cours ; au début, morceau précédent |
| **Début** | revient au décompte du morceau en cours |
| **Lecture / Pause** | lance ou met en pause |
| **Stop** | arrête |
| **Suivant** | va au décompte du morceau suivant |
| Pastilles des **sections** | va au début de la section (la lecture continue) |
| **Setlist** | liste des morceaux : un clic = aller au morceau ; **Reconstruire le concert** |

Pendant la lecture, **Stop**, **Précédent**, **Suivant** et le changement de morceau demandent un **double
appui** : le premier appui affiche « encore ? » en orange, le second (dans les 2 secondes) exécute.

Pour une pédale ou un raccourci clavier : les actions **ReaCue - Morceau suivant** et **ReaCue - Morceau
précédent** (*Actions → Show action list* → sélectionne l'action → **Add…** dans *Shortcuts for selected action*).

> ⚠️ L'arrêt automatique, la télécommande et le profil des instruments ne marchent que si la fenêtre
> **ReaCue** est ouverte (n'importe quel onglet, même ancrée). Ne la ferme pas pendant le concert.

### 16.4 QR code pour les musiciens

1. Dans l'onglet Scène, clique sur **QR**.
2. Le QR code s'affiche en grand avec l'adresse en clair dessous (ex. `http://192.168.1.20:8080/prompteur.html`)
   et le code PIN de la Régie.
3. Chaque musicien, sur le **même Wi-Fi**, ouvre l'appareil photo de son téléphone, vise le QR code et touche
   le lien : le prompteur s'ouvre ; il choisit son rôle.
4. Clique sur **Fermer** (ou sur le QR, ou Échap) pour revenir.

<img src="images/window_qr_fr.png" width="300">

L'adresse est recalculée à chaque clic : si l'ordinateur a changé d'adresse, le QR est quand même juste.
Si « Adresse IP de l'ordinateur introuvable » s'affiche : l'ordinateur n'est connecté à aucun réseau.

### 16.5 Piloter depuis un téléphone (Régie)

1. Sur le téléphone de la personne qui pilote : ouvre le prompteur (QR code), touche **Rôle** puis **Régie**.
2. Touche un bouton (par ex. **Lecture**) : le téléphone demande le **code PIN**. Il est affiché dans
   l'onglet Scène (bouton **PIN 1234**, et sous le QR code) et dans l'onglet Réglages. Tape-le, **OK**.
3. Le bouton s'entoure de vert quand REAPER a exécuté la commande.

<img src="images/prompter_regie_fr.png" width="200"> <img src="images/prompter_regie2_fr.png" width="200">

La Régie offre Lecture/Pause, Stop, Précédent, Début, Suivant, la setlist, les sections et les
**instruments** (16.8), avec le même double appui pendant la lecture. Le PIN est mémorisé sur le téléphone ; **Changer de code** pour le retaper.
Pour changer le PIN : bouton **PIN** de l'onglet Scène (4 chiffres).

> ⚠️ Le PIN évite les fausses manipulations, **pas les attaques** : toute personne sur le même réseau peut
> piloter REAPER par son interface web. En concert, utilise un Wi-Fi réservé au groupe.

### 16.6 Modifier un morceau du concert

1. Ouvre **le projet du morceau** (pas le concert), corrige (structure, réglages…), **Appliquer** ou **Re-préparer** (enregistré tout seul).
2. Reviens dans le concert, onglet Scène → **Reconstruire le concert** → **OK** (ou onglet Concert →
   **Modifier** → **Reconstruire**).

Les modifications faites directement dans le projet concert sont **écrasées** par la reconstruction.

### 16.7 Vérifier avant de jouer

Avant la balance ou le concert, clique sur **Vérifier** dans l'onglet Scène.

<img src="images/window_check_fr.png" width="420">

1. Une liste s'affiche, avec un résumé en haut : **Tout est prêt ✓** (vert), **N point(s) à surveiller**
   (orange) ou **N problème(s)** (rouge).
2. Chaque ligne a une pastille et un détail court :

| Ligne | Ce qui est vérifié | Si ce n'est pas vert |
|---|---|---|
| Fichiers audio | chaque fichier du concert est lisible (pas « OFFLINE ») | **Corriger** remet les médias en ligne ; sinon voir Dépannage (OFFLINE) |
| Annonces vocales | les fichiers des annonces sont présents | **Corriger** reconstruit le concert |
| Morceaux préparés | chaque morceau a une structure et un tempo | prépare le morceau dans son projet, enregistre, reconstruis |
| Concert à jour | aucun projet de morceau n'a changé depuis la construction | **Corriger** reconstruit le concert |
| Pont ReaCue | REAPER répond à ReaCue | redémarre REAPER |
| Interface web | le prompteur est servi (port) | étape 6 |
| Adresse réseau | l'ordinateur a une adresse (pour le QR) | connecte-le au Wi-Fi du groupe |
| Carte son | REAPER joue sur une carte son | *Préférences → Audio → Device* |
| Sorties click et annonces | les sorties choisies pour CLICK / VOIX existent, pistes non coupées | branche la bonne carte son ou change `click_hw_output` (étape 14) |
| Prompteur des téléphones | la page et le concert sont publiés | **Corriger** les republie |
| Téléphones Régie | un téléphone en Régie a été vu récemment | (information seulement) |
| Stems coupés | les instruments coupés (profil « joué en live » ou à la main) | (information seulement) |

3. **Revérifier** relance la liste ; **Fermer** (ou Échap) revient à l'onglet Scène.

> Sans concert ouvert, **Vérifier** contrôle seulement la partie système (pont, interface web, adresse,
> carte son).

### 16.8 Instruments : couper un stem, « joué en live »

Sous les sections, l'onglet Scène a une rangée **Instruments (stems)** : un bouton par piste d'instrument du
concert (Chant, Batterie, Basse, Guitares, Guitare solo, Claviers, Autres, Mix — jamais CLICK, VOIX ni CUES).
Sous chaque nom : **joué** ou **coupé**.

| Geste | Effet |
|---|---|
| **Clic** | couper / remettre ce stem (pendant la lecture hors répétition : **double appui**) |
| **Appui long** | **solo** : on n'entend que lui (encore un appui long = retour) |
| **Tout entendre** | remet tous les stems (encore = retour au profil) |

Ces choix à la main durent jusqu'au morceau suivant.

**« Joué en live » : le profil du concert.** Si le groupe joue pour de vrai la batterie et la basse, leurs
stems doivent être coupés sur tout le concert. Clique **Joué en live…** :

<img src="images/window_live_fr.png" width="420">

1. Coche ce que le groupe joue en vrai (ex. **Batterie**, **Basse**) : ces stems seront coupés au début de
   chaque morceau.
2. **Exceptions par morceau** : clique sur une case pour la faire passer de **·** (profil) à **stem** (on
   garde le stem sur ce morceau) puis **live** (on le coupe sur ce morceau seulement). Exemple : le bassiste
   passe aux claviers sur un morceau → case Basse de ce morceau = **stem**.
3. **Fermer**.

Le profil est enregistré avec le concert (dans `Samedi 15.setlist.json`) et **gardé quand tu reconstruis**.
Il est aussi accessible dans l'onglet Concert (**Joué en live…**). La mesure de décompte de la répétition
n'écrase pas tes choix.

Sur les téléphones, chaque musicien voit en haut **« ton stem est coupé »** (orange) ou **« ton stem est
joué »** (vert). En **Régie**, les mêmes boutons : toucher = couper / remettre, appui long = solo, **Tout
entendre**.

<img src="images/prompter_concert_fr.png" width="200"> <img src="images/prompter_concert_vocals_fr.png" width="200">

Avec Claude : « dans le concert Samedi 15, la batterie et la basse sont jouées en live, sauf la basse sur
Second Demo » (outil `set_live_profile`, sans reconstruire).

### 16.9 Lumière : grandMA3

À chaque préparation et à chaque construction du concert, ReaCue écrit un cue par section pour une console
grandMA3 (dossier `grandMA3/` à côté du projet, ou `Concerts/grandMA3/<concert>/`) : une Sequence par
morceau, un Timecode, une fiche de conduite (CSV avec un effet suggéré par section).

1. Sur un téléphone ou l'ordinateur de la régie lumière, ouvre le prompteur et choisis le rôle **Lumière** :
   liste des cues, cue en cours surligné, liens pour télécharger les trois fichiers.
2. Sur la console : importe la Sequence, puis le Timecode.
3. **REAPER envoie le timecode** (MTC ou LTC) : le concert s'arrête entre les morceaux, la console suit.

**Première configuration (une seule fois).**

1. Dans l'onglet **Lumière** de la fenêtre ReaCue (ou dans `reacue_settings.json`), choisis la ou les sorties :
   - **console en LTC** : `"gma3_ltc_output": 7` (sortie 7 de la carte son → entrée LTC XLR de la console) ;
   - **grandMA3 onPC sur le même Mac** : `"gma3_mtc_output": "IAC Driver Bus 1"` (Configuration audio et MIDI →
     Fenêtre → Afficher le studio MIDI → Gestionnaire IAC → cocher *Le périphérique est en ligne*) ;
   - **onPC sur un autre ordinateur** : `"gma3_mtc_output": "Réseau MIDI"` ou le nom de la session (Configuration
     audio et MIDI → Configuration du réseau MIDI : crée une session, connecte le PC ; sous Windows, rtpMIDI) ;
   - au besoin `"gma3_tc_slot": 1`, `"gma3_tc_start": "01:00:00:00"`, `"gma3_fps": 25`.
2. REAPER : *Préférences → Audio → MIDI Devices* : active cette sortie MIDI (MTC seulement).
3. Prépare un morceau : les pistes `TIMECODE LTC` / `TIMECODE MTC` apparaissent. Double-clic sur l'item du
   générateur → *Propriétés de la source* : images/s = `gma3_fps`, départ = `gma3_tc_start`, *Send MIDI (MTC)*
   coché sur la piste MTC seulement. OK, puis **Préparer** à nouveau (ou, onglet **Lumière**, **Créer / mettre
   à jour les pistes timecode**) : ReaCue le mémorise pour tous les morceaux et concerts. Les pastilles de
   l'onglet **Lumière** passent au vert (sortie LTC, périphérique MIDI activé, pistes, générateur réglé).
4. Console : copie le contenu du dossier d'export (`grandMA3/` à côté du projet, ou
   `Concerts/grandMA3/<concert>/`) dans `grandMA3/` à la racine d'une clé USB, importe le plugin `ReaCue.xml`
   (pool Plugins → Import) et lance-le : Sequences, Timecode et TC Slot en un appui.
5. Entrée de la console (une fois) : *Menu → Output Configuration → Connector Configuration* : SMPTE Mode = In et
   SMPTE TC = slot (LTC), ou MIDI TC Mode = In et MIDI TC = slot (MTC).

<img src="images/window_lighting_fr.png" width="420">

Test : onglet **Lumière** → **Envoyer 10 s de test** : seules les pistes `TIMECODE` jouent (le public n'entend
rien), puis tout est rétabli ; sur la console, le TC Slot passe au vert (le LTC / MTC va dans un seul sens :
ReaCue ne peut pas le vérifier lui-même). Puis lecture dans REAPER → le timecode de la console défile et les cues partent ; stop → le show Timecode
s'arrête ; relance → il repart. Réglage utile : `gma3_song_slot` (ex. `600` : chaque morceau démarre toutes
les 10 minutes rondes). Reconstruis le concert après un changement.

---

## 17. En répétition

### 17.1 Le mode répétition du concert (boucle et ralenti)

Dans un concert ouvert, avec la fenêtre **ReaCue** (onglet **Scène**) :

1. Clique sur **Répétition** (ou, sur le téléphone en Régie, touche **Répétition**). Un bandeau orange
   **RÉPÉTITION** s'affiche ; l'arrêt automatique entre les morceaux est coupé.
2. **Boucler une section** : touche sa pastille (dans la fenêtre ou sur le téléphone). La lecture part
   **une mesure avant** la section : pendant cette mesure, on n'entend que le **click et les annonces**
   (« one two three four »), puis la section joue, et à la fin elle **recommence avec la même mesure de
   décompte**, sans fin.
3. **Boucler plusieurs sections** : touche une 2e section du même morceau (par ex. *Couplet 2* puis
   *Refrain 2*) : la boucle va du début de l'une à la fin de l'autre. Les sections bouclées sont soulignées en
   orange. Un 3e appui recommence une boucle simple.
4. **Ralentir** : boutons **100 %**, **90 %**, **80 %**, **70 %**. La hauteur ne change pas ; le click, les
   annonces et le prompteur suivent.
5. **Boucle off** arrête la boucle (la lecture continue). **Quitter** (dans la fenêtre) ou **Répétition ✓**
   (sur le téléphone) sort du mode : vitesse 100 %, arrêt automatique réactivé, réglages de REAPER remis
   comme avant.

> Pendant la mesure de décompte, les pistes des instruments sont coupées puis remises toutes seules. Si
> tu arrêtes la lecture pendant cette mesure, elles sont remises aussi.

### 17.2 Répéter un morceau seul (sans concert)

Ouvre le projet du morceau ; dans la fenêtre ReaCue, onglet **Scène** (« Morceau seul ») :

- **Début**, **Lecture**, **Stop** ; les musiciens entendent (ou voient sur le prompteur) le décompte, puis
  les annonces avant chaque section ;
- les **sections** en pastilles : un clic = y aller ;
- les **instruments** (couper, solo, tout entendre), comme en 16.8 ;
- **Répétition** : boucle sur une section ou une plage, avec la mesure de décompte avant chaque reprise et
  le ralenti, exactement comme en 17.1 ;
- la **Régie** sur téléphone marche aussi.

Il n'y a pas d'arrêt automatique ni de setlist (un seul morceau). Seul REAPER (et la fenêtre ReaCue pour la
boucle) doit tourner pendant la répétition : Claude n'est pas nécessaire.

### 17.3 ReaCue Studio : l'écran Travail

ReaCue Studio est une page web servie par REAPER (comme le prompteur), faite pour travailler un morceau sur
l'ordinateur ou une tablette.

1. Prépare le morceau (chapitre 10) : la publication crée aussi les **formes d'onde** des stems.
2. Ouvre la fenêtre **ReaCue** dans REAPER (elle exécute la boucle, la rampe, la transposition et l'export).
3. Dans le navigateur : **`http://localhost:8080/studio.html`** sur l'ordinateur, ou
   `http://<IP de l'ordinateur>:8080/studio.html` sur une tablette (l'adresse est affichée sous le QR code).
4. Au premier usage d'une boucle, d'une rampe, de la transposition ou d'un export, la page demande le **PIN**
   (fenêtre ReaCue, onglet **Scène**) : il est mémorisé sur l'appareil.

![ReaCue Studio, écran Travail](images/design_console.png)

| Zone | Ce qu'elle fait |
|---|---|
| Afficheurs (en haut) | POSITION mesure.temps.double-croche · TEMPS · TEMPO et vitesse en % · TON (± transposition) · SMPTE |
| Structure | clic = aller à la section ; double-clic = la boucler (avec la mesure de décompte, comme en 17.1) |
| Accords | défilent sous la tête de lecture ; clic = aller à l'accord |
| Lignes des stems | forme d'onde (partie jouée en couleur), **M** (muet), **S** (solo), volume ; clic = aller à cet endroit |
| Console (à droite) | pan (glisser ; double-clic = centre), vumètre, fader (double-clic = 0 dB), CLICK et VOIX compris |
| Pied de page | Début, Stop, Lecture/Pause (barre d'espace), Boucle, Section suivante ; BOUCLE · RAMPE · CLICK · VOIX ; voyants |
| Mon instrument | la piste choisie est coupée automatiquement (tu joues ta partie par-dessus) |
| TON − / + | transpose les stems d'un demi-ton ; double-clic sur l'afficheur TON = revenir à 0 |

**Rampe de vitesse** : place la lecture dans la section à travailler, clique sur **RAMPE**, règle par exemple
**de 85 % à 100 % en 8 passages**, puis **LANCER**. La section tourne en boucle ; à chaque reprise la vitesse
monte d'un palier (hauteur conservée) ; le compteur affiche « BOUCLE REFRAIN 1 · 4/8 ». Après le dernier
passage, la boucle continue à la vitesse finale. **ARRÊTER** (ou le bouton Boucle) remet 100 %.

> Le voyant **REAPER** est vert quand REAPER et la fenêtre ReaCue répondent, orange quand la fenêtre est
> fermée (mute, volume, transport marchent encore ; pas la boucle, la rampe, la transposition ni l'export).
> La transposition reste propre jusqu'à ±2 demi-tons environ ; au-delà, la voix et la batterie sonnent
> artificiellement. Elle modifie les items des stems : Ctrl/Cmd+Z dans REAPER l'annule.

### 17.3.1 Mode Scène et commandes précises

Le bouton **SCÈNE**, dans le bandeau de Studio, masque les commandes secondaires et agrandit la lecture.
**QUITTER** retrouve la vue complète. Le choix est mémorisé dans ce navigateur. Le bouton à quatre coins
active le **plein écran** si ton navigateur le permet ; ces deux commandes ne démarrent pas la musique.

| Contrôle | Souris / tactile | Clavier après sélection avec Tab |
|---|---|---|
| Fader de volume | glisser ; double-clic = 0 dB | ↑ / ↓ : 1 dB ; Maj : 0,1 dB ; Début : 0 dB ; Fin : −60 dB |
| Panoramique | glisser ; double-clic = centre | ← / → : 5 % ; Maj : 1 % ; Début : centre |
| M / S | mute / solo ; cibles agrandies sur écran tactile | Entrée ou Espace sur le bouton |

Un indicateur **CLIP** apparaît si REAPER signale une crête à 0 dB ou au-dessus pendant la lecture.
Baisse le niveau et vérifie le mix dans REAPER. Il indique la crête reçue, sans remplacer un contrôle
de toute la chaîne audio. La **barre d'espace** pilote l'écran actif (Travail, Concert ou Groupe),
et ne pilote pas un écran Travail caché depuis Biblio ou Lumière. Elle est ignorée pendant la saisie,
dans une fenêtre modale, sur un curseur et lors des répétitions automatiques de touche.

### 17.4 Exporter des stems et des régions (WAV / MP3)

Dans ReaCue Studio, bouton **EXPORTER** :

1. **Instruments** : coche ceux à exporter (TOUS / AUCUN), et **avec le click** si tu veux un click synthétisé
   sur la grille du morceau.
2. **Région** : morceau entier, une **section** (liste), des **mesures** « de → à », ou la **sélection
   REAPER** (sélection temporelle du projet).
3. **Fichiers** : un fichier par instrument, ou tout **mixé** en un seul fichier (ramené à -1 dBFS s'il
   dépasse : jamais d'écrêtage ; volume et pan des pistes appliqués au mix).
4. **Format** : **MP3** (128, 192, 256 ou 320 kbit/s ; 320 par défaut) ou **WAV** 24 bits.
5. **EXPORTER** : la progression s'affiche, puis les liens de téléchargement. Les fichiers sont aussi dans le
   dossier **`exports/`** à côté du projet, nommés `<Titre> - <Instrument> - <Section>.mp3`.

Exemples : la basse seule du refrain en MP3 pour la réviser dans le métro ; « tout sauf la guitare » mixé avec
le click, mesures 33 à 48, pour travailler ta partie ; chaque stem en WAV pour un autre logiciel.

### 17.5 ReaCue Studio : écrans Concert et Lumière

Le soir du concert, la page `studio.html` sert aussi de **poste de régie** sur l'ordinateur ou une tablette.

1. Ouvre le concert dans REAPER (chapitre 16) et la fenêtre **ReaCue** (elle exécute les commandes).
2. Dans ReaCue Studio, clique sur **CONCERT** (ou ouvre directement `studio.html#concert`). Au premier
   appui sur une commande, saisis le **PIN** (fenêtre ReaCue, onglet Scène).

![ReaCue Studio, écran Concert](images/design_concert.png)

| Zone | Ce qu'elle fait |
|---|---|
| Bandeau | voyant + LECTURE / PAUSE / ARRÊT, « MORCEAU n / N », titre ; RESTE (fin du morceau), CONCERT (temps écoulé), SMPTE · LTC |
| Setlist | un bloc par morceau (largeur = durée) : joué grisé, en cours en orange ; clic = aller au morceau |
| Sections | mesure de départ, nom, JOUÉ / EN COURS 3/16 / À VENIR ; clic = aller à la section |
| ◀ PRÉC. · LECTURE · SUIV. ▶ | morceau précédent (ou début du morceau), lecture / pause (barre d'espace), morceau suivant |
| Lumière | cues du morceau (n°, timecode, section, effet), cue en cours surligné, voyants LTC / MTC / export, TEST 10 S |

Pendant la lecture, **PRÉC.**, **SUIV.**, un bloc de la setlist et **TEST 10 S** demandent **deux appuis**
(« ENCORE ? »), comme dans la fenêtre ReaCue. Sans concert ouvert, l'écran montre le morceau seul (PRÉC. /
SUIV. passent d'une section à l'autre) avec un message.

3. Clique sur **LUMIÈRE** (`studio.html#lumiere`) pour la console grandMA3 :

![ReaCue Studio, écran Lumière](images/studio_lumiere_fr.png)

- **Cue en cours** en grand, puis tous les cues (par morceau) : clic = aller au cue.
- **Sorties timecode** : sortie LTC, périphérique MTC, TC Slot, images/s et départ (réglages de l'onglet
  Lumière au moment de l'export) ; voyant **EXPORT À JOUR** (sinon : *Exporter maintenant* dans l'onglet
  Lumière).
- **TEST 10 S** : seules les pistes TIMECODE jouent pendant 10 s (le public n'entend rien), puis tout est
  rétabli ; le bouton affiche le compte à rebours, un 2e appui arrête. Regarde sur la console que le TC Slot
  passe au vert.
- **Fichiers grandMA3** : téléchargement des Sequences, du Timecode et de la fiche de conduite.

> Les effets affichés sont les suggestions par type de section (lecture seule) ; leur modification viendra
> dans une prochaine version.

### 17.5.1 Utiliser la régie en mode Scène

Clique sur **SCÈNE** pour mettre en avant le morceau, le temps restant et les cues lumière comme sur
la capture ci-dessus. **QUITTER** rétablit les onglets, sans arrêter la lecture. La setlist et les boutons
PRÉC./SUIV. conservent leurs protections ; le mode Scène n'autorise pas davantage de commandes.
Pour sélectionner une section au clavier : Tab jusqu'à la ligne, puis Entrée ou Espace.

### 17.6 ReaCue Studio : écrans Biblio et Groupe

**Biblio** (`studio.html#biblio`) : la liste de tous tes morceaux (dossier des projets + concerts).

![ReaCue Studio, écran Biblio](images/studio_biblio_fr.png)

1. Ouvre la fenêtre **ReaCue** dans REAPER (elle publie la bibliothèque et exécute les commandes).
2. Dans ReaCue Studio, clique sur **BIBLIO**. Filtre par étape (compteurs du haut) ou cherche un titre.
3. Clic sur un morceau : il s'ouvre dans REAPER (nouvel onglet) et l'écran passe sur **TRAVAIL**. Un morceau
   « À PRÉPARER » s'ouvre aussi, mais prépare-le d'abord (onglet Morceau de la fenêtre).
4. Colonne **ÉTAPE** : calculée toute seule (AUTO) à partir du temps joué seul ou en groupe ; clique une case
   pour la régler à la main (MANUEL), « auto » pour revenir au calcul.

| Étape | Calcul automatique |
|---|---|
| Découvert | rien de mesuré |
| Travaillé seul | 5 min de lecture |
| Répété en groupe | 3 min de lecture avec au moins 2 prompteurs de musiciens connectés |
| Prêt pour la scène | préparé + répété en groupe sur 2 jours (2 min minimum chaque jour) |

**Groupe** (`studio.html#groupe`) : l'écran de la répétition.

![ReaCue Studio, écran Groupe](images/studio_groupe_fr.png)

1. Chaque musicien ouvre le prompteur sur son téléphone, choisit son rôle et peut taper son prénom.
2. **Notes** : écris « on coupe sur le 4 » à côté de la section, Entrée : la note apparaît en rose sur tous
   les prompteurs (2 à 3 s).
3. **Prêt** : chacun appuie sur « Prêt ? » en haut du prompteur ; l'écran Groupe affiche « PRÊTS 3 / 4 » et
   qui manque. **REMISE À ZÉRO** avant le morceau suivant.
4. **On reprend à…** : clic sur « Refrain 2 » : la lecture repart une mesure avant.

> Les musiciens connectés, les notes et l'étape manuelle passent par la fenêtre ReaCue : garde-la ouverte.

---

## 18. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| L'item affiche **OFFLINE** (Mac) | REAPER n'a pas le droit de lire le fichier, souvent dans *Téléchargements* | Copie le fichier dans le dossier du projet, puis glisse-le à nouveau dans REAPER (ou clic droit sur l'item → *Item properties…* → *Choose new file*). Autre solution : *Réglages Système → Confidentialité et sécurité → Fichiers et dossiers → REAPER*, active le dossier concerné, redémarre REAPER |
| « Le pont ReaCue ne tourne pas » | Le pont n'a pas démarré | Redémarre REAPER ; une fenêtre restée ouverte dans REAPER peut aussi le bloquer |
| Le prompteur affiche « REAPER ne répond pas » | Mauvais Wi-Fi, mauvaise adresse, interface web non activée, pare-feu | Vérifie l'étape 6 et l'étape 13 ; essaie `http://localhost:8080/` sur l'ordinateur |
| Les téléphones ne trouvent plus la page | L'adresse IP de l'ordinateur a changé | Nouvelle adresse (étape 13), puis réservation DHCP |
| Pas d'annonces vocales | Voix absente | Mac : *Réglages Système → Accessibilité → Contenu énoncé* ; Windows : *Paramètres → Heure et langue → Voix* |
| Séparation de stems très lente | Processeur occupé | Ferme les autres applications ; compte 1,5 à 2 fois la durée du morceau |
| Structure fausse | Détection automatique imparfaite | Étape 11 : bande de structure (cases orange), corrige puis *Appliquer*, ou demande à Claude ; tempo faux : tempo dans le nom des fichiers |
| Pastille « Structure : ReaCue » en orange | SongFormer n'est pas installé | Clic sur la pastille → installateur ; ou *Réglages → Vérifier l'installation* |
| Résumé : « Modèle d'accords indisponible… », « Transcription de batterie par modèle (ADTOF) impossible… », « Calage mot par mot impossible… » | Composant facultatif absent, en panne ou trop lent | Rien n'est perdu : ReaCue a pris sa propre méthode. Relance l'installateur du composant ([chapitre 20](#20-composants-facultatifs)) ; après un échec des accords, ReaCue ne réessaie pas sur le même audio pendant 1 h |
| Pas de `paroles (auto).txt` | Pas de stem voix, Whisper pas installé, `lyrics_auto` = `"off"`, ou tu as déjà un fichier de paroles | Sépare les stems, relance `Install ReaCue Words` ; un échec est mémorisé pour ce morceau (pas de nouvel essai à chaque publication) |
| Pas de grille PDF | Le dossier du morceau n'est pas trouvé, ou l'écriture a échoué (avertissement « Grille PDF non créée ») | Clic sur la pastille **Grille PDF —** ; vérifie que le dossier du morceau existe et n'est pas en lecture seule |
| Onglet Scène : « Aucun concert ni morceau ouvert » | L'onglet de projet en cours est vide | Onglet **Concert** → **Ouvrir** un concert, ou ouvre le projet d'un morceau |
| Un morceau du concert n'a pas de sections | Son projet a été enregistré avant la préparation | Ouvre son projet, *Tout faire*, puis *Reconstruire le concert* |
| Téléphone (Régie) : « Ouvre la fenêtre ReaCue… » | Fenêtre ReaCue fermée | Lance l'action **ReaCue** sur l'ordinateur |
| Régie : « Code PIN incorrect » | Mauvais code | Tape le code affiché par le bouton **PIN** de l'onglet Scène |
| La lecture ne s'arrête plus entre les morceaux | Fenêtre ReaCue fermée, ou mode répétition actif | Rouvre **ReaCue** (même ancrée en bas) ; sinon **Quitter** la répétition |
| Un stem reste coupé | Profil « joué en live » ou choix à la main | Onglet Scène : **Tout entendre**, ou **Joué en live…** pour changer le profil |
| **Vérifier** affiche du rouge | Voir la ligne concernée | Tableau de l'étape 16.7 ; **Corriger** quand le bouton est proposé |
| Après une répétition, des pistes restent muettes | REAPER fermé pendant la mesure de décompte | Enlève le mute des pistes (bouton **M**) ; la fenêtre les remet d'habitude toute seule |
| Journaux | — | Préparation et concert : `ReaCueMCP/cli.log` (dossier des ressources REAPER) ; séparation : `…-stems/demucs.log` à côté du morceau |

---

## 19. Pense-bête : un nouveau morceau, un concert

1. Fenêtre **ReaCue** → **+ Nouveau morceau** → un fichier **ou** un dossier de stems → titre → **OK**
   (copie dans `Documents/REAPER Media/<Titre>/`, nouvel onglet, projet enregistré).
2. **Tout faire** (stems si MP3 seul, structure, click, annonces, téléphones, enregistrement).
3. Vérifier la structure (cases orange de la bande, noms) ; au besoin **Renommer** / **◀ ▶** / **Fusionner** /
   **Couper** / **Supprimer** / **+ Section** (**Annuler** si besoin), puis **Appliquer**.
4. Facultatif : `paroles.txt` à côté des fichiers → **Mettre à jour les téléphones** (sans fichier, avec
   Whisper installé : corrige le brouillon `paroles (auto).txt`). La grille `Grille - <Titre>.pdf` est dans le
   dossier du morceau.
5. Plusieurs morceaux : onglet **Concert** → **Préparer tous les morceaux non préparés**.
6. Téléphones : `http://<IP>:8080/prompteur.html`, choisir son rôle.

**Un concert :**

1. Chaque morceau préparé **et enregistré** dans son projet.
2. Onglet **Concert** : **+** sur chaque morceau, **Renommer**, **Construire** (ou Claude : « Construis un concert “Samedi” avec : … »).
3. Le concert s'ouvre dans un nouvel onglet ; la fenêtre passe sur **Scène**.
4. Facultatif : **Joué en live…** → cocher ce que le groupe joue en vrai.
5. **Vérifier** → tout doit être vert (sinon **Corriger**).
6. **QR** → les musiciens scannent ; la personne qui pilote choisit **Régie** et tape le PIN.
7. **Espace** à chaque morceau ; la lecture s'arrête toute seule à la fin de chacun.
8. En répétition : **Répétition**, puis une section pour la boucler (2e section = plage), vitesse au besoin.

---

## 20. Composants facultatifs

ReaCue marche seul. Chaque composant facultatif améliore une partie de l'analyse, **tourne sur ton
ordinateur** (rien n'est envoyé en ligne, internet seulement pendant son installation), s'installe dans son
**propre environnement Python** à l'intérieur du dossier `ReaCue` (le `.venv` de ReaCue n'est jamais touché),
et peut être installé, relancé ou retiré à tout moment.

| Composant | Installateur | Ce qu'il apporte | À télécharger | Installation | Calcul par morceau (Mac Intel, une seule fois) | Licence |
|---|---|---|---|---|---|---|
| Séparation de stems | `Install ReaCue Stems` (ou question de l'étape 4) | un MP3 → 6 stems (Demucs) | ≈ 1 Go | 5 à 15 min | 5 à 8 min | MIT |
| Analyse de structure | `Install ReaCue Structure` (ou question de l'étape 4, oui par défaut) | sections plus justes (SongFormer) | ≈ 3 Go | 10 à 40 min | plusieurs minutes | **non commercial** (MuQ : CC BY-NC 4.0) ; « J'accepte » |
| Accords | `Install ReaCue Chords` | accords par modèle entraîné | ≈ 800 Mo (PyTorch, déjà en cache si les stems sont installés) + 60 Mo | 2 à 10 min | 1 à 2 min | MIT |
| Batterie | `Install ReaCue Drums` | transcription ADTOF du stem batterie | ≈ 300 Mo (PyTorch, idem) + 16 Mo | 3 à 10 min | 20 à 60 s | **non commercial** (CC BY-NC-SA 4.0) ; « J'accepte » |
| Paroles mot par mot et automatiques | `Install ReaCue Words` | chaque mot à son vrai moment ; brouillon de paroles par Whisper | ≈ 1 Go (PyTorch, rien si les stems sont installés) + 1,3 Go par langue (français, anglais) + 1,6 Go (Whisper) | plusieurs minutes (≈ 5 Go en tout, selon la connexion) | 1 à 3 min (mot par mot), 3 à 6 min environ (Whisper) | Apache-2.0 (wav2vec2), MIT (Whisper) |

**Pour installer** : ReaCue d'abord (étape 4), puis double-clic sur l'installateur dans le dossier `ReaCue`
(Mac : `.command` ; Windows : `.bat`), langue `fr`, puis suis la fenêtre. Sur Mac, la première fois, même
manipulation qu'à l'étape 4 si macOS bloque le fichier (clic droit → **Ouvrir**). Chaque installateur termine
par un court essai (par ex. `CHORDS_OK`, `WORDS_OK`, `STRUCTURE_OK`) ; s'il échoue, il dit pourquoi, et
**le relancer reprend là où il s'est arrêté**. REAPER peut rester ouvert : le composant sert dès la
préparation suivante (*Re-préparer* ou *Mettre à jour les téléphones* pour un morceau déjà prêt).

**Repli automatique, toujours.** Si un composant n'est pas installé, est désactivé par son réglage, échoue
ou dépasse son délai, ReaCue utilise sa propre méthode et le dit dans le *Résumé* : la préparation n'est
jamais bloquée.

**Licences.** Les modèles ne sont pas dans le dépôt : chaque installateur les télécharge chez leurs auteurs,
à une version figée. Deux composants sont réservés à un **usage non commercial** (analyse de structure,
batterie) : leur installateur affiche le résumé des licences et n'installe rien tant que tu n'as pas tapé
exactement **`J'accepte`** (accord mémorisé, pas redemandé aux mises à jour). Détails :
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) (ce n'est pas un avis juridique).

### 20.1 Séparation de stems (Demucs)

- **Apporte** : un seul MP3/WAV devient six stems (Chant, Batterie, Basse, Guitare, Piano, Autres), ce qui
  donne la vue batterie, les entrées par instrument, de meilleurs accords et le stem voix nécessaire aux
  paroles. Utilisation : [étape 9](#9-séparer-un-mp3-en-stems).
- **Installe** : `.venv-demucs` ; modèles Demucs dans le cache de PyTorch (`~/.cache/torch/hub/checkpoints`).
  L'installateur mesure la vitesse de ton ordinateur.
- **Réglage** : `stems_model` = `"htdemucs_6s"` (6 stems, par défaut) ou `"htdemucs"` (4 stems ; guitare et
  claviers restent dans « autres »). Onglet *Réglages* → *Séparation de stems*.
- **Sans lui** : prépare le morceau directement depuis le MP3 (moins de détails), ou fournis tes stems.

### 20.2 Analyse de structure (SongFormer)

- **Apporte** : des frontières et des noms de sections plus justes. ReaCue garde sa grille (tempo, mesures,
  décompte) : SongFormer dit seulement où sont les sections et ce qu'elles sont, chaque frontière est calée
  sur la mesure la plus proche ; les cases orange de l'onglet Morceau signalent les doutes
  ([étape 11](#11-vérifier-la-structure)).
- **Installe** : `.venv-structure` et `structure/` (SongFormer, MuQ, MusicFM). Les modèles déjà présents sur
  l'ordinateur (cache Hugging Face, autre copie de SongFormer) sont réutilisés au lieu d'être retéléchargés.
- **Mémoire** : 8 Go de RAM conseillés ; avec 15 Go ou plus, le modèle analyse le morceau par fenêtres de
  420 s (plus précis), sinon de 120 s.
- **Réglage** : onglet *Réglages* → *Détection de structure* : **auto (SongFormer)** ou **ReaCue seul**
  (`structure_engine`). Résultat mémorisé par morceau (`.reacue/` à côté de l'audio).
- **Repli** : non installé ou « ReaCue seul » → détection de ReaCue (pastille **Structure : ReaCue**) ; erreur
  ou plus de 30 min → « Analyse SongFormer impossible : … → structure ReaCue utilisée ».
- Installation sans question (accord de licence) : variable `REACUE_STRUCTURE_ACCEPT=yes`.

### 20.3 Accords par modèle entraîné

- **Apporte** : des accords plus justes pour le prompteur et la grille PDF (majeur / mineur, 7e, maj7, m7,
  sus, dim, aug, renversements comme `D/F#`). Modèle de Jiang et al. (ISMIR 2019, Music X Lab), **code et
  poids sous licence MIT**.
- **Comment** : il écoute les stems **sans la voix ni la batterie** (sinon le fichier unique), suit les temps
  de la grille de ReaCue (au plus deux accords par mesure, `N.C.` quand rien ne joue), écrit dièses / bémols
  selon la tonalité ; les 9e, 11e et 13e sont affichées comme la 7e correspondante (`G9` → `G7`).
- **Installe** : `.venv-chords` et `chords/model` (≈ 60 Mo, version figée depuis GitHub).
- **Réglage** : `chords_engine` = `"auto"` (le modèle s'il est installé, par défaut) ou `"reacue"`.
- **Repli** : non installé, `"reacue"`, erreur ou plus de 10 min → détection de ReaCue (« Modèle d'accords
  indisponible : … ») ; après un échec, pas de nouvel essai sur le même audio pendant 1 h. Le résultat est
  mémorisé dans le dossier `.reacue` du morceau (un changement de grille ne relance que le décodage).
- **Comparer** sur tes morceaux : `.venv/bin/python tools/compare_chords.py <dossier du morceau ou fichier
  audio>` (Windows : `.venv\Scripts\python tools\compare_chords.py …`), qui affiche les deux grilles mesure
  par mesure et leur taux d'accord.

### 20.4 Batterie par modèle entraîné (ADTOF)

- **Apporte** : une vue **Batterie** du prompteur bien plus fiable sur la caisse claire et les cymbales.
  ADTOF (M. Zehren et al.) est entraîné sur 359 heures de musique réelle ; ReaCue précise ensuite tom aigu /
  médium / basse, charley fermé / **ouvert** (ligne **Charley ouv.**, `HO`), crash ou ride selon la section,
  et cale chaque coup sur sa grille en **double-croches**, ou en **triolets** pour un morceau shuffle (choisi
  par morceau). Mêmes patterns, fills et crashs qu'avant, en plus juste.
- **Il faut** un stem batterie (stems fournis, ou séparation de stems).
- **Licence** : poids d'ADTOF sous **CC BY-NC-SA 4.0** (non commercial) ; le portage PyTorch utilisé
  (ADTOF-pytorch) n'indique pas de licence. L'installateur demande de taper **`J'accepte`**
  (`I accept` en anglais) ; sans cela rien n'est téléchargé. Installation sans question :
  `REACUE_DRUMS_ACCEPT=yes`.
- **Installe** : `.venv-drums` et `drums/` (code et poids, 16 Mo, version figée).
- **Réglage** : `drums_engine` = `"auto"` (ADTOF s'il est installé, par défaut) ou `"reacue"` (règles de
  ReaCue).
- **Repli** : non installé, `"reacue"`, erreur ou plus de 15 min → règles de ReaCue (« Transcription de
  batterie par modèle (ADTOF) impossible : … → méthode ReaCue utilisée »). Résultat mémorisé à côté du stem,
  dans `.reacue/`.
- **Comparer** : `.venv/bin/python tools/compare_drums.py <stem batterie>`.

### 20.5 Paroles mot par mot et paroles automatiques

Un seul installateur, **`Install ReaCue Words`**, installe les deux (environnement `.venv-words`, modèles dans
`words/`). Le relancer sur une installation existante n'ajoute que ce qui manque.

**Paroles mot par mot** (wav2vec2 XLSR-53 affiné en français et en anglais par J. Grosman, Apache-2.0) :

- **Apporte** : chaque mot de **tes** paroles placé à son vrai moment sur le stem voix, à l'intérieur des
  lignes déjà calées (le calage par ligne et `paroles_calage.json` restent l'ancrage). Prompteur Chant : mot
  en cours surligné, mots chantés estompés ; grille PDF : chaque mot dans sa mesure.
- **Langue** : déduite du texte des paroles ; `words_language` = `"fr"` ou `"en"` pour la forcer. Une seule
  langue de modèle à l'installation : variable `REACUE_WORDS_LANGS=fr` (ou `en`).
- **Réglage** : `words_engine` = `"auto"` (par défaut) ou `"off"` (lignes seulement).
- **Repli** : erreur ou plus de 15 min → paroles calées par ligne (« Calage mot par mot impossible : … ») ;
  une ligne mal reconnue garde son calage par ligne.
- **Comparer** : `.venv/bin/python tools/compare_words.py` (dernier morceau préparé) montre les positions
  avant / après sans jamais afficher le texte.

**Paroles automatiques** (Whisper `large-v3-turbo` d'OpenAI, code et poids MIT, ≈ 1,6 Go dans
`words/whisper/`) :

- **Apporte** : sans fichier de paroles, un brouillon **`paroles (auto).txt`** dans le dossier du morceau,
  transcrit depuis le stem voix, puis calé comme un fichier normal (par ligne, puis mot par mot). Règles et
  pastille orange : [étape 12](#12-ajouter-les-paroles).
- **Contre les inventions** : seules les zones où la voix chante sont transcrites ; les répétitions en boucle
  et les sous-titres typiques sont retirés ; une ligne par phrase chantée, une ligne vide entre deux blocs.
- **Réglage** : `lyrics_auto` = `"auto"` (par défaut) ou `"off"` ; langue détectée, ou forcée par
  `words_language`. Installation sans Whisper : variable `REACUE_WHISPER=0`.
- **Repli** : erreur, aucun chant reconnu ou plus de 20 min → pas de paroles, comme avant ; l'échec est
  mémorisé pour ce morceau (pas de nouvel essai à chaque publication).
- **Essayer à la main** : `.venv/bin/python tools/transcribe_lyrics.py` (dernier morceau préparé) affiche
  seulement des statistiques, jamais le texte ; `--write` écrit le brouillon s'il n'existe pas.

### 20.6 Retirer un composant

- **Le mettre de côté sans rien supprimer** : son réglage (`structure_engine` / `chords_engine` /
  `drums_engine` = `"reacue"`, `words_engine` / `lyrics_auto` = `"off"`), puis *Re-préparer*.
- **Le supprimer** : supprime ses dossiers dans le dossier `ReaCue` (`.venv-demucs` ; `.venv-structure` et
  `structure` ; `.venv-chords` et `chords` ; `.venv-drums` et `drums` ; `.venv-words` et `words`). ReaCue
  reprend tout seul sa propre méthode. Les modèles Demucs restent dans le cache de PyTorch
  (`~/.cache/torch/hub/checkpoints`, quelques centaines de Mo) : supprime-les aussi si tu veux.
- **Tout désinstaller** : double-clic sur `Uninstall ReaCue.command` / `.bat`, REAPER fermé (scripts, actions,
  démarrage du pont, entrée Claude Desktop). Le script lancé avec `--purge` supprime aussi tes réglages,
  `.venv-demucs`, `.venv-structure` et `structure`. Supprime ensuite le dossier `ReaCue` : tous les
  composants partent avec lui. Tes morceaux, stems, paroles et grilles PDF restent à côté de tes projets.

---

## 21. Annexe : tous les réglages

Fichier **`reacue_settings.json`**, dans le dossier `ReaCueMCP` des ressources de REAPER (menu *Options → Show
REAPER resource path in explorer/finder*). Les onglets **Réglages** et **Lumière** l'écrivent pour toi ; tu peux
aussi l'éditer (TextEdit en texte brut, Bloc-notes), en respectant la syntaxe JSON. Une clé absente prend sa
valeur par défaut ; une clé inconnue est ignorée. Les changements s'appliquent à la prochaine préparation
(*Re-préparer*, *Reconstruire le concert*).

| Clé | Défaut | Rôle | Où la régler |
|---|---|---|---|
| `performance_profile` | `"standard"` | `"standard"` ou `"fast"` : compromis calcul/qualité explicite | Réglages avancés |
| `cpu_threads` | `0` | `0` = auto ; sinon threads PyTorch, bornés au nombre de processeurs logiques | Réglages avancés / étalonnage Mac |
| `language` | `"fr"` | `"fr"` ou `"en"` : noms des régions, annonces, prompteur, messages | Réglages |
| `count_in_bars` | `2` | mesures de click avant la mesure 1 | Réglages |
| `cue_lead_bars` | `2` | annonce N mesures avant la section (2 = avant-dernière mesure) | Réglages avancés |
| `voice_cues` | `true` | annonces vocales des sections (« Refrain ») | Réglages |
| `voice_count_in` | `true` | « one two three four » sur la dernière mesure du décompte | Réglages |
| `voice_count_each` | `true` | « one two three four » sur la dernière mesure de chaque section | fichier |
| `count_lang` | `"en"` | langue du décompte : `"en"` (one two…) ou `"fr"` (un deux…) | Réglages avancés |
| `announce_voice` | `null` | voix du système pour les annonces ; `null` = automatique | Réglages |
| `count_voice` | `null` | voix du décompte ; `null` = automatique | Réglages avancés |
| `count_rate` | `240` | débit du décompte (mots par minute) | Réglages avancés |
| `voice_volume` | `0.8` | volume de la piste VOIX | Réglages avancés |
| `click_volume` | `0.5` | volume de la piste CLICK | Réglages avancés |
| `click_to_master` | `true` | `false` = click et voix seulement sur `click_hw_output` (in-ears), pas en façade | Réglages |
| `click_hw_output` | `null` | sortie physique du click et de la voix : `0` = 1/2, `2` = 3/4… ; `null` = aucune | Réglages |
| `tempo_mode` | `"auto"` | `"auto"`, `"constant"` (tempo fixe) ou `"beatmap"` (un tempo par mesure) | Réglages avancés |
| `stems_model` | `"htdemucs_6s"` | séparation : `"htdemucs_6s"` (6 stems) ou `"htdemucs"` (4 stems) | Réglages avancés |
| `structure_engine` | `"auto"` | sections : `"auto"` (SongFormer s'il est installé) ou `"reacue"` | Réglages |
| `chords_engine` | `"auto"` | accords : `"auto"` (modèle s'il est installé) ou `"reacue"` | fichier |
| `drums_engine` | `"auto"` | batterie : `"auto"` (ADTOF s'il est installé) ou `"reacue"` | fichier |
| `words_engine` | `"auto"` | paroles : `"auto"` (mot par mot s'il est installé) ou `"off"` (lignes seulement) | fichier |
| `words_language` | `"auto"` | langue chantée (mot par mot, Whisper) : `"auto"`, `"fr"` ou `"en"` | fichier |
| `lyrics_auto` | `"auto"` | sans fichier de paroles : `"auto"` (brouillon Whisper s'il est installé) ou `"off"` | fichier |
| `projects_dir` | `null` | dossier des projets des morceaux ; `null` = `<Documents>/REAPER Media` | Réglages avancés |
| `concert_dir` | `null` | dossier des concerts ; `null` = `<dossier des projets>/Concerts` | Réglages avancés |
| `gma3_export` | `true` | écrire les fichiers grandMA3 à chaque préparation / construction de concert | Lumière |
| `gma3_fps` | `25` | images par seconde du timecode (24, 25, 29.97, 30) | Lumière |
| `gma3_tc_start` | `"00:00:00:00"` | timecode du début du projet (ex. `"01:00:00:00"`) | Lumière |
| `gma3_song_gap` | `null` | concert : blanc minimum entre deux morceaux (s) ; `null` = celui de la setlist (4 s) | Lumière |
| `gma3_song_slot` | `0` | concert : chaque morceau démarre au prochain multiple de ce temps (s, ex. `600`) ; `0` = non | Lumière |
| `gma3_ltc_output` | `null` | piste `TIMECODE LTC` : sortie audio (`7`, ou `"7/8"` pour une paire) ; `null` = pas de piste | Lumière |
| `gma3_mtc_output` | `null` | piste `TIMECODE MTC` : nom du périphérique MIDI (`"IAC Driver Bus 1"`…) ; `null` = pas de piste | Lumière |
| `gma3_tc_slot` | `1` | TC Slot grandMA3 (1 à 8) réglé par le plugin ReaCue | Lumière |

Le **code PIN de la Régie** n'est pas dans ce fichier : il est gardé par REAPER et se change avec le bouton
**PIN** de l'onglet Scène (ou dans *Réglages avancés*).
