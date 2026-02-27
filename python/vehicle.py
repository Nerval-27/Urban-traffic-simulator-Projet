
import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

from graph import RoadGraph, haversine
from traffic_light_manager import TrafficLightManager, LightState



# Constantes


# Car-following (même sens)
SAFE_DISTANCE   = 8.0   # m  — distance minimale derrière le leader
BRAKE_DISTANCE  = 25.0  # m  — distance à partir de laquelle on commence à freiner

# Feux
STOP_LINE_DIST  = 12.0  # m  — on s'immobilise à cette distance du nœud-feu
LIGHT_BRAKE_DIST = 28.0 # m  — on commence à freiner pour le feu

# Sens inverse
ONCOMING_SAFE   = 5.0   # m  — arrêt quasi-immédiat si véhicule inverse plus proche
ONCOMING_SLOW   = 14.0  # m  — ralentissement à l'approche d'un véhicule inverse

# Intersection / priorité à droite
INTER_YIELD_DIST = 18.0 # m  — distance au nœud d'intersection à partir de laquelle
                         #      on "regarde" si quelqu'un arrive à droite


MAX_ACCEL       = 2.5   # m/s²
MAX_DECEL       = 5.0   # m/s²
EMERG_DECEL     = 9.0   # m/s²
MIN_SPEED       = 0.3   # m/s — en dessous : considéré à l'arrêt


COLLISION_DIST  = 4.0   # m  — distance physique de collision


class VehicleState(Enum):
    MOVING  = auto()
    BRAKING = auto()
    STOPPED = auto()
    ARRIVED = auto()
    NO_PATH = auto()



@dataclass
class Vehicle:
    vehicle_id:   int
    origin_node:  int
    dest_node:    int

    path:         List[int] = field(default_factory=list)
    path_index:   int       = 0    # index du PROCHAIN nœud à atteindre

    lat:          float     = 0.0
    lon:          float     = 0.0
    speed:        float     = 0.0
    max_speed:    float     = 11.1  # vitesse limite segment courant (m/s)
    segment_length: float   = 0.0

    state:        VehicleState = VehicleState.STOPPED

    color:        Tuple[int, int, int] = (255, 200, 0)
    travel_time:  float     = 0.0
    waiting_at_light: bool  = False
    next_light_node: Optional[int] = None

    # Tronçon courant : from → to  (pour détection sens inverse)
    seg_from:     int = -1
    seg_to:       int = -1




