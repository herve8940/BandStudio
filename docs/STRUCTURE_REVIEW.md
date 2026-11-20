# Compléter le parcours dans Pistes & structure

Cette aide est facultative. La navigation, « Tout préparer », l’éditeur musical,
les validations individuelles et « Valider & envoyer » restent disponibles.
L’import ne lance pas ce nouveau parcours sans action du musicien.

1. Dans **Pistes & structure**, choisir **Vérifier et compléter**. Le logiciel
   cherche d’abord une préparation mémorisée du même enregistrement. Les pistes
   séparées manquantes suivent la préparation habituelle. Sans mémoire compatible,
   les autres analyses manquantes puis la comparaison musicale sont effectuées.
2. Lire le récapitulatif. **Voir les changements** et **Écouter les passages**
   sont facultatifs. Une seule action lance la file des changements et des accords
   incertains, même si aucun nom de section ne change. Sa durée est affichée.
   L’écoute ne marque aucun repère comme validé.
3. **Valider et exporter vers REAPER** applique l’ensemble, régénère les guides
   choisis et crée un nouvel export portable. **Garder le parcours actuel**
   écarte la proposition. L’historique habituel permet d’annuler les modifications
   appliquées ; un export REAPER déjà créé reste un fichier indépendant.

Les notes et réglages en cours d’édition doivent être enregistrés avant cette
action. Une modification du projet invalide la proposition. Les empreintes des
médias, la version du projet, l’identité et la référence d’accords sont vérifiées
de nouveau avant l’application. Une panne pendant la préparation ou l’export ne
remplace pas le projet courant ; les analyses préalables déjà terminées sont
conservées comme dans « Tout préparer ».

## Références et calage

Le lecteur minuté utilise la liste **Song map** publique de DRUMY. Les en-têtes
des cinq fournisseurs de grilles et les exemples de passages Hooktheory sont
également comparés. Une liste sans horaires ne devient jamais une chronologie.
Le titre et l’artiste doivent correspondre ; chaque lecteur limite ses domaines.
La référence factuelle est mise en cache dans le projet pour une utilisation
hors connexion. Une référence manquante, ambiguë ou d’une durée incompatible
donne un avertissement et conserve la structure actuelle. La couverture dépend
du catalogue : ce lecteur ne prétend pas reconnaître toutes les œuvres.

Deux repères confirmés peuvent établir leur propre intervalle. En leur absence,
il faut au moins trois repères concordants couvrant 55 % de la référence, proches
des débuts de mesure locaux. Le recalage interpole entre ces repères, sans
extrapoler ni reconstruire une grille uniforme. Il utilise les mesures déjà
détectées ou les réglages de mesure fixe choisis par le musicien. Les limites protégées ne sont pas déplacées ou supprimées. Un début automatique
peut être proposé légèrement plus tard si une rupture conjointe d’harmonie et
de basse confirme la mesure suivante ; cette modification apparaît dans la proposition. Les régions manuelles,
verrouillées ou explicitement vérifiées sont préservées intégralement.

La proposition peut préciser un nom générique et subdiviser une région pour
retrouver une entrée absente. Un décalage de refrain peut être une anticipation
vocale : il est signalé et conservé. Les positions restent des propositions,
sans pourcentage de confiance présenté comme une garantie.

Les lecteurs d’accords conservent maintenant les suites écrites par section,
y compris les doublons, les occurrences et les répétitions explicites simples.
Le nouveau parcours utilise cet ordre lorsque l’audio le confirme. Sinon le
calage habituel reste provisoire et l’incertitude est signalée. Les durées et
répétitions absentes de la source ne sont pas inventées. Une recherche vide
n’efface plus les accords existants, sur macOS comme sur Windows.

Le nouvel export ajoute une piste muette **Accords**, avec des éléments nommés
aux positions calculées, en plus des métadonnées complètes de retour vers
BandStudio. Les accords peu assurés portent la mention « à vérifier ».

## Hysteria comme référence de développement

