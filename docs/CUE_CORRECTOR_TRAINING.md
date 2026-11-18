# Apprentissage du correcteur de transitions

Cette expérience apprend une correction des horodatages de sections proposés
par SongFormer. Elle ne réentraîne pas SongFormer ni BeatThis. Le correcteur
utilise le contexte des sections et 44 caractéristiques extraites du signal
audio (énergie, flux spectral et changements de timbre à plusieurs échelles).

Le modèle de recalage minimise une perte de Huber par rapport à l'intervalle
d'accord de deux annotations humaines. Une position à l'intérieur de cet
intervalle n'est pas pénalisée. Les candidats expérimentaux initiaux autorisent une seconde (la version distribuée
v2 se limite à 250 ms, voir ci-dessous) et ne
peut pas inverser deux transitions. Trois régularisations/modèles sont comparés,
dont un décalage constant appris servant de référence simple. Un classifieur
logistique expérimental permet également de comparer une suppression prudente
de fragments de moins de 12 secondes. Ses scores ne sont pas des probabilités
calibrées. Les noms de sections restent inchangés.

Les transitions ambiguës restent sans étiquette. Les négatifs du classifieur
proviennent uniquement de transitions éloignées des frontières des deux
annotations, dans une section continue où elles concordent. Les transitions
manquées restent mesurées mais leur insertion n'est pas apprise dans cette
version. Aucune référence de pulsation, mesure ou anticipation vocale n'est
disponible dans ce corpus.

## Déroulement automatique

`tools/launch_cue_corrector.py` lance `tools/train_cue_corrector.py` dans un
processus détaché, à priorité réduite, avec deux threads de calcul. Sur macOS,
`caffeinate` empêche la veille système sur secteur pendant ce travail (48 heures
maximum). L'écran peut s'éteindre. Le Mac doit rester branché, capot ouvert.

Le programme attend un état `complete`, le rapport complet et tous les fichiers
de prédiction et de scores. Un échec ou un arrêt de l'analyse interdit le
démarrage de l'apprentissage. Il vérifie ensuite les empreintes audio et les
prédictions, reconstruit les exemples, extrait les caractéristiques, entraîne
les modèles, les compare sur la validation et évalue le modèle sélectionné sur
le lot final réservé. Le verrou empêche deux entraînements concurrents dans le
même dossier. Créer un fichier `STOP` dans le dossier d'entraînement interrompt
le travail à la prochaine vérification. Les caractéristiques déjà calculées
peuvent être reprises avec le même protocole.

La durée annoncée par un en-tête MP3 peut différer légèrement de la durée
réellement décodée. Le contrôle conserve les empreintes audio et exige un
en-tête inchangé. Un écart MP3 inférieur à 1,5 seconde est accepté seulement si
la durée décodée reste compatible avec les deux fins d'annotation, selon la
borne déjà utilisée lors de la collecte. Cette vérification est journalisée ;
elle ne décale ni l'audio ni les annotations. Les fichiers tronqués au-delà de
cette borne restent refusés.

Les fichiers `status.json` et `run.log` distinguent explicitement l'attente,
l'extraction, l'entraînement, la validation, le test et la fin du travail.
Une fin d'analyse ne signifie donc plus qu'une intervention manuelle est
nécessaire pour lancer l'entraînement.

## Séparation et évaluation

Le protocole est scellé avant l'entraînement : code, bibliothèques, manifeste,
paramètres, critères d'acceptation et répartition déterministe 60/20/20. Les
artistes identiques, titres connus identiques et fichiers audio identiques sont
réunis avant cette répartition. Des reprises ou alias non reconnus restent
possibles. La normalisation des caractéristiques est apprise sur le lot
d'entraînement uniquement. La validation sélectionne un des six candidats au
maximum. Le modèle est sauvegardé avant de consulter les scores du test final.
Un résultat final ne doit pas servir à modifier les paramètres et réessayer sur
le même lot.

Les deux annotations sont évaluées séparément et conservées dans les rapports.
Le score global donne le même poids à chaque couple morceau/annotateur. Les
critères fixés exigent notamment un gain d'au moins un point de F1 à 0,5 seconde,
une diminution d'erreur temporelle d'au moins 20 ms, la préservation des scores à
3 secondes et des étiquettes, au plus 2 % de frontières auparavant correctes
dégradées, et aucune régression par morceau supérieure à 0,10 de F1. Ils doivent
passer à la fois sur la validation et sur le lot final réservé. Une transition
correcte supprimée compte comme une erreur, jamais comme un gain artificiel de
précision temporelle.

Le corpus SALAMI reste un corpus de développement : son éventuelle présence
dans le préentraînement de SongFormer n'est pas exclue et ses genres ne sont
pas uniformément documentés. Le lot final est inédit pour l'ajustement de ce
correcteur, pas un test externe indépendant de toute la chaîne.

## Livrables et installation

Le dossier d'expérience contient `protocol.json`, `split.json`, `dataset.json`,
`examples.json`, les caractéristiques réutilisables, `frozen-model.json`,
`report.json` et `cue-corrector-candidate.json`. Le rapport conserve les scores
avant/après, les régressions et les propositions corrigées pour revue.

L’entraînement initial n’installe aucun modèle dans BandStudio. Même si les
critères passent, le candidat conserve `approved: false` dans l'attente d'une
validation externe sur de nouvelles chansons. En cas d'échec, le rapport
indique `rejected_keep_current_engine`. Le module ne charge aucun poids
implicitement et refuse de transformer toute structure contenant une section
manuelle, verrouillée, validée ou sans provenance d'analyse.

