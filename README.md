# Simulateur de trafic urbain - Paris 13e

## A quoi sert ce projet

Dans une ville, il arrive souvent que des voitures attendent au feu rouge alors
que la direction opposee est presque vide. Le probleme vient des feux a cycles
fixes : ils suivent une horloge prevue a l'avance, sans regarder l'etat reel du
trafic.

Ce projet propose un simulateur de trafic sur le 13e arrondissement de Paris.
Il sert a comparer deux strategies :

- des feux fixes, qui suivent toujours le meme cycle ;
- des feux adaptatifs, pilotes par un agent Q-learning.

L'objectif n'est pas de reproduire exactement les vrais reglages de la voirie
parisienne. L'objectif est de construire un terrain de test stable : meme carte,
memes vehicules, memes scenarios, puis comparaison mesuree entre une gestion
fixe et une gestion adaptative.

Le simulateur devient donc un outil d'aide a la decision. Il permet de voir ou
les files se forment, quels carrefours s'ameliorent avec le pilotage adaptatif,
et quels carrefours restent difficiles.

## Etat actuel

Le projet contient aujourd'hui :

- une carte routiere nettoyee du 13e arrondissement ;
- un moteur de circulation avec itineraire Dijkstra ;
- une gestion des feux fixes par groupes de carrefours ;
- une gestion des routes a sens unique et a double sens ;
- une logique de files d'attente et de distance de securite ;
- une resolution des conflits aux intersections ;
- un agent Q-learning pour les feux adaptatifs ;
- des metriques de trafic ;
- un benchmark feux fixes contre feux adaptatifs ;
- des recommandations de cycles par carrefour ;
- 18 tests unitaires.

Au lancement, le graphe construit actuellement :

```text
7969 noeuds routiers
8458 arcs
7931 noeuds de spawn valides
326 feux initialises dans 250 carrefours
```

## Resultats actuels

Le dernier benchmark enregistre dans `results/benchmark.json` compare les feux
fixes et le mode Q-learning sur 5 scenarios : seeds `42`, `43`, `44`, `45` et
`46`. Chaque scenario dure environ 300 secondes simulees avec une cible de
100 vehicules actifs.

### Cibles officielles du rapport

| Metrique              | Feux fixes | Q-learning | Variation | Cible | Statut |
|-----------------------|-----------:|-----------:|----------:|------:|:------:|
| Temps moyen de trajet | 168.022 s  | 161.048 s  | -4.2%     | -15%  | FAIL   |
| File moyenne          | 34.038     | 27.356     | -19.6%    | -20%  | FAIL   |
| Debit                 | 7.984/min  | 11.249/min | +40.9%    | +10%  | PASS   |

Verdict actuel : progres partiel. Le debit depasse largement la cible
officielle. La file moyenne progresse fortement, mais reste tres legerement
sous le seuil de 20 %. Le temps moyen de trajet progresse aussi, mais pas assez
pour atteindre la cible fixee dans le rapport.

### Indicateurs complementaires

| Metrique                 | Feux fixes | Q-learning | Variation | Cible | Statut |
|--------------------------|-----------:|-----------:|----------:|------:|:------:|
| Temps de trajet median   | 168.550 s  | 162.740 s  | -3.4%     | -5%   | FAIL   |
| Vitesse moyenne          | 5.783 m/s  | 7.264 m/s  | +25.6%    | +10%  | PASS   |
| Attente moyenne aux feux | 28.530 s   | 24.428 s   | -14.4%    | -15%  | FAIL   |
| Debit                    | 7.984/min  | 11.249/min | +40.9%    | +10%  | PASS   |

Ces indicateurs montrent que le pilotage adaptatif ameliore la fluidite du
reseau : plus de vehicules terminent leur trajet, la vitesse moyenne augmente,
et l'attente moyenne aux feux baisse. Le Q-learning reste perfectible, surtout
sur le temps de trajet median et certains carrefours encore instables.

