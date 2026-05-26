"""Déplacement des véhicules et règles de distance.

Chaque vehicule regarde le vehicule devant lui : il freine quand le
gap descend sous BRAKE_DISTANCE et garde toujours au moins SAFE_GAP
de marge. On y ajoute l'approche prudente d'un feu rouge a moins de
LIGHT_BRAKE_DIST metres, et un controle de capacite du segment
suivant (RECEIVING_SEGMENT_FILL_RATIO) pour ne pas pousser une
voiture dans un segment deja sature.
"""

import math
from typing import Dict, List, Tuple

from simulation.graph import haversine
from simulation.lights import LightState
from simulation.vehicle_constants import (
    BRAKE_DISTANCE,
    LIGHT_BRAKE_DIST,
    M_PER_DEG_LAT,
    M_PER_DEG_LON,
    MIN_SPEED,
    QUEUE_SLOT,
    RECEIVING_SEGMENT_FILL_RATIO,
    SAFE_GAP,
    STOP_LINE_DIST,
    VEHICLE_LENGTH,
)
from simulation.vehicle_geometry import _dot_to_other_meters, _seg_dir_meters
from simulation.vehicle_model import Vehicle, VehicleState


class VehicleMotionMixin:
    """Mixin du VehicleManager pour le modele de suivi et l'approche feux."""

    def _gap_to_leader(self, v: Vehicle, target_nid: int,
                       my_dist: float) -> float:
        """Distance au vehicule de devant le plus proche.

        On scanne le segment courant et le segment suivant. Si aucun
        leader n'est trouve, on retourne math.inf, ce qui signifie
        "plein gaz autorise".
        """
        best = math.inf
        target_node = self.graph.nodes.get(target_nid)
        fn_node = self.graph.nodes.get(v.seg_from)
        tn_node = self.graph.nodes.get(v.seg_to)
        ux, uy, has_dir = _seg_dir_meters(fn_node, tn_node)
        next_nid = (v.path[v.path_index + 1]
                    if v.path_index + 1 < len(v.path) else -1)

        for other in self.vehicles.values():
            if other.vehicle_id == v.vehicle_id:
                continue
            if other.state in (VehicleState.ARRIVED, VehicleState.NO_PATH):
                continue

            if other.seg_from == v.seg_from and other.seg_to == v.seg_to:
                if target_node is None:
                    continue
                od = haversine(other.lat, other.lon,
                               target_node.lat, target_node.lon)
                same_place_leader = (
                    abs(od - my_dist) <= 0.1
                    and other.vehicle_id < v.vehicle_id
                )
                if od < my_dist - 0.1 or same_place_leader:
                    best = min(best, max(0.0, my_dist - od - VEHICLE_LENGTH))
                continue

            if (next_nid != -1
                    and other.seg_from == target_nid
                    and other.seg_to == next_nid
                    and has_dir):
                d = haversine(v.lat, v.lon, other.lat, other.lon)
                if d < BRAKE_DISTANCE:
                    if _dot_to_other_meters(v, other, ux, uy) > 0:
                        best = min(best, max(0.0, d - VEHICLE_LENGTH))
                continue

            if (next_nid != -1
                    and other.seg_from == target_nid
                    and other.seg_to == next_nid
                    and other.speed < 1.0):
                d = haversine(v.lat, v.lon, other.lat, other.lon)
                if d < BRAKE_DISTANCE * 1.5:
                    best = min(best, max(0.0, d - VEHICLE_LENGTH))

        return best

    def _light_approach_speed(self, v: Vehicle) -> float:
        """Calcule la vitesse cible a l approche du prochain feu."""
        for lookahead in range(3):
            idx = v.path_index + lookahead
            if idx >= len(v.path):
                break
            nid = v.path[idx]
            if v.queue_light_node == nid:
                break

            from_nid = v.seg_from if lookahead == 0 else v.path[idx - 1]

            light = self._light_for_approach(nid, from_nid)
            if light is None:
                continue
            if light.state == LightState.GREEN:
                continue

            node = self.graph.nodes.get(nid)
            if node is None:
                continue
            d = self._path_distance_to_index(v, idx)
            if d > LIGHT_BRAKE_DIST:
                continue
            eff = max(0.0, d - STOP_LINE_DIST)
            ratio = eff / max(1.0, LIGHT_BRAKE_DIST - STOP_LINE_DIST)
            return v.max_speed * ratio

        return v.max_speed

    def _light_for_approach(self, node_id: int, from_node: int):
        """Retrouve le feu qui controle une approche donnee."""
        if from_node == -1:
            return None
        light = self.light_manager.get_light(node_id)
        if light is None:
            return None
        if not light.is_approached_from(from_node):
            return None
        return light

    def _path_distance_to_index(self, v: Vehicle, target_index: int) -> float:
        """Mesure la distance restante jusqu a un noeud plus loin dans le trajet."""
        if target_index < v.path_index or target_index >= len(v.path):
            return math.inf

        first_node = self.graph.nodes.get(v.path[v.path_index])
        if first_node is None:
            return math.inf

        total = haversine(v.lat, v.lon, first_node.lat, first_node.lon)
        for idx in range(v.path_index, target_index):
            a = self.graph.nodes.get(v.path[idx])
            b = self.graph.nodes.get(v.path[idx + 1])
            if a is None or b is None:
                return math.inf
            total += haversine(a.lat, a.lon, b.lat, b.lon)
        return total

    def _red_light_stop_guard(self, v: Vehicle, target_nid: int,
                              dist: float, dt: float) -> bool:
        """Empeche un vehicule de depasser la ligne d arret au feu rouge."""
        if v.queue_light_node != -1:
            return False
        if v.seg_to != target_nid:
            return False

        light = self._light_for_approach(target_nid, v.seg_from)
        if light is None or light.state == LightState.GREEN:
            return False

        if dist <= STOP_LINE_DIST + 0.5:
            self._place_on_current_segment(v, STOP_LINE_DIST)
            v.speed = 0.0
            v.state = VehicleState.STOPPED
            return True

        move = v.speed * dt
        max_move_before_line = max(0.0, dist - STOP_LINE_DIST)
        if move >= max_move_before_line:
            self._place_on_current_segment(v, STOP_LINE_DIST)
            v.speed = 0.0
            v.state = VehicleState.STOPPED
            return True

        return False

    def _move_vehicle(self, v: Vehicle, target_node,
                      dist: float, dt: float) -> Tuple[float, bool]:
        """Avance le vehicule sur son segment et bascule au segment suivant si possible."""
        move = v.speed * dt
        if move <= 0.0:
            return dt, False
        if dist <= move + 0.1:
            used_dt = 1e-6 if dist <= 0.1 else dist / max(v.speed, 1e-6)
            used_dt = min(dt, max(used_dt, 1e-6))
            if not self._next_segment_has_space(v):
                if v.reserved_node == v.seg_to:
                    self._token_release(v)
                self._place_on_current_segment(v, STOP_LINE_DIST)
                v.speed = 0.0
                v.state = VehicleState.STOPPED
                return dt, False
            if v.reserved_node == v.seg_to:
                self._token_release(v)
            v.lat = target_node.lat
            v.lon = target_node.lon
            v.path_index += 1
            if v.path_index >= len(v.path):
                v.state = VehicleState.ARRIVED
                return used_dt, True
            self._init_segment(v)
            v.state = VehicleState.MOVING
            return used_dt, True

        r = move / dist
        v.lat += (target_node.lat - v.lat) * r
        v.lon += (target_node.lon - v.lon) * r
        return dt, False

    def _next_segment_has_space(self, v: Vehicle) -> bool:
        """Verifie que le segment suivant peut recevoir le vehicule."""
        if v.path_index + 1 >= len(v.path):
            return True

        next_from = v.seg_to
        next_to = v.path[v.path_index + 1]
        origin_node = self.graph.nodes.get(next_from)
        target_node = self.graph.nodes.get(next_to)
        if origin_node is None or target_node is None:
            return True

        seg_len = haversine(origin_node.lat, origin_node.lon,
                            target_node.lat, target_node.lon)
        if seg_len < 1e-6:
            return True

        occupants: List[Tuple[float, Vehicle]] = []
        closest_from_origin = math.inf
        for other in self.vehicles.values():
            if other.vehicle_id == v.vehicle_id:
                continue
            if other.state in (VehicleState.ARRIVED, VehicleState.NO_PATH):
                continue
            if other.seg_from != next_from or other.seg_to != next_to:
                continue
            d = haversine(other.lat, other.lon,
                          origin_node.lat, origin_node.lon)
            closest_from_origin = min(closest_from_origin, d)
            occupants.append((d, other))

        if closest_from_origin == math.inf:
            return True
        if closest_from_origin < QUEUE_SLOT:
            return False

        usable_len = max(QUEUE_SLOT, seg_len - STOP_LINE_DIST)
        capacity = max(1, int(usable_len / QUEUE_SLOT))
        max_occupants = max(1, math.ceil(capacity * RECEIVING_SEGMENT_FILL_RATIO))
        if len(occupants) >= max_occupants:
            return False

        near_entry_limit = min(seg_len, QUEUE_SLOT * 2.0)
        for d, other in occupants:
            if d <= near_entry_limit and other.speed < 1.0:
                return False

        return True

    def _resolve_same_segment_overlaps(self) -> None:
        """Separe les vehicules trop proches sur un meme segment."""
        groups: Dict[Tuple[int, int], List[Vehicle]] = {}
        for v in self.vehicles.values():
            if v.state in (VehicleState.ARRIVED, VehicleState.NO_PATH):
                continue
            if v.seg_from == -1 or v.seg_to == -1:
                continue
            groups.setdefault((v.seg_from, v.seg_to), []).append(v)

        for (_, seg_to), cars in groups.items():
            if len(cars) < 2:
                continue
            target_node = self.graph.nodes.get(seg_to)
            if target_node is None:
                continue

            cars.sort(key=lambda car: (
                haversine(car.lat, car.lon, target_node.lat, target_node.lon),
                car.vehicle_id,
            ))

            prev_dist = haversine(cars[0].lat, cars[0].lon,
                                  target_node.lat, target_node.lon)
            prev_speed = cars[0].speed

            for car in cars[1:]:
                car_dist = haversine(car.lat, car.lon,
                                     target_node.lat, target_node.lon)
                min_dist = prev_dist + QUEUE_SLOT
                if car_dist < min_dist:
                    car_dist = self._place_on_current_segment(car, min_dist)
                    car.speed = min(car.speed, prev_speed)
                    if car.speed <= MIN_SPEED:
                        car.speed = 0.0
                        car.state = VehicleState.STOPPED
                    else:
                        car.state = VehicleState.BRAKING

                prev_dist = max(prev_dist, car_dist)
                prev_speed = car.speed

    def _resolve_adjacent_segment_overlaps(self) -> None:
        """Evite les chevauchements au passage entre deux segments voisins."""
        by_segment: Dict[Tuple[int, int], List[Vehicle]] = {}
        for v in self.vehicles.values():
            if v.state in (VehicleState.ARRIVED, VehicleState.NO_PATH):
                continue
            if v.seg_from == -1 or v.seg_to == -1:
                continue
            by_segment.setdefault((v.seg_from, v.seg_to), []).append(v)

        for follower in self.vehicles.values():
            if follower.state in (VehicleState.ARRIVED, VehicleState.NO_PATH):
                continue
            if follower.path_index + 1 >= len(follower.path):
                continue

            shared_node = follower.seg_to
            next_node = follower.path[follower.path_index + 1]
            shared = self.graph.nodes.get(shared_node)
            if shared is None:
                continue

            best_leader_dist = math.inf
            best_leader_speed = follower.speed
            for leader in by_segment.get((shared_node, next_node), []):
                if leader.vehicle_id == follower.vehicle_id:
                    continue

                leader_dist = haversine(leader.lat, leader.lon,
                                        shared.lat, shared.lon)
                if leader_dist < best_leader_dist:
                    best_leader_dist = leader_dist
                    best_leader_speed = leader.speed

            if best_leader_dist == math.inf:
                continue

            follower_dist = haversine(follower.lat, follower.lon,
                                      shared.lat, shared.lon)
            path_gap = follower_dist + best_leader_dist
            if path_gap >= QUEUE_SLOT:
                continue

            target_dist = QUEUE_SLOT - best_leader_dist
            self._place_on_current_segment(follower, target_dist)
            follower.speed = min(follower.speed, best_leader_speed)
            if follower.speed <= MIN_SPEED:
                follower.speed = 0.0
                follower.state = VehicleState.STOPPED
            else:
                follower.state = VehicleState.BRAKING

    def _place_on_current_segment(self, v: Vehicle,
                                  target_dist: float) -> float:
        """Replace un vehicule a une distance precise de la fin du segment."""
        target_node = self.graph.nodes.get(v.seg_to)
        origin_node = self.graph.nodes.get(v.seg_from)
        if target_node is None or origin_node is None:
            return target_dist

        seg_len = haversine(origin_node.lat, origin_node.lon,
                            target_node.lat, target_node.lon)
        if seg_len < 1e-6:
            return target_dist

        ux, uy, ok = _seg_dir_meters(origin_node, target_node)
        if not ok:
            return target_dist

        upper = max(0.5, seg_len - 0.5)
        d = max(0.5, min(target_dist, upper))
        v.lat = target_node.lat - uy * (d / M_PER_DEG_LAT)
        v.lon = target_node.lon - ux * (d / M_PER_DEG_LON)
        return d

    def _init_segment(self, v: Vehicle) -> None:
        """Charge dans le vehicule les informations du segment courant."""
        if v.path_index >= len(v.path):
            return
        curr = v.path[v.path_index - 1] if v.path_index > 0 else v.path[0]
        nxt = v.path[v.path_index]
        v.seg_from = curr
        v.seg_to = nxt

        edge = next((e for e in self.graph.edges.get(curr, [])
                     if e.to_node == nxt), None)
        if edge:
            v.max_speed = edge.speed_limit
            v.segment_length = edge.distance
            v.seg_road_id = edge.road_id
            v.seg_oneway = self._road_oneway.get(edge.road_id, False)
        else:
            cn = self.graph.nodes.get(curr)
            nn = self.graph.nodes.get(nxt)
            v.max_speed = 11.1
            v.seg_road_id = -1
            v.seg_oneway = False
            v.segment_length = (haversine(cn.lat, cn.lon, nn.lat, nn.lon)
                                if cn and nn else 10.0)

    def _spawn_free(self, new_v: Vehicle) -> bool:
        """Verifie qu'un nouveau vehicule peut apparaitre sans collision."""
        for other in self.vehicles.values():
            if other.vehicle_id == new_v.vehicle_id:
                continue
            if other.state in (VehicleState.ARRIVED, VehicleState.NO_PATH):
                continue
            if haversine(new_v.lat, new_v.lon,
                         other.lat, other.lon) < SAFE_GAP * 2.0:
                return False
        return True
