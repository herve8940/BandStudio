# Contribuer à BandStudio

Les améliorations musicales, corrections, traductions et retours d’usage sont bienvenus. Décris le problème et l’effet attendu dans une issue avant une modification importante.

- Pars de `main` dans une branche dédiée. Garde une modification cohérente par pull request.
- Conserve la compatibilité des projets existants et les corrections manuelles. Ne modifie jamais les médias sources.
- Partage seulement des exemples synthétiques ou dont tu possèdes les droits. Aucun morceau, modèle, cache, secret ou environnement personnel dans Git.
- Vérifie la compilation des deux hôtes si tu modifies le contrat JavaScript/Python/Swift. Les nouveaux modes d’écoute doivent produire le même mix dans l’aperçu et dans REAPER.
- Ajoute un test de régression pour un comportement corrigé. Le workflow de publication vérifie les paquets et les mises à jour.

Le [README](README.md) détaille les commandes de test. Le [guide](docs/BANDSTUDIO.md) explique le périmètre de l’application. Décris dans la PR ce qui change, les tests exécutés et les vérifications restant à faire sur matériel réel.