## Lancer le projet

```bash
make setup       # cree le venv et installe les dependances
make data        # recupere et nettoie les donnees OSM

make run         # lance la GUI avec feux fixes
make rl-run      # lance la GUI avec l'agent Q-learning
make console     # lance une petite simulation sans GUI

make rl-demo     # teste rapidement l'environnement RL
make rl-train    # entraine l'agent Q-learning
make rl-bench    # compare feux fixes et Q-learning
make rl-all      # entraine puis lance le benchmark

make test        # lance les 18 tests unitaires
make check       # verifie la syntaxe Python
make help        # affiche toutes les commandes
```

Parametres par defaut de l'entrainement :

```bash
make rl-train
```

equivaut a :

```text
RL_EPISODES=80
RL_MAX_TIME=180
RL_VEHICLES=100
RL_SEED_BASE=42
```

L'entrainement lance donc 80 episodes de 180 secondes simulees. La seed change
a chaque episode : 42, 43, 44, etc. Les tables apprises sont ecrites dans :

```text
results/q_table.json
results/q_table_best.json
```

Parametres par defaut du benchmark :

```bash
make rl-bench
```

equivaut a :

```text
BENCH_TIME=300
BENCH_VEHICLES=100
BENCH_QTABLE=results/q_table.json
BENCH_SEEDS=42,43,44
```

Pour reproduire le benchmark a 5 seeds utilise dans les resultats ci-dessus :

```bash
make rl-bench BENCH_SEEDS=42,43,44,45,46
```

Le benchmark ecrit ensuite :

```text
results/benchmark.json
results/recommended_cycles.json
```

## Donnees en entree

L'entree principale du simulateur est le fichier nettoye :

```text
data/map_clean.json
```

Il contient le reseau routier, les intersections, les feux, les passages pietons
et les coordonnees des noeuds. Les donnees brutes `data/paris13.json` servent
seulement a reconstruire `map_clean.json` avec `make data`.

Types des donnees d'entree, en syntaxe OCaml :

```ocaml
type node_id = int
type road_id = int
type light_id = int
type intersection_id = int

type coord = {
  lat : float;
  lon : float;
}

type road = {
  id : road_id;
  name : string;
  length : float;        (* metres *)
  speed_limit : float;   (* m/s *)
  oneway : bool;
  nodes : node_id list;
  next : node_id;
}

type intersection = {
  id : intersection_id;
  lat : float;
  lon : float;
  incoming : road_id list;
  outgoing : road_id list;
  has_light : bool;
}

type traffic_signal = {
  id : light_id;
  lat : float;
  lon : float;
}

type pedestrian_crossing = {
  id : int;
  lat : float;
  lon : float;
  is_regulated : bool;
}

type network_input = {
  roads : road list;
  intersections : intersection list;
  feux : traffic_signal list;
  passages : pedestrian_crossing list;
  nodes : (node_id * coord) list;
}
```

Le mode RL utilise aussi une Q-table comme entree quand on lance `make rl-run`
ou `make rl-bench` :

```ocaml
type action = Keep | Switch | Extend

type rl_state = int * int * int * int
(* file_A, file_B, phase, temps_dans_phase *)

type q_values = float * float * float
(* valeur_KEEP, valeur_SWITCH, valeur_EXTEND *)

type q_table_input = {
  alpha : float;
  gamma : float;
  epsilon : float;
  q : (rl_state * q_values) list;
}
```

Dans le JSON, les etats de la Q-table sont stockes sous forme de chaines comme
`"0,2,1,1"`, puis relus comme des tuples d'entiers.

## Donnees en sortie

Le projet produit trois familles de sorties :

- une sortie visuelle : la fenetre Pygame avec la carte, les feux, les
  vehicules et le HUD ;
- des sorties d'entrainement : les Q-tables sauvegardees en JSON ;
- des sorties d'analyse : benchmark, observations, snapshots et
  recommandations de cycles.

