# Aide & communauté BandStudio

[Rejoindre Discord](https://discord.gg/5UnQPdMUpR) · [Guide](docs/BANDSTUDIO.md) · [GitHub Issues](https://github.com/herve8940/BandStudio/issues/new/choose)

Le serveur **BandStudio — Communauté** est distinct du serveur BandPilot. Français et anglais sont bienvenus.

| Besoin | Salon |
|---|---|
| Découvrir l’application | #accueil-welcome, #démarrer-start-here |
| Installation, stems, tempo, paroles, accords, REAPER | #entraide-help |
| Bug reproductible et diagnostic | #rapports-de-bugs |
| Proposer une amélioration | #idées-suggestions |
| Suivre les versions | #annonces-news |

Dans l’application, **Aide & Discord** est accessible depuis la navigation et les Réglages, même sans morceau ouvert. Décris le problème, les étapes et le résultat attendu. Le diagnostic compact est facultatif. **Copier le rapport et ouvrir Discord** copie exactement l’aperçu et ouvre le salon des bugs. Colle le texte et envoie-le dans Discord. Rejoins d’abord le serveur si c’est ta première visite.

Le message reste local jusqu’à ton partage. Il est limité à 2 000 caractères. Le filtre masque certains secrets, adresses e-mail et chemins reconnaissables, et neutralise les mentions ; relis toujours ce que tu saisis. Le diagnostic compact exclut les messages d’erreur libres, les noms de morceaux, les chemins, les paroles et les fichiers audio. Le diagnostic complet peut être exporté, relu, puis joint manuellement. Aucun webhook, jeton Discord ou compte utilisateur n’est embarqué dans l’application.

Si la copie échoue, le texte est sélectionné pour une copie manuelle. Si Discord ne s’ouvre pas, utilise l’invitation ci-dessus. Les bugs reproductibles peuvent aussi être suivis dans GitHub Issues.

**English:** join the BandStudio server, open **Aide & Discord** in the app, describe the issue and optionally include compact diagnostics. Review the preview, copy it and paste it into #rapports-de-bugs. You choose when to send it. No audio or project is included. For detailed logs, export and review the diagnostic file before attaching it yourself.

## Maintenir les liens

`config/community.json` contient l’invitation permanente et les identifiants du serveur et des salons. Après un changement, exécuter `python3 tools/sync_community.py`, mettre à jour les liens publics puis `python3 tools/sync_community.py --check`. Vérifier dans Discord que l’invitation arrive sur l’accueil, n’expire jamais et autorise un nombre illimité d’utilisations. Un renommage de salon conserve son identifiant ; sa recréation demande une mise à jour.
