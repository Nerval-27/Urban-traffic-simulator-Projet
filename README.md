#gbaguidi-lengrai-pprog-2025

##Description générale du projet

Ce projet vise à développer un simulateur de trafic urbain, codé intégralement en OCaml, dans lequel circulent des véhicules sur un réseau de routes et d’intersections.

Sur ce simulateur, nous implémenterons ensuite un agent d’apprentissage par renforcement (RL) chargé de contrôler dynamiquement les feux de circulation afin de réduire les embouteillages et d’optimiser la fluidité du trafic.

##Quel problème le projet résout-il ?

Les systèmes de feux urbains actuels sont généralement :

à cycle fixe,

incapables de s’adapter en temps réel,

responsables d’embouteillages, de pollution et d'une augmentation du temps d’attente.

##Notre objectif

Créer un système de signalisation adaptatif, capable d’observer l’état réel du trafic et d’ajuster dynamiquement les feux afin de fluidifier la circulation.

Pour cela, nous :

Simulons le trafic (sans bibliothèques externes comme SUMO),

Définissons un MDP (états, actions, récompenses),

Entraînons un agent RL (Q-learning ou Deep RL),

Mesurons scientifiquement les améliorations (temps moyen de trajet, longueur des files, throughput…).

##Objectifs du projet

###Objectif principal

Construire un simulateur complet de trafic urbain, doté d’un contrôle intelligent des feux par RL, en OCaml (ou un autre langage encore à définir).

###Objectifs intermédiaires

Modéliser un graphe routier minimal (routes, intersections, feux),

Implémenter la physique du trafic (déplacement, vitesse, files, évitement des collisions),

Définir précisément un MDP,

Implémenter un agent RL simple (Q-learning tabulaire),

Rédiger des tests unitaires pour chaque module.

##Entrées et Sorties du programme

Dans cette section, nous présentons les types OCaml représentant les données d’entrée (réseau, trafic, RL) et les données de sortie (statistiques, traces de simulation).

###Entrées

### 1. Paramètres du réseau

type intersection_id = int
type road_id = int

Type road
type road = {
id : road_id;
length : float; (_ en mètres _)
speed_limit : float; (_ en m/s _)
next : intersection_id; (_ intersection d'arrivée _)
}

Type light_color
type light_color = Red | Green | Yellow

Type intersection
type intersection = {
id : intersection_id;
incoming : road_id list;
outgoing : road_id list;
light_state : (road_id, light_color) Hashtbl.t;
}

### 2. Paramètres du trafic

Type vehicle
type vehicle = {
id : int;
current_road : road_id;
position : float; (_ distance depuis le début de la route _)
speed : float; (_ vitesse actuelle en m/s _)
}

### 3. Paramètres RL

Type state
type state = {
queue_lengths : int list; (_ nb de voitures par voie entrante _)
light_config : light_color list;
}

Type action
type action =
| SwitchLights of (road_id \* light_color) list
| Keep

Sorties

### 1. Statistiques du trafic

Type traffic_stats
type traffic_stats = {
mean_travel_time : float; (_ temps moyen de trajet des véhicules _)
mean_queue_length : float; (_ longueur moyenne des files d'attente _)
throughput : float; (_ nombre de véhicules écoulés par unité de temps _)
}

### 2. Trace de simulation (pour visualisation)

Type simulation_trace
type simulation_trace = (float _ state _ vehicle list) list

Ce type représente une liste de snapshots, où chaque élément contient :

un temps float,

l’état du MDP (state),

la liste complète des véhicules avec leurs positions et vitesses.

##Algorithmes impliqués

### 1. Simulation physique

Discrétisation du temps Δt,

Mise à jour du mouvement :
position ← position + speed × Δt,

Gestion des files d’attente (ralentissement, arrêt),

Arrêt obligatoire au feu rouge,

Prévention simple des collisions (distance minimale).

### 2. Définition du MDP

État : longueurs des files + configuration des feux,

Action : changer ou conserver la configuration des feux,

Transition : propagation du trafic selon la physique + changement de feux,

Récompense :

négative si files longues,

positive si throughput élevé,

basée sur la réduction du temps de trajet.

### 3. Q-Learning

Table Q en Hashtbl,

Politique ε-greedy,

Mise à jour :

Q(s,a) ← Q(s,a) + α ( r + γ max_a' Q(s',a') − Q(s,a) )

Entraînement sur plusieurs épisodes.
