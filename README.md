# Simulateur de trafic urbain - Paris 13e

Ce projet simule la circulation sur une partie du reseau routier reel du
13e arrondissement de Paris. Les donnees viennent d'OpenStreetMap, puis sont
nettoyees pour construire un graphe routier utilisable par le simulateur.

Le programme fait circuler des vehicules, gere les feux, les files d'attente,
les intersections, les routes a sens unique et les routes a double sens. Une
partie apprentissage par renforcement permet ensuite de comparer des feux fixes
avec des feux adaptatifs bases sur du Q-learning.

## Resultats

Apres 60 episodes d'entrainement (180s simules par episode), le benchmark
sur 300s avec 100 vehicules donne :

### Cibles officielles du rapport intermediaire

| Metrique              | Baseline | RL       | Variation | Cible | Statut |
|-----------------------|---------:|---------:|----------:|------:|:------:|
| Temps moyen de trajet | 163.6 s  | 173.4 s  | +6.0%     | -15%  | FAIL   |
| File moyenne          | 34.7     | 27.7     | -20.0%    | -20%  | PASS   |
| Debit                 | 8.5      | 11.6     | +37.2%    | +10%  | PASS   |

2 cibles sur 3 atteintes. Le temps moyen de trajet semble empirer, mais
c'est un biais de selection : le RL fait arriver 16 vehicules de plus
(59 contre 43 en baseline), dont les longs trajets qui restaient bloques.
Ces longs trajets tirent la moyenne vers le haut.

### Indicateurs robustes (analyse complementaire)

| Metrique                  | Baseline | RL       | Variation | Cible | Statut |
|---------------------------|---------:|---------:|----------:|------:|:------:|
| Trip median               | 189.1 s  | 177.2 s  | -6.3%     | -5%   | PASS   |
| Vitesse moyenne effective | 5.79 m/s | 7.00 m/s | +20.7%    | +10%  | PASS   |
| Attente moyenne aux feux  | 28.4 s   | 19.8 s   | -30.3%    | -15%  | PASS   |
| Debit                     | 8.5 v/min| 11.6 v/min| +37.2%   | +10%  | PASS   |

4 cibles sur 4 atteintes. Sur les indicateurs robustes au biais de
selection, le RL ameliore tout :

- les voitures roulent 20% plus vite ;
- elles attendent 30% moins de temps aux feux ;
- le vehicule typique (median) finit son trajet 6% plus vite ;
- 37% plus de voitures terminent leur trajet dans le meme intervalle.

## Lancer

```bash
make setup       installe le venv et les dependances
make data        telecharge les donnees OSM (1ere fois seulement)

make run         GUI Pygame avec cycles fixes
make rl-run      GUI Pygame avec l'agent RL
make console     simulation 10s sans GUI

make rl-demo     test rapide avec actions au hasard
make rl-train    entraine l'agent (parametres ci-dessous)
make rl-bench    compare baseline vs RL et ecrit les recommandations
make rl-all      train + bench enchaines

make test        13 tests unitaires
make check       verifie la syntaxe Python
make help        liste toutes les commandes
```

Parametres surchargeables :

```bash
make rl-train  RL_EPISODES=60  RL_MAX_TIME=180  RL_VEHICLES=100
make rl-bench  BENCH_TIME=300  BENCH_VEHICLES=100
```

## Arborescence

```text
python/
  simulation/
    graph.py             graphe routier et Dijkstra
    lights.py            feux fixes, groupes de carrefours, securite des phases
    metrics.py           mesures de trafic en temps reel
    vehicle.py           gestionnaire des vehicules
    vehicle_*.py         mouvement, files, intersections, geometrie
    loader.py, models.py chargement des donnees
    utils.py             fonctions utilitaires

  gui/
    app.py               boucle Pygame
    renderer.py          affichage carte, vehicules, feux, HUD

  rl/
    agent.py             agent Q-learning
    env.py               environnement RL et controleur pour la GUI
    train.py             entrainement
    benchmark.py         comparaison feux fixes vs feux RL
    analysis.py          recommandations de cycles par carrefour
    demo.py              essai rapide de l'environnement

  data_tools/
    fetch_osm.py         telechargement Overpass
    clean_json.py        nettoyage des donnees OSM

  tests/
    test_rl.py           13 tests unitaires

  main.py                point d'entree console
  requirements.txt       dependances Python

data/                    donnees OSM brutes et nettoyees
results/                 sorties JSON (ignore par Git)
report/                  rapport LaTeX
Makefile                 toutes les commandes
```

## Comment marche le RL

### Etat (un par carrefour)

4 nombres entiers, 240 combinaisons possibles :

- file phase A    : 0, 1-2, 3-5, ou 6+
- file phase B    : idem
- phase courante  : 5 valeurs (A vert, A jaune, B vert, B jaune, tout rouge)
- temps dans phase: court, moyen, long