## Candidat conservateur et nouveau lot réservé

La régression observée sur « Void » a motivé une règle générale d'abstention :
les propositions des trois modèles entraînés sont comparées avant toute
limitation. Un désaccord supérieur à 150 ms ou des déplacements de signes
opposés empêche la correction. Les déplacements acceptés sont limités à 250 ms
et les modifications inférieures à 20 ms sont ignorées. Aucun nom de morceau
ni horodatage d'annotation n'entre dans cette décision. Sur le cas connu, la
transition de 33,84 secondes reste exactement à sa position initiale.

`prepare_cue_release.py` choisit la tolérance sur l'ancienne validation. L'ancien
test, déjà consulté et utilisé pour diagnostiquer la régression, devient
explicitement un contrôle de développement. `run_cue_holdout.py` collecte 24
autres enregistrements : artistes, titres connus, identifiants et empreintes
audio sont distincts des 120 précédents. Les téléchargements défaillants sont
remplacés selon un ordre déterministe fixé avant les scores. L'éventuel
recouvrement avec le préentraînement de SongFormer demeure inconnu.

`validate_cue_release.py` applique le candidat figé sans réentraînement et utilise
exactement la transformation destinée au moteur. Il conserve les critères
initiaux, exige zéro transition auparavant correcte devenue erronée et calcule
un intervalle de confiance à 95 % du gain de F1 par rééchantillonnage des
morceaux/artistes. Les deux annotations d'un morceau restent ensemble. La borne
inférieure doit être positive. Aucune nouvelle sélection de modèle ne peut
utiliser ce résultat.

Si tous les critères passent, l'installation demandée est exécutée par
`install_cue_corrector.py`. Elle sauvegarde les fichiers du moteur, publie le
modèle approuvé en dernier, puis vérifie le worker installé sur une vraie
prédiction en cache, dans le Python du moteur. Un échec restaure les anciens
fichiers. Aucun projet utilisateur n'est réécrit. Le redémarrage de l'application
n'est pas nécessaire : les prochaines analyses lancent un nouveau worker.

L'activation se limite au contexte testé : fenêtre SongFormer de 60 secondes,
enregistrements de 120 à 600 secondes, sections contiguës issues de l'analyse,
aucune section manuelle ou validée dans le projet. Une autre configuration,
des poids ou du code modifiés, ou une approbation absente désactivent le
correcteur. Les caches gardent les segments bruts de SongFormer ; une nouvelle
analyse ne cumule jamais deux corrections. Les sections corrigées restent des
propositions à vérifier par l'utilisateur.


## Résultats du lot réservé et distribution

Version publiée : **cue-corrector-v2**, coefficients figés le 18 novembre 2026,
conditionnement portable du 19 novembre 2026. Les 120 premiers morceaux ont
servi au développement (72 entraînement, 24 validation, 24 ancien test). Après
la correction de la régression, 24 autres morceaux ont été évalués sans nouvel
ajustement des coefficients ou des seuils sur leurs scores.

| Mesure sur les 24 nouveaux morceaux | SongFormer dans BandStudio | Avec correcteur |
|---|---:|---:|
| F1 des frontières à ±0,5 seconde | 46,84 / 100 | 52,06 / 100 |
| F1 à ±3 secondes | 62,60 / 100 | 63,00 / 100 |
| Erreur moyenne par rapport à l’intervalle humain, 79 transitions appariées | 310 ms | 206 ms |
| Transitions auparavant correctes devenues erronées selon le critère fixé | — | 0 sur 46 |

150 frontières déplacées, aucune supprimée. Aucune perte par morceau supérieure
à 0,10 de F1. L’intervalle de confiance à 95 % du gain de F1 à 0,5 seconde est
**+2,67 à +8,24 points**, par 5 000 rééchantillonnages appariés. « Zéro devenue
erronée » ne signifie pas que chaque erreur individuelle a diminué. La mesure
d’erreur temporelle porte sur les 79 transitions appariées, pas sur toutes les
frontières ou sur les annonces vocales.

[Rapport agrégé et empreintes](evaluation/cue-corrector-v2.json). Ces résultats
ont été mesurés sur Mac Intel avec la fenêtre de 60 secondes. Les vérifications
Mac Intel, Apple Silicon et Windows de la publication contrôlent la compilation,
le conditionnement et le comportement logiciel ; elles ne remplacent pas une
nouvelle mesure audio sur chaque machine. Le recouvrement possible de SALAMI
avec le préentraînement de SongFormer reste inconnu. Ces chiffres ne promettent
pas le même gain sur chaque morceau ou chaque genre.

Les mises à jour contiennent les coefficients approuvés dans
`desktop/studio/cue_corrector_bundle.py`, sous forme de données littérales. Ce
format traverse aussi les anciens installateurs de mises à jour qui acceptent
les modules Python mais pas de nouveaux dossiers de données. Les paquets ne
contiennent ni enregistrement du corpus, ni annotation humaine complète, ni
projet utilisateur. Les modèles tiers gardent leur installation et leurs
conditions existantes.

Au premier usage compatible, le moteur vérifie les empreintes des poids
SongFormer/MusicFM/MuQ présents localement. Le cache des vérifications est propre
à cette installation et invalidé si ces fichiers changent. Le déplacement vers
un autre ordinateur déclenche une nouvelle vérification, sans réentraînement.
Un contexte incompatible conserve la proposition SongFormer initiale.

Les corrections de l’utilisateur sont journalisées localement dans le dossier
`Learning` du morceau. Elles ne déclenchent ni envoi automatique sur Internet ni
réentraînement immédiat du modèle distribué.