class VehicleManager:

    def __init__(self, graph: RoadGraph, light_manager: TrafficLightManager,
                 rng: Optional[random.Random] = None):
        self.graph         = graph
        self.light_manager = light_manager
        self.rng           = rng or random.Random(0)

        self.vehicles:     Dict[int, Vehicle] = {}
        self._next_id      = 0
        self.total_arrived = 0
        self.total_spawned = 0



    def spawn_vehicle(self,
                      origin_node: Optional[int] = None,
                      dest_node:   Optional[int] = None):
        """
        Crée un véhicule A→B.
        Retourne None si :
          - Dijkstra ne trouve pas de chemin
          - La position de spawn est déjà occupée
        """
        pool = self.graph.get_spawn_nodes()
        if len(pool) < 2:
            return None

        for _ in range(20):
            o = origin_node if origin_node is not None else self.rng.choice(pool)
            d = dest_node   if dest_node   is not None else self.rng.choice(pool)
            if o != d:
                break
        else:
            return None

        path = self.graph.dijkstra(o, d)

        vid = self._next_id
        self._next_id += 1

        color = (self.rng.randint(180, 255),
                 self.rng.randint(100, 200),
                 self.rng.randint(0,   80))

        on = self.graph.nodes.get(o)
        if on is None:
            return None

        v = Vehicle(
            vehicle_id=vid, origin_node=o, dest_node=d,
            path=path if path else [],
            path_index=1,
            lat=on.lat, lon=on.lon,
            speed=0.0, color=color,
        )

        if not path or len(path) < 2:
            v.state = VehicleState.NO_PATH
        else:
            v.state = VehicleState.MOVING
            self._init_segment(v)

        # Vérification position libre
        self.vehicles[vid] = v
        if v.state != VehicleState.NO_PATH and not self._spawn_free(v):
            del self.vehicles[vid]
            return None

        self.total_spawned += 1
        return v

    def spawn_batch(self, count: int) -> int:
        ok = 0
        for _ in range(count):
            v = self.spawn_vehicle()
            if v and v.state != VehicleState.NO_PATH:
                ok += 1
        return ok



    def update(self, dt: float) -> None:
        to_remove = []
        for vid, v in self.vehicles.items():
            if v.state in (VehicleState.ARRIVED, VehicleState.NO_PATH):
                to_remove.append(vid)
                continue
            v.travel_time += dt
            self._update_vehicle(v, dt)
            if v.state == VehicleState.ARRIVED:
                to_remove.append(vid)
                self.total_arrived += 1

        for vid in to_remove:
            del self.vehicles[vid]

        # Filet de sécurité après tous les déplacements
        self.check_collisions()

    # Mise à jour d'un véhicule

    def _update_vehicle(self, v: Vehicle, dt: float) -> None:

        if not v.path or v.path_index >= len(v.path):
            v.state = VehicleState.ARRIVED
            return

        target_nid  = v.path[v.path_index]
        target_node = self.graph.nodes.get(target_nid)
        if target_node is None:
            v.state = VehicleState.ARRIVED
            return

        dist_to_target = haversine(v.lat, v.lon, target_node.lat, target_node.lon)

        #Feux de circulation
        stop_for_light = self._check_traffic_light(v, target_nid, dist_to_target)
        if stop_for_light:
            v.state = VehicleState.STOPPED
            v.speed = 0.0
            return
        else:
            if v.waiting_at_light:
                v.waiting_at_light = False
                v.state = VehicleState.MOVING

        # Calcul de la vitesse désirée
        desired = v.max_speed

        # Véhicule devant sur le même segment
        gap_ahead = self._gap_to_leader(v, target_nid, dist_to_target)
        if gap_ahead < SAFE_DISTANCE:
            desired = 0.0
        elif gap_ahead < BRAKE_DISTANCE:
            ratio = (gap_ahead - SAFE_DISTANCE) / (BRAKE_DISTANCE - SAFE_DISTANCE)
            desired = min(desired, v.max_speed * max(0.0, ratio))

        # Véhicule en sens inverse sur le même tronçon physique
        oncoming = self._dist_to_oncoming(v)
        if oncoming < ONCOMING_SAFE:
            desired = 0.0
        elif oncoming < ONCOMING_SLOW:
            ratio = (oncoming - ONCOMING_SAFE) / (ONCOMING_SLOW - ONCOMING_SAFE)
            desired = min(desired, v.max_speed * max(0.15, ratio))

        # Priorité à l'intersection
        should_yield = self._must_yield(v, target_nid, dist_to_target)
        if should_yield:
            desired = 0.0

        # Freinage approche feu (orange/rouge) ou stop line
        if self.light_manager.has_light(target_nid):
            state_light = self.light_manager.get_state(target_nid)
            if state_light in (LightState.RED, LightState.YELLOW):
                if dist_to_target <= LIGHT_BRAKE_DIST:
                    # Freinage proportionnel : on veut être à vitesse nulle à STOP_LINE_DIST
                    brake_ratio = max(0.0,
                        (dist_to_target - STOP_LINE_DIST) /
                        max(1.0, LIGHT_BRAKE_DIST - STOP_LINE_DIST)
                    )
                    desired = min(desired, v.max_speed * brake_ratio)

        # Mise à jour de l'état
        if desired <= 0.0:
            v.state = VehicleState.STOPPED
        elif desired < v.max_speed * 0.95:
            v.state = VehicleState.BRAKING
        else:
            v.state = VehicleState.MOVING


        if v.speed < desired:
            v.speed = min(desired, v.speed + MAX_ACCEL * dt)
        elif v.speed > desired:
            v.speed = max(desired, v.speed - MAX_DECEL * dt)

        if v.speed <= MIN_SPEED and desired <= MIN_SPEED:
            v.speed = 0.0
            v.state = VehicleState.STOPPED
            return

        # Déplacement
        move = v.speed * dt

        if dist_to_target <= move + 0.5:
            # Nœud atteint : on se téléporte dessus pour éviter le dépassement
            v.lat        = target_node.lat
            v.lon        = target_node.lon
            v.path_index += 1

            if v.path_index >= len(v.path):
                v.state = VehicleState.ARRIVED
                return

            self._init_segment(v)
            v.state = VehicleState.MOVING
        else:

            ratio   = move / dist_to_target
            v.lat  += (target_node.lat - v.lat) * ratio
            v.lon  += (target_node.lon - v.lon) * ratio

    #  Gestion des feux

    def _check_traffic_light(self, v: Vehicle, target_nid: int,
                              dist: float) -> bool:
        """
        Retourne True si le véhicule doit s'arrêter pour un feu rouge/orange.

        """
        if not self.light_manager.has_light(target_nid):
            return False

        state = self.light_manager.get_state(target_nid)
        if state not in (LightState.RED, LightState.YELLOW):
            return False

        if dist <= STOP_LINE_DIST:
            if not v.waiting_at_light:
                # Premier frame d'arrêt : on enregistre dans les stats
                self.light_manager.record_vehicle_waiting(target_nid)
            v.waiting_at_light = True
            return True

        return False

    # Car-following : gap au leader

    def _gap_to_leader(self, v: Vehicle, target_nid: int,
                       my_dist: float) -> float:
        """
        Retourne la distance (mètres) au véhicule le plus proche DEVANT v.

        """
        best = math.inf

        # Vecteur de déplacement de v (seg_from → seg_to) pour le cône avant
        v_fn = self.graph.nodes.get(v.seg_from)
        v_tn = self.graph.nodes.get(v.seg_to)
        v_has_dir = (v_fn is not None and v_tn is not None
                     and v.seg_from != -1 and v.seg_to != -1)
        if v_has_dir:
            vdx = v_tn.lat - v_fn.lat
            vdy = v_tn.lon - v_fn.lon
            v_norm = math.sqrt(vdx * vdx + vdy * vdy)
            if v_norm > 0:
                vdx /= v_norm
                vdy /= v_norm
            else:
                v_has_dir = False

        target_node = self.graph.nodes.get(target_nid)

        for other in self.vehicles.values():
            if other.vehicle_id == v.vehicle_id:
                continue
            if other.state == VehicleState.ARRIVED:
                continue
            if other.path_index >= len(other.path):
                continue

            other_next = other.path[other.path_index]

            # même segment, autre toujours sur ce segment
            if other_next == target_nid and other.seg_from == v.seg_from:
                if target_node is None:
                    continue
                other_dist = haversine(other.lat, other.lon,
                                       target_node.lat, target_node.lon)
                if other_dist < my_dist:
                    gap = my_dist - other_dist
                    best = min(best, gap)
                else:
                    # Sécurité : physiquement très proche (ex: stoppé au feu)
                    direct = haversine(v.lat, v.lon, other.lat, other.lon)
                    if direct < SAFE_DISTANCE:
                        best = min(best, direct)
                continue

            # transition de segment
            # other vient de franchir target_nid ce tick :
            # son path_index a avancé, donc other_next != target_nid,
            # mais son seg_from == target_nid → il est physiquement juste
            # après le nœud, devant v qui n'y est pas encore.
            if other.seg_from == target_nid:
                direct = haversine(v.lat, v.lon, other.lat, other.lon)
                if direct < BRAKE_DISTANCE:
                    best = min(best, direct)
                continue


            # Deux véhicules de rues différentes visent le même nœud.

            if other_next == target_nid and other.seg_from != v.seg_from:
                direct = haversine(v.lat, v.lon, other.lat, other.lon)
                if direct >= BRAKE_DISTANCE:
                    continue

                # Test du cône avant : l'autre est-il devant v ?
                if v_has_dir:
                    odx = other.lat - v.lat
                    ody = other.lon - v.lon
                    dot = odx * vdx + ody * vdy
                    if dot <= 0:
                        # L'autre est derrière ou sur le côté → on ignore
                        continue

                # L'autre est devant, dans une rue différente, proche → on freine
                best = min(best, direct)

        return best

    #Sens inverse

    def _dist_to_oncoming(self, v):
        """
        Retourne la distance au véhicule le plus proche circulant en SENS INVERSE
        sur le même tronçon physique.

        Détection : v va seg_from→seg_to.
        Un véhicule inverse va seg_to→seg_from.
        """
        if v.seg_from == -1 or v.seg_to == -1:
            return math.inf

        best = math.inf
        for other in self.vehicles.values():
            if other.vehicle_id == v.vehicle_id:
                continue
            if other.state == VehicleState.ARRIVED:
                continue
            # Détection sens inverse exact
            if other.seg_from == v.seg_to and other.seg_to == v.seg_from:
                d = haversine(v.lat, v.lon, other.lat, other.lon)
                best = min(best, d)

        return best

    # Priorité à l'intersection

    def _must_yield(self, v, inter_nid, dist_to_inter) -> bool:
        """
        Priorité à droite .
        """
        # On n'applique pas la priorité si le nœud a déjà un feu
        if self.light_manager.has_light(inter_nid):
            return False

        # On n'applique que si on approche vraiment du carrefour
        if dist_to_inter > INTER_YIELD_DIST:
            return False

        # Le nœud doit être une vraie intersection (≥ 3 arcs sortants)
        outgoing = self.graph.edges.get(inter_nid, [])
        if len(outgoing) < 3:
            return False

        # Cap de v : vecteur seg_from → seg_to (en degrés, 0 = nord, sens horaire)
        my_bearing = self._bearing(v.seg_from, v.seg_to)
        if my_bearing is None:
            return False

        inter_node = self.graph.nodes.get(inter_nid)
        if inter_node is None:
            return False

        for other in self.vehicles.values():
            if other.vehicle_id == v.vehicle_id:
                continue
            if other.state == VehicleState.ARRIVED:
                continue
            if other.path_index >= len(other.path):
                continue
            if other.path[other.path_index] != inter_nid:
                continue   # L'autre ne va pas au même carrefour

            # Distance de l'autre au carrefour
            other_dist = haversine(other.lat, other.lon,
                                   inter_node.lat, inter_node.lon)

            # L'autre n'est pertinent que s'il est aussi proche
            if other_dist > INTER_YIELD_DIST:
                continue

            # Cap de l'autre véhicule
            other_bearing = self._bearing(other.seg_from, other.seg_to)
            if other_bearing is None:
                continue

            # Angle relatif : positif = l'autre est à droite de v
            rel_angle = (other_bearing - my_bearing) % 360

            # "À droite" = entre 45° et 135° dans le sens horaire
            if 45 <= rel_angle <= 135:
                # L'autre est à droite ET plus proche de l'intersection → on cède
                if other_dist < dist_to_inter:
                    return True

        return False

    def _bearing(self, from_nid, to_nid) :
        fn = self.graph.nodes.get(from_nid)
        tn = self.graph.nodes.get(to_nid)
        if fn is None or tn is None:
            return None

        dlat = tn.lat - fn.lat
        dlon = tn.lon - fn.lon


        mid_lat = math.radians((fn.lat + tn.lat) / 2)
        dlon_m  = dlon * math.cos(mid_lat)

        bearing = math.degrees(math.atan2(dlon_m, dlat)) % 360
        return bearing

    #  Initialisation d'un segment

    def _init_segment(self, v) :
        """
        Met à jour max_speed, segment_length, seg_from et seg_to
        pour le segment courant du véhicule.
        """
        if v.path_index >= len(v.path):
            return

        curr = v.path[v.path_index - 1] if v.path_index > 0 else v.path[0]
        nxt  = v.path[v.path_index]

        v.seg_from = curr
        v.seg_to   = nxt

        edge = None
        for e in self.graph.edges.get(curr, []):
            if e.to_node == nxt:
                edge = e
                break

        if edge:
            v.max_speed      = edge.speed_limit
            v.segment_length = edge.distance
        else:
            v.max_speed = 11.1
            cn = self.graph.nodes.get(curr)
            nn = self.graph.nodes.get(nxt)
            if cn and nn:
                v.segment_length = haversine(cn.lat, cn.lon, nn.lat, nn.lon)
            else:
                v.segment_length = 10.0

    # check_collisions

    def check_collisions(self):
        collisions = []
        vlist = [v for v in self.vehicles.values()
                 if v.state not in (VehicleState.ARRIVED, VehicleState.NO_PATH)]

        for i in range(len(vlist)):
            for j in range(i + 1, len(vlist)):
                v1, v2 = vlist[i], vlist[j]
                dist = haversine(v1.lat, v1.lon, v2.lat, v2.lon)
                if dist >= COLLISION_DIST:
                    continue

                collisions.append((v1.vehicle_id, v2.vehicle_id))


                is_oncoming = (
                    v1.seg_from != -1 and v1.seg_to != -1 and
                    v1.seg_from == v2.seg_to and v1.seg_to == v2.seg_from
                )

                if is_oncoming:
                    v1.speed = 0.0; v1.state = VehicleState.STOPPED
                    v2.speed = 0.0; v2.state = VehicleState.STOPPED
                    self._push_back(v1)
                    self._push_back(v2)
                    continue

                # Même sens : identifier qui est derrière
                t1 = v1.path[v1.path_index] if v1.path_index < len(v1.path) else -1
                t2 = v2.path[v2.path_index] if v2.path_index < len(v2.path) else -1

                if t1 == t2 and t1 != -1:
                    n = self.graph.nodes.get(t1)
                    if n:
                        d1 = haversine(v1.lat, v1.lon, n.lat, n.lon)
                        d2 = haversine(v2.lat, v2.lon, n.lat, n.lon)
                        # Plus loin du nœud cible = derrière → s'arrête
                        if d1 > d2:
                            v1.speed = 0.0; v1.state = VehicleState.STOPPED
                        else:
                            v2.speed = 0.0; v2.state = VehicleState.STOPPED
                        continue

                # Cas générique
                v1.speed = 0.0; v1.state = VehicleState.STOPPED
                v2.speed = 0.0; v2.state = VehicleState.STOPPED

        return collisions

    def _push_back(self, v: Vehicle) -> None:
        """
        Recule v de 3m vers son nœud d'origine de segment pour
        défaire un blocage face-à-face.
        """
        if v.seg_from == -1:
            return
        origin = self.graph.nodes.get(v.seg_from)
        if origin is None:
            return
        d = haversine(v.lat, v.lon, origin.lat, origin.lon)
        if d < 0.5:
            return
        push  = min(3.0, d * 0.5)
        ratio = push / d
        v.lat += (origin.lat - v.lat) * ratio
        v.lon += (origin.lon - v.lon) * ratio

    # Position de spawn libre

    def _spawn_free(self, new_v):
        for other in self.vehicles.values():
            if other.vehicle_id == new_v.vehicle_id:
                continue
            if other.state == VehicleState.ARRIVED:
                continue
            if haversine(new_v.lat, new_v.lon, other.lat, other.lon) < SAFE_DISTANCE:
                return False
        return True



    def get_vehicle_list(self) -> List[Vehicle]:
        return list(self.vehicles.values())

    def get_active_count(self) -> int:
        return len(self.vehicles)

    def get_stats(self) -> dict:
        moving  = sum(1 for v in self.vehicles.values() if v.state == VehicleState.MOVING)
        stopped = sum(1 for v in self.vehicles.values() if v.state == VehicleState.STOPPED)
        braking = sum(1 for v in self.vehicles.values() if v.state == VehicleState.BRAKING)
        waiting = sum(1 for v in self.vehicles.values() if v.waiting_at_light)
        return {
            "total":    self.get_active_count(),
            "moving":   moving,
            "stopped":  stopped,
            "braking":  braking,
            "at_light": waiting,
            "arrived":  self.total_arrived,
            "spawned":  self.total_spawned,
        }
