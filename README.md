# gbaguidi-lengrai-pprog-2025

## Description générale du projet

Ce projet implémente un simulateur de trafic urbain en OCaml.  
Des véhicules circulent sur un réseau de routes et d’intersections, et un agent d’apprentissage par renforcement (RL) contrôle dynamiquement les feux pour fluidifier le trafic et réduire les embouteillages.

---

## Problématique

Les feux urbains actuels présentent souvent les limites suivantes :

- cycles fixes et non adaptatifs,
- incapacité à ajuster en temps réel selon le trafic,
- contribution aux embouteillages, à la pollution et à l’allongement des temps de trajet.

---

## Objectif

Développer un système de signalisation adaptatif capable d’observer l’état du trafic et de modifier les feux en conséquence, via :

- simulation du trafic en OCaml,
- définition d’un MDP (état, actions, récompenses),
- entraînement d’un agent RL,
- évaluation scientifique de la performance (temps de trajet, files d’attente, throughput).

---

## Objectifs du projet

### Objectif principal

- Créer un simulateur complet avec contrôle intelligent des feux via RL.

### Objectifs intermédiaires

- Modéliser un graphe routier minimal (routes, intersections, feux),
- Implémenter la physique du trafic (déplacement, vitesse, files, collisions),
- Définir un MDP cohérent,
- Implémenter un agent RL simple (Q-learning tabulaire),
- Rédiger des tests unitaires pour chaque module.

---

## Entrées et sorties du programme

### Entrées

1. **Réseau routier (`network`)**

type light_color = Red | Green | Yellow

type road = {
id : road*id;
length : float; (* mètres _)
speed_limit : float; (_ m/s _)
nodes : node_id list; (_ trajectoire de la route _)
next : node_id; (_ nœud ou intersection de destination \_)
}

type intersection = {
id : intersection*id;
incoming : road_id list; (* routes entrantes _)
outgoing : road_id list; (_ routes sortantes _)
light_state : (road_id _ light*color) list; (* état initial des feux _)
}
type vehicle = {
id : vehicle_id;
current_road : road_id;
position : float; (_ distance depuis le début de la route en mètres _)
speed : float; (_ vitesse en m/s _)
}
type sim_config = {
network : network; (_ réseau complet _)
initial_vehicles : vehicle list; (_ véhicules initiaux _)
dt : float; (_ pas de temps de simulation en secondes _)
max_time : float; (_ durée maximale de simulation _)
random_seed : int option; (_ graine pour reproductibilité _)
}
type state = {
queue_lengths : int list; (_ nombre de voitures par voie entrante _)
light_config : light_color list; (_ configuration actuelle des feux \*)
}

type action =
| SwitchLights of (road_id \* light_color) list
| Keep

## Sorties

type traffic*stats = {
mean_travel_time : float; (* temps moyen de trajet _)
mean_queue_length : float; (_ longueur moyenne des files d’attente _)
throughput : float; (_ véhicules écoulés par unité de temps _)
}
type snapshot = {
time : float; (_ instant de l’instantané _)
state : state; (_ état du MDP à cet instant _)
vehicles : vehicle list; (_ positions et vitesses des véhicules \_)
}

type simulation_trace = snapshot list

Algorithmes impliqués

1. Simulation physique

Discrétisation du temps Δt

Mise à jour des positions : position ← position + speed × Δt

Gestion des files d’attente et des ralentissements

Arrêt obligatoire au feu rouge

Prévention des collisions (distance minimale)

2. Définition du MDP

État : longueurs des files + configuration des feux

Action : changer ou conserver la configuration des feux

Transition : propagation du trafic selon la physique + changement des feux

Récompense : négative si files longues, positive si throughput élevé, basée sur la réduction du temps de trajet

3. Q-Learning

Table Q en Hashtbl

Politique ε-greedy
