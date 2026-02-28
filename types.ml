(* ================================================================
   types.ml — Types OCaml adaptés du simulateur Python
   Paris 13e Traffic Simulator

   Organisation par module (reflète l'architecture Python) :
     1. Identifiants
     2. models.py   → réseau OSM brut
     3. graph.py    → graphe routier (nœuds + arcs Dijkstra)
     4. traffic_light_manager.py → feux de circulation
     5. vehicle.py  → véhicules et physique
     6. simulation_gui.py → configuration + stats
     7. MDP / RL    → état, action, Q-learning
   ================================================================ *)


type node_id         = int
type road_id         = int
type intersection_id = int
type vehicle_id      = int


(* ----------------------------------------------------------------
   2. models.py — Réseau OSM brut
   ---------------------------------------------------------------- *)

(* models.py : class LightColor *)
type light_color =
  | Red
  | Green
  | Yellow

(* models.py : class Road
   Le champ [name] est optionnel (défaut "Inconnue" en Python) *)
type road = {
  road_id     : road_id;
  length      : float;           (* mètres *)
  speed_limit : float;           (* m/s *)
  nodes       : node_id list;    (* liste ordonnée des nodes OSM traversés *)
  next        : node_id;         (* node de destination finale, -1 si absent *)
  name        : string;          (* nom de la rue, "Inconnue" par défaut *)
}

(* models.py : class TrafficSignal
   Feu OSM brut (position GPS uniquement, avant traitement graph.py) *)
type traffic_signal = {
  signal_id : int;
  sig_lat   : float;
  sig_lon   : float;
}

(* models.py : class PedestrianCrossing *)
type pedestrian_crossing = {
  crossing_id  : int;
  cross_lat    : float;
  cross_lon    : float;
  is_regulated : bool;  (* true si feu de circulation associé *)
}

(* models.py : class Intersection *)
type intersection = {
  inter_id    : intersection_id;
  inter_lat   : float;
  inter_lon   : float;
  incoming    : road_id list;                   (* routes entrantes *)
  outgoing    : road_id list;                   (* routes sortantes *)
  light_state : (road_id * light_color) list;   (* état initial des feux par voie *)
}

(* models.py : class Network
   Réseau complet chargé depuis map_clean.json par loader.py *)
type network = {
  roads         : road list;
  intersections : intersection list;
  feux          : traffic_signal list;          (* feux OSM bruts *)
  passages      : pedestrian_crossing list;
  net_nodes     : (node_id * (float * float)) list;
  (* node_id → (lat, lon) ; en Python : Dict[int, Tuple[float,float]] *)
}

(* models.py : class SimConfig *)
type sim_config = {
  network     : network;
  dt          : float;           (* pas de temps en secondes *)
  max_time    : float;           (* durée maximale de simulation *)
  random_seed : int option;
}


(* ----------------------------------------------------------------
   3. graph.py — Graphe routier orienté pondéré (Dijkstra)
   ---------------------------------------------------------------- *)

(* graph.py : class GraphNode
   Nœud du graphe = node OSM qui appartient à au moins une route carrossable.*)
type graph_node = {
  gn_node_id          : node_id;
  gn_lat              : float;
  gn_lon              : float;
  has_traffic_light   : bool;        (* marqué lors du build si feu OSM proche *)
  traffic_light_id    : int option;  (* id du feu OSM associé, None si absent *)
}

(* graph.py : class GraphEdge
   Arc orienté A → B.
   Le graphe est bidirectionnel en pratique : _add_road_edges crée
   aussi l'arc B → A (reverse_edge) pour chaque route. *)
type graph_edge = {
  from_node          : node_id;
  to_node            : node_id;
  ge_road_id         : road_id;
  road_name          : string;
  distance           : float;      (* mètres *)
  ge_speed_limit     : float;      (* m/s *)
  weight             : float;      (* distance / speed_limit = temps en secondes *)
  intermediate_nodes : node_id list;
}

(* graph.py : class RoadGraph*)
type road_graph = {
  rg_nodes     : (node_id * graph_node) list;
  (* dict[node_id -> GraphNode]  — liste d'adjacence des nœuds *)

  rg_edges     : (node_id * graph_edge list) list;
  (* dict[node_id -> list[GraphEdge]]  — liste d'adjacence sortante *)

  all_edges    : graph_edge list;
  (* toutes les arêtes dans le sens forward uniquement (pour le renderer) *)

  spawn_nodes  : node_id list;
  (* nœuds avec au moins 1 arc sortant = positions de spawn valides *)
}


(* ----------------------------------------------------------------
   4. traffic_light_manager.py — Feux de circulation
   ---------------------------------------------------------------- *)

(* traffic_light_manager.py : class LightState
   Distinct de light_color (models.py) : LightState est l'état runtime du feu,
   light_color est l'état statique dans la config réseau OSM. *)
type light_state =
  | LightRed
  | LightGreen
  | LightYellow

(* traffic_light_manager.py : class TrafficLight
   Un feu individuel avec son timer et son cycle.
   Le cycle est une liste de (état, durée_en_secondes).
   Durées par défaut : vert=10s, orange=3s, rouge=12s (cycle=25s). *)
type traffic_light = {
  tl_node_id           : node_id;
  tl_lat               : float;
  tl_lon               : float;
  cycle                : (light_state * float) list;
  (* liste de (état, durée) — ex: [(Green,10.); (Yellow,3.); (Red,12.)] *)
  current_phase_index  : int;    (* index dans cycle *)
  time_in_phase        : float;  (* secondes déjà passées dans la phase courante *)
  phase_offset         : float;  (* décalage initial pour désynchroniser les feux *)
}

(* traffic_light_manager.py : class TrafficLightManager
   Gestionnaire centralisé.
   _red_waiting_counts : compteur d'arrêts par feu (pour stats et futur RL). *)
type traffic_light_manager = {
  lights              : (node_id * traffic_light) list;
  (* dict[node_id -> TrafficLight] *)
  simulation_time     : float;
  red_waiting_counts  : (node_id * int) list;
  (* dict[node_id -> int] : nb total d'arrêts enregistrés par feu *)
}


(* ----------------------------------------------------------------
   5. vehicle.py — Véhicules et physique du trafic
   ---------------------------------------------------------------- *)

(* vehicle.py : class VehicleState *)
type vehicle_state =
  | Moving    (* circulation normale *)
  | Braking   (* ralentissement progressif *)
  | Stopped   (* arrêt complet : feu, embouteillage, priorité *)
  | Arrived   (* destination atteinte → à supprimer *)
  | NoPath    (* Dijkstra n'a pas trouvé de chemin → supprimé immédiatement *)

(* vehicle.py : class Vehicle
   Position = (lat, lon) interpolée entre deux nœuds consécutifs du chemin.
   seg_from/seg_to : tronçon courant pour la détection de sens inverse. *)
type vehicle = {
  v_id             : vehicle_id;
  origin_node      : node_id;
  dest_node        : node_id;

  path             : node_id list;  (* chemin Dijkstra : liste ordonnée de node_ids *)
  path_index       : int;           (* index du PROCHAIN nœud à atteindre *)

  v_lat            : float;         (* position GPS courante *)
  v_lon            : float;
  speed            : float;         (* m/s *)
  max_speed        : float;         (* vitesse limite du segment courant, m/s *)
  segment_length   : float;         (* longueur du segment courant, mètres *)

  v_state          : vehicle_state;

  color            : int * int * int;  (* RGB pour le renderer Pygame *)
  travel_time      : float;            (* temps total de trajet accumulé *)
  waiting_at_light : bool;
  next_light_node  : node_id option;

  seg_from         : node_id;  (* nœud de départ du segment courant, -1 si inconnu *)
  seg_to           : node_id;  (* nœud d'arrivée du segment courant, -1 si inconnu *)
}

(* vehicle.py : class VehicleManager
   Constantes physiques associées (définies en tête de vehicle.py) : *)
type physics_constants = {
  safe_distance    : float;  (* 8.0  m  — distance min derrière le leader *)
  brake_distance   : float;  (* 25.0 m  — début du freinage car-following *)
  stop_line_dist   : float;  (* 12.0 m  — arrêt devant le feu *)
  light_brake_dist : float;  (* 28.0 m  — début du freinage pour le feu *)
  oncoming_safe    : float;  (* 5.0  m  — arrêt si véhicule inverse trop proche *)
  oncoming_slow    : float;  (* 14.0 m  — ralentissement sens inverse *)
  inter_yield_dist : float;  (* 18.0 m  — distance cédez-le-passage *)
  max_accel        : float;  (* 2.5  m/s² *)
  max_decel        : float;  (* 5.0  m/s² *)
  emerg_decel      : float;  (* 9.0  m/s² *)
  min_speed        : float;  (* 0.3  m/s — seuil arrêt complet *)
  collision_dist   : float;  (* 4.0  m  — seuil collision physique *)
}

(* VehicleManager complet *)
type vehicle_manager = {
  vm_graph         : road_graph;
  vm_light_manager : traffic_light_manager;
  vehicles         : (vehicle_id * vehicle) list;
  (* dict[vehicle_id -> Vehicle] *)
  next_id          : int;
  total_arrived    : int;
  total_spawned    : int;
}


(* ----------------------------------------------------------------
   6. simulation_gui.py
   ---------------------------------------------------------------- *)

(* Paramètres de simulation (constantes en tête de simulation_gui.py) *)
type sim_params = {
  initial_vehicle_count : int;    (* 15  — véhicules au démarrage *)
  max_vehicles          : int;    (* 150 — limite haute *)
  spawn_interval        : float;  (* 5.5 s — intervalle entre spawns auto *)
  target_vehicles       : int;    (* 100 — nombre cible maintenu *)
  sim_speed_default     : float;  (* 1.0 — multiplicateur de vitesse *)
  sim_speed_min         : float;  (* 0.25 *)
  sim_speed_max         : float;  (* 8.0 *)
  random_seed           : int;    (* 42 *)
}

(* Statistiques runtime (get_stats dans VehicleManager) *)
type traffic_stats = {
  total_vehicles   : int;
  moving           : int;
  stopped          : int;
  braking          : int;
  at_light         : int;    (* waiting_at_light = True *)
  arrived          : int;    (* total_arrived *)
  spawned          : int;    (* total_spawned *)
}

(* Statistiques finales (_print_final_stats dans simulation_gui.py) *)
type final_stats = {
  sim_duration_s    : float;   (* durée simulée en secondes *)
  total_spawned     : int;
  total_arrived     : int;
  total_light_stops : int;     (* somme de red_waiting_counts *)
  congested_lights  : node_id list;  (* feux avec > threshold arrêts *)
}

(* a completer avec les types decider pour l'implamnetation des feu inteligent*)