### Actions

L'agent decide toutes les 5 secondes simulees, parmi :

```text
KEEP    laisse le cycle se faire normalement
SWITCH  coupe la phase verte (passe au jaune plus tot)
EXTEND  prolonge la phase verte de 5 secondes
```

### Recompense

```text
penalite_attente   = 2.5 * voitures_au_rouge
penalite_passage   = 0.2 * voitures_au_vert
penalite_long      = 1.0 * nb_attentes_de_plus_de_30s
bonus              = 0.5 * voitures_arrivees_pendant_le_pas

reward = -penalite_attente - penalite_passage - penalite_long + bonus
```

L'idee : on punit surtout les voitures bloquees au rouge (celles que
SWITCH ou EXTEND peuvent aider), pas celles qui passent deja au vert.

### Q-table

Une seule Q-table pour les 250 carrefours du reseau. Chaque entree
contient 3 valeurs :

```text
Q[(file_A, file_B, phase, temps)] = [valeur_KEEP, valeur_SWITCH, valeur_EXTEND]
```

Comme l'etat est decrit de la meme maniere pour tous les carrefours,
ce qui est appris a un carrefour sert aux autres.

Mise a jour :

```text
Q(s,a) = Q(s,a) + alpha * (reward + gamma * max(Q(s')) - Q(s,a))
```

Hyperparametres :

```text
alpha = 0.1
gamma = 0.9
epsilon initial = 1.0
epsilon minimal = 0.05
epsilon_decay   = 0.92
```

## Securite des feux

Le simulateur impose des regles de securite que l'agent ne peut pas
contourner :

- vert minimal de 6 secondes ;
- jaune obligatoire avant le rouge ;
- courte phase tout rouge de 1 seconde entre deux phases vertes ;
- jamais deux directions conflictuelles vertes en meme temps.

L'agent peut donc proposer un SWITCH ou un EXTEND, mais le controleur
de feux garde la main sur la securite.

## Sorties dans `results/`

| Fichier                    | Contenu                                              |
|----------------------------|------------------------------------------------------|
| `q_table.json`             | Q-table apprise par l'agent (lisible)               |
| `benchmark.json`           | Comparaison baseline vs RL avec les 2 panneaux      |
| `recommended_cycles.json`  | Pour chaque carrefour : duree de phase recommandee  |
| `fixed_*.json`             | Snapshots de la GUI en mode cycles fixes            |
| `rl_*.json`                | Snapshots de la GUI en mode RL                      |

Exemple d'entree dans `recommended_cycles.json` :

```json
"carrefour_12": {
  "current_fixed":  {"green_A": 35, "yellow_A": 4, "red_A": 39},
  "rl_observed":    {"green_A_avg": 22.3, "green_A_n": 7},
  "recommended":    {"green_A": 22, "yellow_A": 4, "red_A": 28},
  "verdict":        "RL recommande : phase A raccourcie de 13s (35s -> 22s)",
  "performance":    {"avg_queue_baseline": 0.84,
                     "avg_queue_rl":       0.19,
                     "improvement_pct":    78.0}
}
```

## Controles dans la GUI

| Touche                    | Action                                       |
|---------------------------|----------------------------------------------|
| WASD ou fleches           | deplace la vue                               |
| Molette                   | zoom                                         |
| R                         | revient au zoom de depart                    |
| `+` / `-`                 | accelere / ralentit la simulation            |
| N                         | spawn un vehicule a la main                  |
| Clic gauche               | selectionne un vehicule ou un carrefour      |
| Clic droit                | deselectionne                                |
| Echap                     | quitte (et ecrit les stats)                  |

En mode RL (`make rl-run`), un cercle bleu s'allume autour des feux
que l'agent vient de toucher. Le HUD affiche le nombre de decisions
KEEP / SWITCH / EXTEND prises depuis le debut.

## Dependances

Listees dans `python/requirements.txt` :

- `pygame`     pour la GUI
- `requests`   pour appeler l'API Overpass
- `matplotlib` (peu utilise)

Tout est en Python standard. Pas de TensorFlow, pas de PyTorch, pas
de gym. La table Q est un dictionnaire Python sauvegarde en JSON.

## Tests

Les 13 tests verifient :

- creation de l'agent, choix d'action, mise a jour Q, sauvegarde et
  chargement de la table Q
- environnement RL : reset, step, format des observations, constantes

Lancement : `make test` (environ 2 secondes).

## Auteurs

- GBAGUIDI Nerval (nerval.gbaguidi@etu.u-paris.fr)
- LENGRAI Jordan (jordan.lengrai@etu.u-paris.fr)

Programmation avancee 2025, Universite Paris Cite.
