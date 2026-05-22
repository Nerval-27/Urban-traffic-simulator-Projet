# Simulateur de trafic urbain - Paris 13e

## A quoi sert ce projet

Dans toutes les villes, des voitures attendent au feu rouge alors que la
rue d'en face est vide. Le probleme, c'est que les feux suivent encore
des cycles fixes, calcules pour un trafic moyen qui n'existe en realite
jamais. Resultat : du temps perdu pour les usagers, du trafic en plus,
et de l'energie gaspillee.

Notre projet est un **outil d'aide a la decision** pour optimiser un
reseau de feux existant, sans toucher aux routes et sans depenser un
centime en travaux. On reproduit la circulation d'un quartier reel a
partir des donnees OpenStreetMap, on compare une politique de feux
fixes a une politique adaptative pilotee par un agent Q-learning, et
on en deduit pour chaque carrefour une **duree de phase recommandee**
qu'on peut appliquer directement.

Concretement, sur le 13e arrondissement de Paris, notre agent fait
passer **plus de 40 % de voitures en plus** dans le meme intervalle de
temps, augmente la vitesse moyenne effective de **25 %**, et reduit
l'attente moyenne aux feux de **14 %**. Sur les dix carrefours les
plus engorges du reseau, **huit sur dix sont ameliores**, avec un gain
qui peut atteindre **84 %** sur le carrefour le plus charge, juste en
changeant la duree des phases.

## Ce que notre outil produit pour une ville

A partir d'une zone urbaine reelle :

1. Une **simulation complete** de la circulation avec un comportement
   realiste : itineraires Dijkstra, files d'attente, priorites,
   suivi entre vehicules, sens uniques.
2. Une **comparaison chiffree** entre la politique actuelle (cycles
   fixes) et une politique optimisee par apprentissage par renforcement.
3. Un fichier `recommended_cycles.json` qui contient, **carrefour par
   carrefour**, la duree de phase recommandee, le gain attendu sur la
   file d'attente, et une phrase de verdict en francais.

Cet outil sert a tester une strategie de feux **avant** de la deployer.
On peut identifier les carrefours qui meritent une attention
particuliere, prolonger un vert qui le merite, raccourcir une phase
qui sert a rien, et mesurer le gain attendu sur l'ensemble du reseau.

## Resultats chiffres

Benchmark realise sur 300 secondes simulees, 100 vehicules cibles,
**moyenne sur 5 simulations** avec des graines aleatoires differentes
(42 a 46) pour eviter qu'un coup de chance ne fausse les resultats.

### Cibles fixees dans le rapport intermediaire

| Metrique              | Baseline | RL       | Variation | Cible | Statut |
|-----------------------|---------:|---------:|----------:|------:|:------:|
| Temps moyen de trajet | 168.0 s  | 161.0 s  | -4.2%     | -15%  | FAIL   |
| File moyenne          | 34.0     | 27.4     | -19.6%    | -20%  | FAIL   |
| Debit                 | 8.0      | 11.2     | +40.9%    | +10%  | PASS   |

Verdict : **PROGRES PARTIEL (1/3 cibles atteintes)**. La file moyenne
est a 0,4 point de la cible, le debit la depasse largement, et le
temps moyen de trajet est trompeur a cause d'un biais : le RL fait
arriver des vehicules a longs trajets qui restaient bloques en
baseline, ce qui tire la moyenne vers le haut.

### Indicateurs robustes au biais de selection

| Metrique                  | Baseline | RL        | Variation | Cible | Statut |
|---------------------------|---------:|----------:|----------:|------:|:------:|
| Trip median               | 168.6 s  | 162.7 s   | -3.4%     | -5%   | FAIL   |
| Vitesse moyenne effective | 5.78 m/s | 7.26 m/s  | +25.6%    | +10%  | PASS   |
| Attente moyenne aux feux  | 28.5 s   | 24.4 s    | -14.4%    | -15%  | FAIL   |
| Debit                     | 8.0 v/min| 11.2 v/min| +40.9%    | +10%  | PASS   |

Verdict : **SUCCES MAJORITAIRE (2/4 cibles atteintes)**. Sur les six
indicateurs mesures (trois cibles officielles plus quatre robustes),
**tous vont dans le bon sens, sans aucune regression**.

## Comment lancer le projet

```bash
make setup       installe le venv et les dependances
make data        telecharge les donnees OSM (1ere fois seulement)

make run         simulation visuelle avec cycles fixes
make rl-run      simulation visuelle avec l'agent RL
make console     simulation 10 s sans interface graphique

make rl-demo     test rapide avec actions au hasard
make rl-train    entraine l'agent Q-learning
make rl-bench    compare baseline vs RL et ecrit les recommandations
make rl-all      entrainement + benchmark enchaines

make test        18 tests unitaires
make check       verifie la syntaxe Python
make help        liste toutes les commandes
```

Parametres surchargeables :

```bash
make rl-train RL_EPISODES=60 RL_MAX_TIME=180 RL_VEHICLES=100
make rl-bench BENCH_TIME=300 BENCH_VEHICLES=100 BENCH_SEEDS=42,43,44,45,46
```

## Sortie principale : les recommandations par carrefour

Apres un benchmark, le fichier `results/recommended_cycles.json`
contient pour **chaque carrefour** une entree de ce type :

