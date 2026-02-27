# Simulateur de Trafic Urbain — Paris 13e

## Objectif

Ce projet simule la circulation de véhicules sur le réseau routier réel du 13e arrondissement de Paris (données OpenStreetMap). Des véhicules calculent leur trajet via Dijkstra, respectent les feux de circulation et gèrent les priorités aux intersections.

L'objectif à terme est de brancher un agent d'apprentissage par renforcement (Q-learning) sur les feux pour les rendre adaptatifs : observer l'état du trafic, choisir une action sur les feux, et maximiser le débit tout en réduisant les files d'attente.

---

## Données en entrée

Les entrées sont le réseau routier OSM et la configuration initiale de la simulation.

```ocaml
(* Identifiants *)
type node_id         = int
type road_id         = int
type intersection_id = int
type vehicle_id      = int

(* Couleur d'un feu dans la configuration statique du réseau *)
type light_color =
  | Red
  | Green
  | Yellow

(* Une route : séquence de nœuds OSM avec vitesse limite *)
type road = {
  road_id     : road_id;
  length      : float;         (* mètres *)
  speed_limit : float;         (* m/s *)
  nodes       : node_id list;  (* nœuds OSM traversés dans l'ordre *)
  next        : node_id;       (* nœud de destination, -1 si absent *)
  name        : string;
}

(* Un feu de circulation OSM (position GPS brute) *)
type traffic_signal = {
  signal_id : int;
  sig_lat   : float;
  sig_lon   : float;
}

(* Une intersection : routes entrantes/sortantes + état initial des feux *)
type intersection = {
  inter_id    : intersection_id;
  inter_lat   : float;
  inter_lon   : float;
  incoming    : road_id list;
  outgoing    : road_id list;
  light_state : (road_id * light_color) list;
}

(* Réseau complet chargé depuis map_clean.json *)
type network = {
  roads         : road list;
  intersections : intersection list;
  feux          : traffic_signal list;
  net_nodes     : (node_id * (float * float)) list; (* node_id → (lat, lon) *)
}

(* Configuration de la simulation *)
type sim_config = {
  network              : network;
  dt                   : float;      (* pas de temps en secondes *)
  max_time             : float;      (* durée maximale de simulation *)
  initial_vehicle_count: int;        (* véhicules au démarrage *)
  target_vehicles      : int;        (* nombre cible maintenu *)
  max_vehicles         : int;        (* limite haute *)
  random_seed          : int option;
}
```

---

## Données en sortie

Les sorties sont les statistiques de trafic produites à chaque instant et en fin de simulation, ainsi que les données nécessaires au module RL.

```ocaml
(* État d'un véhicule pendant la simulation *)
type vehicle_state =
  | Moving    (* en circulation *)
  | Braking   (* ralentissement *)
  | Stopped   (* arrêt complet : feu, embouteillage, priorité *)
  | Arrived   (* destination atteinte *)
  | NoPath    (* aucun chemin trouvé *)

type vehicle = {
  v_id             : vehicle_id;
  origin_node      : node_id;
  dest_node        : node_id;
  path             : node_id list; (* chemin Dijkstra *)
  v_lat            : float;
  v_lon            : float;
  speed            : float;        (* m/s *)
  v_state          : vehicle_state;
  travel_time      : float;        (* temps de trajet accumulé en secondes *)
  waiting_at_light : bool;
}

(* Statistiques en temps réel (produites à chaque tick) *)
type traffic_stats = {
  total_vehicles : int;
  moving         : int;
  stopped        : int;
  braking        : int;
  at_light       : int;   (* véhicules en attente à un feu *)
  arrived        : int;   (* total arrivés à destination depuis le début *)
  spawned        : int;   (* total créés depuis le début *)
}

(* Statistiques finales (produites à l'arrêt de la simulation) *)
type final_stats = {
  sim_duration_s    : float;        (* durée simulée en secondes *)
  total_spawned     : int;
  total_arrived     : int;
  total_light_stops : int;          (* total d'arrêts aux feux *)
  congested_lights  : node_id list; (* feux ayant dépassé le seuil d'arrêts *)
}

(* État MDP observé par l'agent RL *)
type light_state =
  | LightRed
  | LightGreen
  | LightYellow

type rl_state = {
  queue_lengths : (node_id * int) list;        (* nb véhicules en attente par feu *)
  light_config  : (node_id * light_state) list (* état courant de chaque feu *)
}

(* Action choisie par l'agent RL *)
type rl_action =
  | SwitchLights of (node_id * light_state) list (* modifier ces feux *)
  | Keep                                          (* ne rien changer *)

(* Résultat d'un épisode d'entraînement RL *)
type episode_result = {
  episode_id   : int;
  total_reward : float;
  final_stats  : final_stats;
  steps        : int;
}
```
