# BandStudio

[English](#english) · [Français](#français)

## English

**Learn your part before rehearsal.** Import a recording, solo the bass to learn the line, then mute it and play along with the band. BandStudio brings separated tracks, a metronome, lyrics and chord charts together in a local editor for Mac and Windows.

**BandStudio is available in English and French on Mac and Windows.**

[Official website](https://herve8940.github.io/BandStudio/en.html) · [Download for Windows](https://github.com/herve8940/BandStudio/releases/latest/download/BandStudio-1.1.0-Windows-x64.zip) · [macOS setup guide in French](docs/BANDSTUDIO.md#macos)

![The BandStudio editor showing a demo project, instrument tracks and passages to review](site/assets/editor-review.jpg)

### Install BandStudio

| Your computer | Getting started |
| --- | --- |
| **Windows 11 x64** | Extract the entire ZIP to a writable folder, then open **BandStudio.exe**. Python and FFmpeg are included. WebView2 and .NET Framework 4.8 are required. Install optional engines in **Settings → Local analysis**. |
| **An existing Intel or Apple Silicon Mac installation** | Open **Settings** and check for updates. Quit BandStudio after the download finishes, then reopen it. |
| **First-time Mac setup** | Building from source requires an existing ReaCue engine and prepared Python environments. A standalone installer for a new Mac is not currently available. [Requirements and commands](docs/BANDSTUDIO.md#macos) |

**Version 1.1.0, 24 November 2026**, opens directly in the editor and optimizes track waveform calculation. Update packages preserve your projects and settings. [Release notes in English](docs/RELEASE_2026-11-24.md#english) · [Changelog](CHANGELOG.md)

### Prepare your first song

Choose **English** in **Settings → Interface language**, then quit and reopen BandStudio.

1. Import your audio file in **My songs**. Leave **Prepare automatically after import** selected to use the installed engines. For several files, open **Prepare a batch** and start the queue.
2. In **Song editor**, solo a track, loop a section or slow down playback. Listen to flagged passages before adjusting a marker, a lyric or a chord.
3. Open **Song sheet** to export a PDF with chords and lyrics by bar. In **REAPER project**, export the tracks and media to continue working in REAPER.

[Visual guide from import to REAPER](https://herve8940.github.io/BandStudio/tutorial.html) · [Song sheet and PDF guide](https://herve8940.github.io/BandStudio/song-sheet.html) · [Full walkthrough](docs/BANDSTUDIO_TUTORIAL_en.md)

### In rehearsal

- **Listen**. Adjust volume, pan, speed and pitch. Isolate your part or play with the other tracks. Available instruments depend on the installed model.
- **Follow the song**. Adjust tempo, section boundaries, metronome and count-in. Compare chord charts, choose a capo and align lyrics to the vocal.
- **Export**. Save a mix, individual tracks, LRC/SRT lyrics, drum MIDI, a PDF song sheet or a REAPER project. Individually exported audio tracks keep their original speed and pitch.

Audio processing runs on your computer. Lyrics, chord and artwork lookups use online services. Results depend on the recording and installed engines. [Technical guide and limitations in French](docs/BANDSTUDIO.md#traitement-du-morceau)

### Help and contributions

Ask rehearsal questions in the [BandStudio Discord](https://discord.gg/5UnQPdMUpR). To report a reproducible issue, include your operating system and the steps you followed. **Help & Discord** lets you review diagnostic information before you share it. [Support](SUPPORT.md) · [Report an issue](https://github.com/herve8940/BandStudio/issues/new/choose)

The source code uses the [MIT license](LICENSE). Dependencies and models have their own licenses, some with non-commercial terms. [Third-party notices](THIRD_PARTY_NOTICES.md) · [Contributing and running tests](CONTRIBUTING.md) · [Security](SECURITY.md) · [Code of conduct](CODE_OF_CONDUCT.md)

For soundchecks and stage monitoring, see [BandPilot](https://herve8940.github.io/BandPilot/). The original REAPER scripts are documented in the [ReaCue manual](README_REACUE.md).

---

## Français

**Prépare ta partie avant la répétition.** Importe un enregistrement, écoute la basse seule pour apprendre sa ligne, puis coupe-la pour jouer avec le reste du groupe. BandStudio rassemble les pistes séparées, le métronome, les paroles et la grille d’accords dans un éditeur local pour Mac et Windows.

**BandStudio est disponible en français et en anglais sur Mac et Windows.**

[Site officiel](https://herve8940.github.io/BandStudio/) · [Télécharger pour Windows](https://github.com/herve8940/BandStudio/releases/latest/download/BandStudio-1.1.0-Windows-x64.zip) · [Guide macOS](docs/BANDSTUDIO.md#macos)

![L’éditeur de BandStudio avec un projet de démonstration, les pistes et les passages à réécouter](site/assets/editor-review.jpg)

### Installer BandStudio

| Ton ordinateur | Pour démarrer |
| --- | --- |
| **Windows 11 x64** | Extrais le ZIP entier dans un dossier accessible en écriture, puis lance **BandStudio.exe**. Python et FFmpeg sont inclus. WebView2 et .NET Framework 4.8 sont requis. Les moteurs facultatifs s’installent dans **Réglages → Analyses locales**. |
| **Mac Intel ou Apple Silicon déjà équipé** | Dans **Réglages**, vérifie les mises à jour. Une fois le téléchargement terminé, quitte BandStudio et rouvre-le. |
| **Première installation sur Mac** | La compilation depuis les sources nécessite un moteur ReaCue et ses environnements Python déjà préparés. Aucun installateur complet pour Mac neuf n’est distribué actuellement. [Prérequis et commandes](docs/BANDSTUDIO.md#macos) |

La version **1.1.0 du 24 novembre 2026** ouvre directement l’éditeur et optimise le calcul des formes d’onde. Les archives de mise à jour préservent les projets et les réglages. [Notes de version](docs/RELEASE_2026-11-24.md) · [Historique](CHANGELOG.md)

### Préparer ton premier morceau

Pour choisir la langue de l’application, ouvre **Réglages → Langue de l’interface**, choisis **Français** ou **English**, puis quitte et rouvre BandStudio.

1. Dans **Mes morceaux**, importe ton fichier audio. Laisse **Préparer automatiquement après l’import** activé pour utiliser les moteurs installés. Pour plusieurs fichiers, ouvre **Préparer une série** et démarre la file.
2. Dans **Éditeur du morceau**, isole une piste, boucle une section ou ralentis la lecture. Réécoute les passages signalés avant de corriger un repère, une parole ou un accord.
3. Ouvre **Fiche morceau** pour exporter un PDF avec les accords et les paroles par mesure. Dans **Projet REAPER**, exporte les pistes et leurs médias pour poursuivre le travail dans REAPER.

[Guide illustré de l’import à REAPER](https://herve8940.github.io/BandStudio/tutoriel.html) · [Guide de la fiche PDF](https://herve8940.github.io/BandStudio/fiche-morceau.html) · [Manuel complet](docs/BANDSTUDIO.md)

### Pendant la répétition

- **Écoute**. Règle le volume, le panoramique, la vitesse et la transposition. Isole ta partie ou joue avec les autres pistes. Les instruments disponibles dépendent du modèle installé.
- **Repères**. Ajuste le tempo, les sections, le métronome et le décompte. Compare les grilles d’accords, choisis ton capo et cale les paroles sur le chant.
- **Exports**. Récupère le mix, les pistes séparées, les paroles LRC/SRT, le MIDI de batterie, la fiche PDF ou le projet REAPER. Les pistes audio exportées individuellement gardent leur vitesse et leur hauteur d’origine.

Les calculs audio s’exécutent sur ton ordinateur. Les recherches de paroles, d’accords et de pochettes utilisent Internet. La qualité des propositions dépend de l’enregistrement et des moteurs installés. [Fonctions et limites](docs/BANDSTUDIO.md#traitement-du-morceau)

### Aide et contribution

Pour une question de musicien, rejoins le [Discord BandStudio](https://discord.gg/5UnQPdMUpR). Pour un problème reproductible, indique ton système et les étapes suivies. Dans **Aide & Discord**, tu peux relire un diagnostic avant de le partager. [Assistance](SUPPORT.md) · [Signaler un bug](https://github.com/herve8940/BandStudio/issues/new/choose)

Le code est sous [licence MIT](LICENSE). Les moteurs et modèles ont leurs propres licences, dont certaines limitent l’usage commercial. [Crédits et licences des composants](THIRD_PARTY_NOTICES.md) · [Contribuer et lancer les tests](CONTRIBUTING.md) · [Sécurité](SECURITY.md) · [Code de conduite](CODE_OF_CONDUCT.md)

Pour les balances et les retours de scène du groupe, voir [BandPilot](https://herve8940.github.io/BandPilot/). Les scripts REAPER historiques sont documentés dans le [manuel ReaCue](README_REACUE.md).
