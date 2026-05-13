# Simulateur de trafic urbain - Paris 13e

Ce projet simule la circulation sur une partie du reseau routier reel du
13e arrondissement de Paris. Les donnees viennent d'OpenStreetMap, puis sont
nettoyees pour construire un graphe routier utilisable par le simulateur.

Le programme fait circuler des vehicules, gere les feux, les files d'attente,
les intersections, les routes a sens unique et les routes a double sens. Une
partie apprentissage par renforcement permet ensuite de comparer des feux fixes
avec des feux adaptatifs bases sur du Q-learning.

Le projet est fonctionnel, mais les feux intelligents ne sont pas encore
parfaits. Ils ameliorent nettement le debit et souvent les files, mais le gain
sur le temps moyen de trajet reste encore trop faible dans les derniers tests.

## Etat actuel

Dernier entrainement long teste :

```text
300 episodes
300 s simulees par episode
100 vehicules cibles
1172 etats visites sur 61440 possibles
```

Dernier benchmark multi-seeds avec `results/q_table.json` :

| Metrique              | Baseline | RL       | Gain observe | Cible |
|-----------------------|---------:|---------:|-------------:|------:|
| Temps moyen de trajet | 169.721 s | 167.925 s | +1.1%  | +15% |
| File moyenne          | 34.151 veh | 27.329 veh | +20.0% | +20% |
| Debit                 | 8.024 veh/min | 10.973 veh/min | +36.8% | +10% |

Verdict actuel : le benchmark global reste en echec, surtout a cause du temps
moyen de trajet. Le debit est clairement meilleur avec le RL. La file moyenne
est presque au seuil, mais l'arrondi masque le fait que la valeur reelle reste
legerement sous la cible.

`results/q_table_best.json` a aussi ete teste. Il donne un meilleur gain sur le
temps moyen de trajet, mais il est moins bon sur les files et le debit. Pour le
moment, `results/q_table.json` est donc la table la plus interessante.

## Lancer le projet

```bash
make setup
make data
make run
```

Commandes utiles :

```bash
make run        # simulation avec feux fixes
make rl-run     # simulation avec l'agent Q-learning
make console    # simulation courte sans interface graphique
make test       # tests unitaires
make check      # verification de la syntaxe Python
```

Commandes pour le Q-learning :

```bash
make rl-demo
make rl-train
make rl-bench
make rl-all
```

Exemple d'entrainement plus serieux :

```bash
make rl-train RL_EPISODES=300 RL_MAX_TIME=300 RL_VEHICLES=100
```

Exemple de benchmark sur plusieurs seeds :

```bash
make rl-bench BENCH_QTABLE=results/q_table.json BENCH_TIME=300 BENCH_VEHICLES=100 BENCH_SEEDS=42,43,44,45,46
```

Pour tester la meilleure table sauvegardee pendant l'entrainement :

```bash
make rl-bench BENCH_QTABLE=results/q_table_best.json BENCH_TIME=300 BENCH_VEHICLES=100 BENCH_SEEDS=42,43,44,45,46
```

## Organisation du code

```text
python/
  simulation/
    graph.py              graphe routier et Dijkstra
    lights.py             feux fixes, groupes de carrefours, securite des phases
    metrics.py            mesures de trafic
    vehicle.py            gestionnaire des vehicules
    vehicle_*.py          mouvement, files, intersections, geometrie
    loader.py, models.py  chargement des donnees

  gui/
    app.py                boucle Pygame
    renderer.py           affichage carte, vehicules, feux, HUD

  rl/
    agent.py              agent Q-learning
    env.py                environnement RL et controleur pour la GUI
    train.py              entrainement
    benchmark.py          comparaison feux fixes / feux RL
    analysis.py           recommandations de cycles
    demo.py               essai rapide de l'environnement

  data_tools/
    fetch_osm.py          telechargement Overpass
    clean_json.py         nettoyage des donnees OSM

  tests/
    test_rl.py            tests unitaires
```

Les fichiers generes par l'entrainement et le benchmark sont places dans
`results/`. Ce dossier est ignore par Git.

## Fonctionnement de la simulation

Le reseau est charge depuis `data/map_clean.json`. Le graphe contient les noeuds
routiers, les arcs, les distances et les informations de sens de circulation.
Les vehicules choisissent un trajet avec Dijkstra, puis avancent sur les arcs du
graphe.

Les vehicules gerent plusieurs situations :

- suivi du vehicule devant ;
- arret aux feux rouges et orange ;
- file d'attente devant les feux ;
- reservation simple des intersections ;
- detection des conflits dans les zones de carrefour ;
- prise en compte des routes a sens unique et a double sens.

Le simulateur reste volontairement simple. Il ne cherche pas a reproduire toute
la complexite d'une vraie circulation urbaine, mais il donne une base assez riche
pour comparer plusieurs strategies de feux.