Types des principales sorties, en syntaxe OCaml :

```ocaml
type light_summary = {
  avg_queue_length : float;
  max_queue_length : int;
  avg_wait_s : float;
  max_wait_s : float;
  stop_events : int;
}

type metric_summary = {
  duration_s : float;
  spawned : int;
  arrived : int;
  active : int;
  completion_rate : float;
  throughput_per_min : float;
  avg_trip_time_s : float;
  median_trip_time_s : float;
  avg_queue_length : float;
  max_queue_length : int;
  avg_waiting_at_lights : float;
  max_waiting_at_light : int;
  avg_light_wait_s : float;
  avg_wait_time_per_spawned_s : float;
  avg_stop_time_per_spawned_s : float;
  avg_speed_m_s : float;
  congestion_ratio : float;
  per_light : (light_id * light_summary) list;
}

type benchmark_row = {
  metric : string;
  key : string;
  baseline : float;
  rl : float;
  improvement : float;
  target : float;
  passed : bool;
}

type comparison = {
  rows : benchmark_row list;
  passed : int;
  total : int;
  all_pass : bool;
  verdict : string;
}

type seed_result = {
  seed : int;
  baseline : metric_summary;
  rl : metric_summary;
}

type benchmark_output = {
  seeds : int list;
  baseline : metric_summary;
  rl : metric_summary;
  per_seed : seed_result list;
  comparison : comparison;
  robust : comparison;
}
```

Les recommandations de cycles sont ecrites dans `recommended_cycles.json` :

```ocaml
type fixed_cycle = {
  green_A : int;
  yellow_A : int;
  green_B : int;
  yellow_B : int;
}

type recommended_cycle = {
  green_A : int;
  yellow_A : int;
  red_A : int;
  green_B : int;
  yellow_B : int;
}

type recommendation_performance = {
  avg_queue_baseline : float;
  avg_queue_rl : float;
  improvement_pct : float;
}

type cycle_recommendation = {
  current_fixed : fixed_cycle;
  recommended : recommended_cycle;
  verdict : string;
  performance : recommendation_performance;
}
```

Les principaux fichiers de sortie sont :

| Fichier | Role |
|---------|------|
| `results/q_table.json` | Q-table finale de l'agent |
| `results/q_table_best.json` | meilleure Q-table rencontree pendant l'entrainement |
| `results/benchmark.json` | comparaison feux fixes contre Q-learning |
| `results/recommended_cycles.json` | recommandations par carrefour |
| `results/fixed_summary.json` | resume d'une simulation en feux fixes |
| `results/rl_summary.json` | resume d'une simulation en mode RL |
| `results/*_snapshots.csv` | mesures prises pendant une simulation |

Le dossier `results/` est ignore par Git, car il contient des sorties
regenerables.

## Sortie principale : recommandations par carrefour

Apres un benchmark, `results/recommended_cycles.json` donne pour chaque
carrefour une proposition de cycle et l'evolution de sa file moyenne. Le meme
fichier contient aussi deux classements :

- les carrefours les plus ameliores ;
- les carrefours qui restent les plus problematiques.

Cela permet de ne pas regarder seulement un score global. On peut voir ou le RL
fonctionne bien, et ou il faudra encore travailler.

## Fonctionnement du Q-learning

Chaque carrefour controle par l'agent est resume par un etat discret :

```text
(file_A, file_B, phase, temps_dans_phase)
```

Les files `A` et `B` sont rangees en quatre categories : aucune voiture,
1-2 vehicules, 3-5 vehicules, ou 6 vehicules et plus. La phase encode l'etat du
carrefour : phase A verte, phase A jaune, phase B verte, phase B jaune, ou tout
rouge. Le temps dans la phase est lui aussi discretise.

L'agent choisit toutes les 5 secondes simulees entre trois actions :