Les fixtures de test reprennent les repères locaux et la structure factuelle
publiée pour [Hysteria — Muse](https://drumy.app/drums/hysteria-muse).
Le moteur retrouve cinq repères concordants, propose le couplet à 95,438594 s
et le solo à 146,964490 s et précise quatre noms, dont la continuation du solo. Il conserve les
départs de refrains et toutes les limites préexistantes. Aucun titre, artiste
ou horaire de Hysteria n’est codé en dur dans le moteur.

Ce cas est un test de régression du parcours apprécié par le musicien, pas une
mesure indépendante de précision sur tous les styles. Les tests couvrent aussi
les références incompatibles, les protections, le 3/4 et les mesures variables,
les propositions périmées, les pannes, la conservation des accords et l’export.

## Apprentissage local

La bibliothèque conserve une mémoire locale dans `.bandstudio-memory`. Le rappel
vérifie une empreinte complète des échantillons audio décodés, de leur fréquence
et de leurs canaux. Un nom ou des métadonnées différents n’invalident pas le même
audio ; une autre prise, un montage ou un encodage modifiant les échantillons
n’est pas assimilé à une référence validée. Les anciens projets comportant des
repères confirmés sont découverts dans la bibliothèque sans clic d’enregistrement.

La mémoire distingue les corrections individuelles et les préparations globalement
acceptées. Elle ne copie pas les pistes ni le mix d’un autre projet. Une grille
protégée ou une décision manuelle contradictoire reste prioritaire. Plusieurs
mémoires incompatibles ne sont pas fusionnées. Le rappel est une proposition ;
il utilise les mêmes validation, historique et export que le parcours existant.

Les répétitions sont comparées sur la grille locale, avec des contrôles séparés
de l’harmonie, de la basse, du timbre, de la batterie et de la présence du chant.
Les groupes exigent que toutes leurs paires concordent ; une chaîne de ressemblances
ne suffit pas. Une section confirmée peut préciser un nom générique comparable,
sans déplacer ses limites. Une phrase d’accords manuels complète et sans trous
peut être adaptée à une occurrence comparable ; cette cible reste non validée.
Les variantes et les données insuffisantes font s’abstenir le transfert.

Les phrases écrites identiques peuvent partager leur évidence audio entre
occurrences concordantes. Les fins différentes restent séparées et une proposition
qui augmente les cellules incertaines d’une occurrence est rejetée. Les scores de
ressemblance ne sont pas des probabilités de justesse. La file d’écoute couvre
tous les accords signalés incertains, sans en masquer sous un compteur de groupes.

Les décisions globales sont journalisées dans `Learning/structure-reviews`,
avec la référence et les modifications proposées. Accepter un export ou garder
le parcours existant ne constitue pas une annotation musicale vérifiée. Les
nouvelles sections sont protégées après acceptation mais restent `reviewed:false`.
Les validations individuelles et corrections explicites continuent à alimenter
le journal existant. Aucun nouvel entraînement, changement de poids ou envoi
d’audio ne se déclenche à la validation.

`tools/compare_structure_memory.py` compare l’ancienne et la nouvelle proposition
sur des copies privées avec les mêmes références Internet enregistrées. Il mesure
séparément la sortie musicale, l’incertitude, le rappel exact et un scénario de
nom masqué après validation simulée. Sans transcription indépendante, il ne
présente aucun de ces indicateurs comme un taux d’erreur musicale. Les temps de
comparaison et de rappel excluent les analyses préalables et l’export.


## Fiabilité dès le premier import

La piste de basse séparée apporte maintenant une information indépendante du
chant et des guitares. Ses pics spectraux sont décomposés en notes par moindres
carrés non négatifs, avec un dictionnaire d’harmoniques généré à partir des
fréquences musicales. Cette étape limite la confusion entre une fondamentale et
ses harmoniques. Une piste muette ne fournit pas de preuve. Sans basse séparée,
le lecteur garde son chemin compatible avec un seul fichier audio.

La basse partage l’accordage global estimé sur l’harmonie, y compris pour les
enregistrements éloignés du diapason standard. Elle n’est pas réaccordée par
extrait. Une note de basse tenue ne force pas les changements de guitare à
devenir un seul accord ; une quinte ou une tierce compatible avec une harmonie
nette ne suffit pas non plus à la remplacer par un nouvel accord majeur.
Une piste de basse absente ou illisible laisse fonctionner l’analyse harmonique.

Le décodage conserve le vocabulaire publié et pénalise davantage les changements
isolés. Les changements rapides restent possibles lorsque le signal les appuie.
Une grille sans en-têtes conserve aussi sa suite complète d’accords ; les
représentations en tablature ne sont pas prises pour une deuxième exécution.
L’alignement de cette suite n’est accepté que dans les sections dont le signal
reste concordant. Une version abrégée ne force donc pas tous ses accords sur le
morceau. Les anciens caches de sources sont actualisés au catalogue 6.

Les scores du décodage et l’ordre écrit ne servent pas de confiance affichée.
La confiance compare les familles harmoniques, puis vérifie séparément la basse
d’un renversement. Une note de basse claire, stable pendant au moins 0,8 pulsation
et hors pédale peut apporter une contradiction bornée (0,12 au maximum) contre
une harmonie qui ne contient pas cette note. Une note passagère ou incertaine ne
le peut pas. Ces indices audio restent heuristiques : un accord choisi grâce à
la basse peut encore être signalé à vérifier, et le score n’est pas une probabilité.

Les renversements d’une même harmonie (par exemple D et D/F#) ne sont plus traités
comme deux accords concurrents dans le calcul de confiance. La note de basse
observée décide de leur notation ; une basse étrangère aux renversements publiés
fait préférer l’accord sans renversement lorsqu’il existe dans la source. Un
renversement sans preuve de sa note de basse reste incertain. Les suspensions,
couleurs et fondamentales différentes restent distinctes, même lorsque deux
accords partagent toutes leurs classes de hauteur (par exemple C6 et Am7).

Une pédale est reconnue sur toute sa durée, y compris ses extrémités proches d’un
changement de basse. Elle exige environ six pulsations de hauteur stable. Une
cellule intermédiaire incertaine peut relier deux notes identiques ; un silence
ou une autre note claire interrompt cette continuité.

Les variantes explicitement écrites pour chaque occurrence peuvent préciser le
vocabulaire, sans exclure une fondamentale entière omise par une grille abrégée.
Aux extrémités d’une section, le poids de ce vocabulaire diminue pendant deux
pulsations pour les fondamentales absentes. L’ordre écrit ne peut pas avancer
ou prolonger sa première/dernière harmonie contre un autre accord soutenu à la
fois par l’audio harmonique et une note grave claire. Cela ajuste les accords ;
les limites de section ne changent pas.

Les références de structure à la seconde près peuvent utiliser un consensus de
quatre repères intérieurs ou plus, sans exiger une validation manuelle. Une
insertion dans une section nommée exige également un changement audio dans au
moins deux dimensions. La fin publiée peut préciser un départ final déjà présent,
mais ne crée pas de limite extrapolée. Les versions divergentes restent refusées.

Les repères automatiques légèrement anticipés peuvent rejoindre une mesure plus
tardive quand harmonie et basse présentent une rupture conjointe nettement plus
forte. Le mouvement est borné à 1,35 pulsation et 1,3 seconde. Un simple fill ou
une entrée de chant ne suffit pas ; les repères manuels, verrouillés ou vérifiés
et leurs sections voisines sont conservés.

Les principes s’appuient sur [NNLS Chroma, Mauch et Dixon](https://github.com/c4dm/nnls-chroma),
l’[alignement et la fusion de références symboliques étudiés dans DECIBEL](https://arxiv.org/abs/2002.09748)
et les méthodes de [segmentation musicale par répétition et contraste](https://librosa.org/doc/main/auto_tutorials/03-advanced/plot_segmentation.html).
L’implémentation légère ne reproduit pas les systèmes complets de ces travaux et
n’en reprend pas les résultats de précision.

`tools/compare_first_import.py` exécute les deux révisions sur des copies privées,
avec pages Internet figées et sorties brutes des mêmes modèles préalables. Les
accords, corrections manuelles, validations et mémoires de morceaux sont retirés.
Les repères précédemment vérifiés ne servent qu’à une comparaison extérieure.
Le nombre d’accords, leur couverture et leur incertitude ne constituent pas un
taux de justesse. Les tests sur signaux synthétiques possèdent, eux, des notes
exactement connues et couvrent des transpositions, renversements et changements
rapides. Aucun titre ou horaire des trois morceaux n’entre dans le moteur.
