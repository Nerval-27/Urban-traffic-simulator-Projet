# Simulateur de trafic urbain - Paris 13e

Simulation de trafic sur le reseau routier reel du 13e arrondissement de
Paris (donnees OSM), avec un agent Q-learning qui apprend a piloter les
feux de circulation.

## Resultats

Apres 60 episodes d'entrainement (180s simules par episode), l'agent
fait mieux que les 3 cibles fixees dans le rapport :

| Metrique               | Baseline | RL       | Variation | Cible  |
|------------------------|---------:|---------:|----------:|-------:|
| Temps moyen de trajet  | 166.1 s  | 129.3 s  | -22.1%    | -15%   |
| File moyenne           | 35.3 veh | 2.1 veh  | -94.2%    | -20%   |
| Debit                  | 8.5 v/min| 31.7 v/min| +274.4%  | +10%   |

Sur les 10 carrefours les plus bloques au depart, 9 finissent avec
une file de 0 et le 10e gagne 68%.

## Lancer

```
make setup       installe le venv et les dependances
make data        telecharge les donnees OSM (1ere fois seulement)

make run         lance la GUI Pygame avec cycles fixes
make rl-run      lance la GUI Pygame avec l'agent RL
make console     simulation 10s sans GUI

make rl-demo     test rapide avec actions au hasard
make rl-train    entraine l'agent
make rl-bench    compare baseline vs RL et ecrit les recommandations
make rl-all      train + bench enchaines

make test        lance les 13 tests
make check       verifie la syntaxe Python
make help        liste toutes les commandes
```

On peut changer les valeurs par defaut :

```
make rl-train  RL_EPISODES=60  RL_MAX_TIME=180  RL_VEHICLES=100
make rl-bench  BENCH_TIME=300  BENCH_VEHICLES=100
```

## Arborescence

```
python/
  simulation/      moteur de simulation
    models.py, loader.py, graph.py, utils.py
    lights.py            feux de circulation + cycles A/B
    metrics.py           mesures (debit, files, attentes)
    vehicle.py           VehicleManager
    vehicle_*.py         physique des vehicules (6 fichiers)
  gui/
    app.py               boucle Pygame
    renderer.py          dessin de la carte / vehicules / feux
  rl/
    env.py               environnement RL (reset/step) + RLController
    agent.py             agent Q-learning
    train.py             entrainement
    benchmark.py         comparaison baseline vs RL
    analysis.py          mesure des durees + recommandations
    demo.py              test rapide
  data_tools/
    fetch_osm.py         telecharge depuis Overpass API
    clean_json.py        nettoie le JSON
  tests/                 tests unitaires
  main.py                mode console

data/                    donnees OSM brutes + nettoyees
results/                 sorties JSON
report/                  rapport LaTeX
Makefile                 toutes les commandes
```

## Comment marche le RL

### Etat (un par carrefour)

4 nombres entiers (240 combinaisons possibles au total) :
- nombre de voitures dans la file phase A     (0, 1-2, 3-5, ou 6+)
- nombre de voitures dans la file phase B     (idem)
- phase qui est verte ou jaune en ce moment   (5 valeurs : A vert, A jaune, B vert, B jaune, tout rouge)
- depuis combien de temps on est dans la phase  (court, moyen, long)

### Actions

L'agent decide toutes les 5 secondes simulees, parmi :
- KEEP   : on laisse le cycle se faire normalement
- SWITCH : on coupe la phase verte (passe au jaune plus tot)
- EXTEND : on prolonge la phase verte de 5 secondes

### Recompense

```
penalite_attente = 2.5 * voitures_au_rouge
penalite_passage = 0.2 * voitures_au_vert
penalite_long    = 1.0 * nombre_d_attentes_de_plus_de_30s
bonus            = 0.5 * voitures_arrivees_pendant_le_pas

reward = -penalite_attente - penalite_passage - penalite_long + bonus
```

L'idee : on punit surtout les voitures bloquees au rouge (celles que
SWITCH ou EXTEND peuvent aider), pas celles qui passent deja au vert.

### Table Q

On a une seule table Q pour les 250 carrefours du reseau. Chaque case
contient 3 valeurs :

```
Q[(file_A, file_B, phase, temps)] = [valeur_KEEP, valeur_SWITCH, valeur_EXTEND]
```

Comme l'etat est decrit pareil pour tous les carrefours, ce qui est
appris a un carrefour sert aux autres.

Mise a jour de la table Q :
```
Q(s,a) = Q(s,a) + alpha * (reward + gamma * max(Q(s')) - Q(s,a))
```
Avec alpha=0.1, gamma=0.9, et epsilon qui passe de 1.0 a 0.05 au fil
des episodes.

## Sorties dans `results/`

| Fichier                    | Contenu                                              |
|----------------------------|------------------------------------------------------|
| `q_table.json`             | Table Q apprise (en JSON, lisible)                  |
| `benchmark.json`           | Comparaison baseline vs RL sur les 3 metriques      |
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
| WASD ou fleches           | bouge la vue                                 |
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
- creation de l'agent, choix d'action, mise a jour, sauvegarde et
  chargement de la table Q
- environnement RL : reset, step, format des observations, constantes

Lancement : `make test` (~2 secondes).

## Auteurs

- GBAGUIDI Nerval (nerval.gbaguidi@etu.u-paris.fr)
- LENGRAI Jordan (jordan.lengrai@etu.u-paris.fr)

Programmation avancee 2025, Universite Paris Cite.
