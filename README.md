# BandStudio

**Prépare ta partie avant la répétition.** Importe un enregistrement, écoute la basse seule pour apprendre sa ligne, puis coupe-la pour jouer avec le reste du groupe. BandStudio rassemble les pistes séparées, le métronome, les paroles et la grille d’accords dans un éditeur local pour Mac et Windows.

**BandStudio est disponible en français et en anglais sur Mac et Windows.**

[Site officiel](https://herve8940.github.io/BandStudio/) · [Télécharger pour Windows](https://github.com/herve8940/BandStudio/releases/latest/download/BandStudio-1.1.0-Windows-x64.zip) · [Guide macOS](docs/BANDSTUDIO.md#macos) · [English](README.en.md)

![L’éditeur de BandStudio avec un projet de démonstration, les pistes et les passages à réécouter](site/assets/editor-review.jpg)

## Installer BandStudio

| Ton ordinateur | Pour démarrer |
| --- | --- |
| **Windows 11 x64** | Extrais le ZIP entier dans un dossier accessible en écriture, puis lance **BandStudio.exe**. Python et FFmpeg sont inclus. WebView2 et .NET Framework 4.8 sont requis. Les moteurs facultatifs s’installent dans **Réglages → Analyses locales**. |
| **Mac Intel ou Apple Silicon déjà équipé** | Dans **Réglages**, vérifie les mises à jour. Une fois le téléchargement terminé, quitte BandStudio et rouvre-le. |
| **Première installation sur Mac** | La compilation depuis les sources nécessite un moteur ReaCue et ses environnements Python déjà préparés. Aucun installateur complet pour Mac neuf n’est distribué actuellement. [Prérequis et commandes](docs/BANDSTUDIO.md#macos) |

La version **1.1.0 du 24 novembre 2026** ouvre directement l’éditeur et optimise le calcul des formes d’onde. Les archives de mise à jour préservent les projets et les réglages. [Notes de version](docs/RELEASE_2026-11-24.md) · [Historique](CHANGELOG.md)

## Préparer ton premier morceau

Pour choisir la langue de l’application, ouvre **Réglages → Langue de l’interface**, choisis **Français** ou **English**, puis quitte et rouvre BandStudio.

1. Dans **Mes morceaux**, importe ton fichier audio. Laisse **Préparer automatiquement après l’import** activé pour utiliser les moteurs installés. Pour plusieurs fichiers, ouvre **Préparer une série** et démarre la file.
2. Dans **Éditeur du morceau**, isole une piste, boucle une section ou ralentis la lecture. Réécoute les passages signalés avant de corriger un repère, une parole ou un accord.
3. Ouvre **Fiche morceau** pour exporter un PDF avec les accords et les paroles par mesure. Dans **Projet REAPER**, exporte les pistes et leurs médias pour poursuivre le travail dans REAPER.

[Guide illustré de l’import à REAPER](https://herve8940.github.io/BandStudio/tutoriel.html) · [Guide de la fiche PDF](https://herve8940.github.io/BandStudio/fiche-morceau.html) · [Manuel complet](docs/BANDSTUDIO.md)

## Pendant la répétition

- **Écoute**. Règle le volume, le panoramique, la vitesse et la transposition. Isole ta partie ou joue avec les autres pistes. Les instruments disponibles dépendent du modèle installé.
- **Repères**. Ajuste le tempo, les sections, le métronome et le décompte. Compare les grilles d’accords, choisis ton capo et cale les paroles sur le chant.
- **Exports**. Récupère le mix, les pistes séparées, les paroles LRC/SRT, le MIDI de batterie, la fiche PDF ou le projet REAPER. Les pistes audio exportées individuellement gardent leur vitesse et leur hauteur d’origine.

Les calculs audio s’exécutent sur ton ordinateur. Les recherches de paroles, d’accords et de pochettes utilisent Internet. La qualité des propositions dépend de l’enregistrement et des moteurs installés. [Fonctions et limites](docs/BANDSTUDIO.md#traitement-du-morceau)

## Aide et contribution

Pour une question de musicien, rejoins le [Discord BandStudio](https://discord.gg/5UnQPdMUpR). Pour un problème reproductible, indique ton système et les étapes suivies. Dans **Aide & Discord**, tu peux relire un diagnostic avant de le partager. [Assistance](SUPPORT.md) · [Signaler un bug](https://github.com/herve8940/BandStudio/issues/new/choose)

Le code est sous [licence MIT](LICENSE). Les moteurs et modèles ont leurs propres licences, dont certaines limitent l’usage commercial. [Crédits et licences des composants](THIRD_PARTY_NOTICES.md) · [Contribuer et lancer les tests](CONTRIBUTING.md) · [Sécurité](SECURITY.md) · [Code de conduite](CODE_OF_CONDUCT.md)

Pour les balances et les retours de scène du groupe, voir [BandPilot](https://herve8940.github.io/BandPilot/). Les scripts REAPER historiques sont documentés dans le [manuel ReaCue](README_REACUE.md).