```text
KEEP    laisser le cycle continuer
SWITCH  demander le passage a l'autre phase
EXTEND  prolonger le vert de 5 secondes
```

La recompense favorise les decisions qui reduisent les voitures bloquees au
rouge, limitent les longues attentes et font arriver plus de vehicules :

```text
penalite_attente = 2.5 * voitures_au_rouge
penalite_passage = 0.2 * voitures_au_vert
penalite_longue  = 1.0 * attentes_de_plus_de_30s
bonus_arrivees   = 0.5 * voitures_arrivees

reward = -penalite_attente - penalite_passage - penalite_longue + bonus_arrivees
```

La mise a jour Q-learning est la formule classique :

```text
Q(s,a) = Q(s,a) + alpha * (reward + gamma * max(Q(s')) - Q(s,a))
```

avec :

```text
alpha = 0.1
gamma = 0.9
epsilon initial = 1.0
epsilon minimal = 0.05
epsilon_decay = 0.92
```

## Securite des feux

L'agent ne modifie pas directement les couleurs affichees. Il fait une demande
au controleur de feux, et ce controleur garde les contraintes physiques :

- vert minimal de 6 secondes ;
- jaune obligatoire avant le rouge ;
- phase tout rouge de 1 seconde entre deux phases ;
- pas de vert simultane pour deux directions conflictuelles.

Cela permet de tester une strategie adaptative sans casser les regles de base
d'un carrefour.

## Arborescence

```text
python/
  simulation/
    graph.py             graphe routier et Dijkstra
    lights.py            feux, groupes de carrefours, securite des phases
    metrics.py           mesures de trafic
    vehicle.py           gestionnaire des vehicules
    vehicle_*.py         mouvement, files, intersections, geometrie
    loader.py, models.py chargement des donnees
    utils.py             fonctions utilitaires

  gui/
    app.py               boucle principale Pygame
    renderer.py          affichage carte, vehicules, feux et HUD

  rl/
    agent.py             agent Q-learning
    env.py               environnement RL et controleur de GUI
    train.py             entrainement
    benchmark.py         comparaison feux fixes / Q-learning
    analysis.py          recommandations de cycles
    demo.py              essai rapide de l'environnement

  data_tools/
    fetch_osm.py         recuperation des donnees OSM
    clean_json.py        nettoyage des donnees

  tests/
    test_rl.py           tests unitaires
```

## Controle dans la GUI

| Touche | Action |
|--------|--------|
| WASD ou fleches | deplacer la vue |
| Molette | zoomer |
| R | revenir au zoom de depart |
| `+` / `-` | accelerer ou ralentir |
| N | ajouter un vehicule |
| Clic gauche | selectionner un vehicule ou un carrefour |
| Clic droit | deselectionner |
| Echap | quitter et ecrire les statistiques |

En mode RL, un cercle bleu apparait autour des feux qu'un agent vient de
modifier. Le HUD affiche aussi les decisions `KEEP`, `SWITCH` et `EXTEND`.

## Dependances

Les dependances sont listees dans `python/requirements.txt` :

- `pygame` pour la fenetre graphique ;
- `requests` pour recuperer les donnees OSM avec `make fetch` ;
- `matplotlib`, garde pour les sorties d'analyse.

La partie Q-learning ne depend pas de TensorFlow, PyTorch ou Gym. La Q-table est
un dictionnaire Python sauvegarde en JSON.

## Tests

Les tests verifient principalement :

- la creation de l'agent Q-learning ;
- le choix d'action ;
- la mise a jour de la Q-table ;
- la sauvegarde et le chargement de la Q-table ;
- le format des observations de l'environnement RL ;
- les verdicts du benchmark.

Lancement :

```bash
make test
```

Etat actuel :

```text
Ran 18 tests
OK
```

## Auteurs

- GBAGUIDI Nerval
- LENGRAI Jordan

Programmation avancee 2025, Universite Paris Cite.
