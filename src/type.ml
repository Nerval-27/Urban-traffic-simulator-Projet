(* types.ml
   Ce fichier définit l’ensemble des structures utilisées par le simulateur.
*)

(* Identifiants des entités principales du réseau *)
type intersection_id = int    (* Identifiant d’une intersection *)
type road_id = int            (* Identifiant d’une route *)
type vehicle_id = int         (* Identifiant d’un véhicule *)

(* Identifiants des nœuds géographiques.
   Les valeurs issues du JSON peuvent dépasser 2^31, d’où l’utilisation de int64 *)
type node_id = int64

(* États possibles d’un feu de circulation *)
type light_color =
  | Red     (* Arrêt obligatoire *)
  | Green   (* Passage autorisé *)
  | Yellow  (* Phase de transition / avertissement *)

(* Représentation d’une route du réseau *)
type road = {
  id : road_id;              (* Identifiant unique de la route *)
  length : float;            (* Longueur de la route (en mètres) *)
  speed_limit : float;       (* Vitesse maximale autorisée (en m/s) *)
  nodes : node_id list;      (* Suite ordonnée de nœuds représentant la géométrie *)
  next : node_id;            (* Nœud ou intersection de destination *)
}

(* Représentation d’une intersection routière *)
type intersection = {
  id : intersection_id;              (* Identifiant unique de l’intersection *)
  incoming : road_id list;          (* Liste des routes entrantes *)
  outgoing : road_id list;          (* Liste des routes sortantes *)
  light_state : (road_id * light_color) list; (* État des feux par route entrante *)
}

(* Représentation d’un véhicule individuel *)
type vehicle = {
  id : vehicle_id;           (* Identifiant du véhicule *)
  current_road : road_id;   (* Route sur laquelle il se trouve actuellement *)
  position : float;         (* Distance depuis le début de la route (en mètres) *)
  speed : float;            (* Vitesse instantanée (en m/s) *)
}

(* État utilisé par le modèle MDP (Markov Decision Process) *)
type state = {
  queue_lengths : int list;     (* Taille des files sur chaque voie entrante *)
  light_config : light_color list;  (* Configuration actuelle des feux correspondants *)
}

(* Actions possibles du système de contrôle *)
type action =
  | SwitchLights of (road_id * light_color) list (* Modification ciblée des feux *)
  | Keep                                        (* Aucun changement appliqué *)

(* Statistiques calculées à la fin d’une simulation *)
type traffic_stats = {
  mean_travel_time : float;   (* Temps moyen de trajet d’un véhicule *)
  mean_queue_length : float;  (* Longueur moyenne des files d’attente *)
  throughput : float;         (* Débit moyen de véhicules par unité de temps *)
}

(* Instantané à un instant donné de la simulation *)
type snapshot = {
  time : float;            (* Temps courant de la simulation *)
  state : state;           (* État global du MDP à cet instant *)
  vehicles : vehicle list; (* Liste complète des véhicules présents *)
}

(* Historique complet d’une simulation *)
type simulation_trace = snapshot list

(* Représentation complète du réseau routier *)
type network = {
  roads : road list;                (* Ensemble des routes du réseau *)
  intersections : intersection list;(* Ensemble des intersections *)
}

(* Configuration globale d’une simulation *)
type sim_config = {
  network : network;             (* Structure du réseau routier *)
  initial_vehicles : vehicle list; (* Liste initiale des véhicules *)
  dt : float;                    (* Pas de temps de simulation (en secondes) *)
  max_time : float;              (* Durée maximale de la simulation *)
  random_seed : int option;      (* Graine optionnelle pour la reproductibilité *)
}