```json
"carrefour_188": {
  "current_fixed":  {"green_A": 35, "yellow_A": 4, "green_B": 35},
  "rl_observed":    {"green_A_avg": 70.0, "green_B_avg": 4.75},
  "recommended":    {"green_A": 70, "yellow_A": 4, "green_B": 8},
  "verdict":        "RL recommande : phase A prolongee de 35s (35s -> 70s) ; phase B raccourcie de 30s (35s -> 5s)",
  "performance":    {"avg_queue_baseline": 0.15,
                     "avg_queue_rl":       0.00,
                     "improvement_pct":    99.0}
}
```

Sur ce carrefour, l'outil recommande de doubler le vert d'une
direction et de raccourcir l'autre. La file moyenne tombe a zero,
soit **99 % de gain**.

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
    train.py             entrainement avec sauvegarde de la meilleure Q-table
    benchmark.py         comparaison multi-seed feux fixes vs feux RL
    analysis.py          recommandations de cycles par carrefour
    demo.py              essai rapide de l'environnement

  data_tools/
    fetch_osm.py         telechargement Overpass
    clean_json.py        nettoyage des donnees OSM

  tests/
    test_rl.py           18 tests unitaires

  main.py                point d'entree console
  requirements.txt       dependances Python

data/                    donnees OSM brutes et nettoyees
results/                 sorties JSON (q_table, benchmark, recommandations)
report/                  rapport LaTeX
Makefile                 toutes les commandes
```

## Comment fonctionne l'agent RL

### Etat observe par carrefour

4 nombres entiers, soit 240 combinaisons possibles :

- file phase A    : 0, 1-2, 3-5, ou 6 et plus
- file phase B    : idem
- phase courante  : A vert, A jaune, B vert, B jaune, tout rouge
- temps dans la phase : court, moyen, long

### Actions possibles

L'agent decide toutes les 5 secondes simulees, parmi trois choix :

```text
KEEP    laisse le cycle continuer normalement
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

On punit surtout les voitures bloquees au rouge (celles qu'un SWITCH
ou un EXTEND peut aider), pas celles qui passent deja au vert.

### Q-table partagee

Une seule Q-table sert aux 250 carrefours du reseau. Comme l'etat est
decrit de la meme maniere pour tous, ce qui est appris a un carrefour
sert aux autres.

Formule de mise a jour :

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

Chaque episode d'entrainement utilise une graine aleatoire differente
pour que l'agent voie plusieurs scenarios et ne s'enferme pas dans un
cas particulier.

## Securite des feux

Le simulateur impose des regles de securite que l'agent ne peut pas
contourner :

- vert minimal de 6 secondes ;
- jaune obligatoire avant le rouge ;
- courte phase tout rouge de 1 seconde entre deux phases vertes ;
- jamais deux directions conflictuelles vertes en meme temps.

L'agent peut donc proposer un SWITCH ou un EXTEND, mais le controleur
de feux garde la main sur la securite.

## Controles dans la GUI

| Touche            | Action                                       |
|-------------------|----------------------------------------------|
| WASD ou fleches   | deplace la vue                               |
| Molette           | zoom                                         |
| R                 | revient au zoom de depart                    |
| `+` / `-`         | accelere / ralentit la simulation            |
| N                 | spawn un vehicule a la main                  |
| Clic gauche       | selectionne un vehicule ou un carrefour      |
| Clic droit        | deselectionne                                |
| Echap             | quitte (et ecrit les stats)                  |

En mode RL (`make rl-run`), un cercle bleu s'allume autour des feux
que l'agent vient de toucher. Le HUD affiche le nombre de decisions
KEEP, SWITCH et EXTEND prises depuis le debut.

## Dependances

Listees dans `python/requirements.txt` :

- `pygame`     pour la GUI
- `requests`   pour appeler l'API Overpass
- `matplotlib` (peu utilise)

Tout est en Python standard. Pas de TensorFlow, pas de PyTorch, pas
de gym. La Q-table est un dictionnaire Python sauvegarde en JSON.

## Tests

Les 18 tests verifient :

- agent Q-learning : creation, choix d'action, mise a jour Q,
  sauvegarde et chargement de la table ;
- environnement RL : reset, step, format des observations,
  constantes ;
- verdict du benchmark : SUCCES GLOBAL, SUCCES MAJORITAIRE, PROGRES
  PARTIEL, PROGRES DETECTE ou ECHEC selon les metriques.

Lancement : `make test` (environ 2 secondes).

## Pour aller plus loin

Le Q-learning actuel est volontairement simple, ce qui permet de bien
expliquer chaque decision. Plusieurs ameliorations sont possibles :

- entrainement plus long pour couvrir l'ensemble des 240 etats ;
- enrichir l'etat avec la saturation $\rho = \lambda / \mu$ par phase ;
- coordonner les carrefours voisins entre eux (vague verte sur un axe) ;
- remplacer la cible "temps moyen de trajet" par le temps median, plus
  robuste au biais de selection.

## Auteurs

- GBAGUIDI Nerval (nerval.gbaguidi@etu.u-paris.fr)
- LENGRAI Jordan (jordan.lengrai@etu.u-paris.fr)

Programmation avancee 2025, Universite Paris Cite.