## Feux de circulation

Les feux classiques utilisent des cycles fixes. Les feux d'un meme carrefour
sont regroupes en phases A/B pour eviter de donner le vert a deux directions
conflictuelles.

Le controleur de feux impose aussi des regles de securite :

- vert minimal ;
- jaune obligatoire ;
- courte phase tout rouge ;
- vert maximal ;
- pas de passage direct d'une phase verte conflictuelle a une autre.

Ces regles restent actives meme quand le Q-learning demande un changement de
phase. L'agent peut donc proposer une action, mais le controleur garde la main
sur la securite.

## Q-learning

L'agent prend une decision toutes les 5 secondes simulees pour chaque groupe de
feux.

Actions possibles :

```text
KEEP    garder le cycle courant
SWITCH  demander un changement de phase
EXTEND  prolonger le vert courant de 5 secondes
```

L'etat observe par l'agent contient 8 valeurs discretisees :

```text
file phase A
file phase B
saturation phase A
saturation phase B
pression phase A
pression phase B
phase courante
temps passe dans la phase
```

La Q-table est partagee entre les carrefours. Cela veut dire qu'une situation
apprise sur un carrefour peut servir sur les autres.

Formule de mise a jour :

```text
Q(s,a) = Q(s,a) + alpha * (reward + gamma * max(Q(s')) - Q(s,a))
```

Parametres actuels de l'entrainement :

```text
alpha = 0.1
gamma = 0.9
epsilon initial = 1.0
epsilon minimal = 0.08
epsilon_decay = 0.985
```

Chaque episode utilise une seed differente. C'est important, car l'agent ne doit
pas apprendre uniquement un seul scenario de circulation.

## Recompense RL

La recompense cherche a eviter les longues files et a faire passer plus de
vehicules. Elle tient compte de :

- la pression du cote rouge ;
- la pression du cote vert ;
- le temps d'attente maximal ;
- la saturation des files ;
- le temps moyen passe par les vehicules dans le reseau ;
- la proportion de vehicules arretes ;
- les carrefours qui empirent entre deux decisions ;
- les actions inutiles ou prises au mauvais moment.

L'objectif n'est donc pas seulement de changer les feux souvent. L'agent doit
apprendre quand il vaut mieux garder une phase, quand il faut changer, et quand
il faut prolonger un vert.

## Benchmark

Le benchmark compare deux conditions :

```text
Baseline : feux fixes
RL       : feux controles par la Q-table
```

Les deux conditions sont lancees sur les memes seeds. Le benchmark mesure :

- temps moyen de trajet ;
- file moyenne ;
- debit ;
- carrefours ameliores ;
- carrefours qui empirent.

Le verdict global est valide seulement si les trois cibles sont atteintes en
meme temps. Dans l'etat actuel, le debit passe largement, les files sont proches
du seuil, mais le temps moyen de trajet reste insuffisant.

## Fichiers dans `results/`

```text
q_table.json             derniere Q-table entrainee
q_table_best.json        meilleure Q-table observee pendant l'entrainement
benchmark.json           detail du dernier benchmark
recommended_cycles.json  recommandations de cycles par carrefour
```

Ces fichiers changent apres les entrainements et les benchmarks.

## Dependances

Le projet utilise :

- `pygame` pour l'interface graphique ;
- `requests` pour telecharger les donnees OSM avec Overpass ;
- `matplotlib`, peu utilise actuellement.

La simulation et le Q-learning restent en Python classique. Il n'y a pas de
TensorFlow, pas de PyTorch et pas de Gym.

L'API Overpass est utilisee seulement pour recuperer les donnees OSM avec
`make data` ou `make fetch`. Une fois `data/map_clean.json` present, la
simulation fonctionne avec les fichiers locaux.

## Tests

Les tests couvrent surtout la partie RL et la securite des feux :

- creation et sauvegarde de l'agent Q-learning ;
- choix d'action et mise a jour de la Q-table ;
- format des observations de l'environnement RL ;
- changement de seed pendant l'entrainement ;
- penalite quand une file empire brusquement ;
- absence de phases conflictuelles vertes en meme temps.

Lancement :

```bash
make test
```

## Limites connues

Le projet est utilisable pour une demonstration et pour comparer les strategies
de feux, mais il reste des limites :

- le Q-learning ne reduit pas encore assez le temps moyen de trajet ;
- certains carrefours peuvent encore empirer avec la politique RL ;
- la coordination entre carrefours voisins reste limitee ;
- le modele de conduite reste simplifie ;
- les resultats dependent beaucoup de l'entrainement lance.

La suite logique serait de renforcer la recompense sur le temps de trajet, de
mieux proteger les carrefours qui empirent et d'ajouter une coordination entre
carrefours proches.

## Auteurs

- GBAGUIDI Nerval
- LENGRAI Jordan

Programmation avancee 2025, Universite Paris Cite.
