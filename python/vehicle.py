"""Gestion des véhicules, des files et des priorités de circulation."""

import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Set, Tuple

from graph import RoadGraph, haversine
from traffic_light_manager import TrafficLightManager, LightState


# Constantes physiques

VEHICLE_LENGTH   = 4.5
SAFE_GAP         = 5.0
BRAKE_DISTANCE   = 35.0

QUEUE_SLOT       = VEHICLE_LENGTH + 2.0
QUEUE_JOIN_DIST  = 80.0
STOP_LINE_DIST   = 4.0
LIGHT_BRAKE_DIST = 50.0

INTER_RESERVE_DIST  = 20.0
INTER_CLEAR_DIST    =  3.0
INTER_YIELD_TIMEOUT =  8.0

MAX_ACCEL        = 2.5
MAX_DECEL        = 5.5
MIN_SPEED        = 0.1

MAX_SEGS_PER_TICK = 5

QUEUE_RELEASE_COOLDOWN = 2.0

CONGESTION_VEHICLE_PENALTY = 2.0
CONGESTION_BRAKING_PENALTY = 4.0
CONGESTION_STOPPED_PENALTY = 7.0
CONGESTION_QUEUE_PENALTY   = 6.0
CONGESTION_ROAD_FACTOR     = 0.25

RECEIVING_SEGMENT_FILL_RATIO = 0.85

# Conversion GPS vers mètres locaux (Paris, latitude moyenne 48.85).
M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(48.85))


# États véhicule

class VehicleState(Enum):
    MOVING  = auto()
    BRAKING = auto()
    STOPPED = auto()
    ARRIVED = auto()
    NO_PATH = auto()


# Données d'un véhicule.

@dataclass
class Vehicle:
    vehicle_id:  int
    origin_node: int
    dest_node:   int

    path:        List[int] = field(default_factory=list)
    path_index:  int       = 0

    lat:            float = 0.0
    lon:            float = 0.0
    speed:          float = 0.0
    max_speed:      float = 11.1
    segment_length: float = 0.0

    state:       VehicleState         = VehicleState.STOPPED
    color:       Tuple[int, int, int] = (255, 200, 0)
    travel_time: float                = 0.0

    waiting_at_light: bool = False

    seg_from:    int  = -1
    seg_to:      int  = -1
    seg_road_id: int  = -1
    seg_oneway:  bool = False

    queue_light_node:    int   = -1
    queue_index:         int   = -1
    queue_seg_from:      int   = -1
    queue_release_timer: float = 0.0
    queue_cooldown:      float = 0.0

    reserved_node: int   = -1
    yield_timer:   float = 0.0


# Utilitaires géométriques.

def _seg_dir_meters(fn, tn) -> Tuple[float, float, bool]:
    """
    Vecteur unitaire (ux, uy) en mètres métriques du segment fn→tn.
    ux = composante Est (lon), uy = composante Nord (lat).
    """
    if fn is None or tn is None:
        return 0.0, 0.0, False
    dx = (tn.lon - fn.lon) * M_PER_DEG_LON
    dy = (tn.lat - fn.lat) * M_PER_DEG_LAT
    n  = math.sqrt(dx * dx + dy * dy)
    if n < 1e-6:
        return 0.0, 0.0, False
    return dx / n, dy / n, True


def _dot_to_other_meters(v: "Vehicle", other: "Vehicle",
                          ux: float, uy: float) -> float:
    """
    Produit scalaire (vecteur v→other en mètres) · (ux, uy).
    > 0  ⟺  other est dans la direction (ux,uy) par rapport à v.
    """
    dx = (other.lon - v.lon) * M_PER_DEG_LON
    dy = (other.lat - v.lat) * M_PER_DEG_LAT
    return dx * ux + dy * uy


def _speed_for_gap(gap: float, max_speed: float) -> float:
    if gap <= SAFE_GAP:
        return 0.0
    if gap >= BRAKE_DISTANCE:
        return max_speed
    return max_speed * (gap - SAFE_GAP) / (BRAKE_DISTANCE - SAFE_GAP)


def _apply_speed(v: "Vehicle", desired: float, dt: float) -> None:
    if desired <= 0.0:
        v.speed = max(0.0, v.speed - MAX_DECEL * dt)
        if v.speed < MIN_SPEED:
            v.speed = 0.0
            v.state = VehicleState.STOPPED
        else:
            v.state = VehicleState.BRAKING
    elif v.speed < desired:
        v.speed = min(desired, v.speed + MAX_ACCEL * dt)
        v.state = VehicleState.MOVING
    elif v.speed > desired:
        v.speed = max(desired, v.speed - MAX_DECEL * dt)
        v.state = VehicleState.BRAKING
    else:
        v.state = VehicleState.MOVING


# VehicleManager

class VehicleManager:

    def __init__(self, graph: RoadGraph, light_manager: TrafficLightManager,
                 rng: Optional[random.Random] = None):
        self.graph         = graph
        self.light_manager = light_manager
        self.rng           = rng or random.Random(0)

        self.vehicles:      Dict[int, Vehicle]                 = {}
        self._next_id:      int                                = 0
        self.total_arrived: int                                = 0
        self.total_spawned: int                                = 0

        self._road_oneway:    Dict[int, bool]                  = {}
        self._queues:         Dict[Tuple[int, int], List[int]] = {}
        self._node_tokens:    Dict[int, Set[int]]              = {}
        self._incoming_cache: Optional[Dict[int, Set[int]]]    = None

    # Construction

    def build_edge_index(self) -> None:
        existing: Set[Tuple[int, int, int]] = set()
        road_fwd: Dict[int, List[Tuple[int, int]]] = {}

        for edges_list in self.graph.edges.values():
            for e in edges_list:
                existing.add((e.road_id, e.from_node, e.to_node))
                road_fwd.setdefault(e.road_id, []).append((e.from_node, e.to_node))

        for rid, pairs in road_fwd.items():
            self._road_oneway[rid] = all(
                (rid, tn, fn) not in existing for (fn, tn) in pairs
            )

        self._incoming_cache = {}
        for from_nid, edges in self.graph.edges.items():
            for e in edges:
                self._incoming_cache.setdefault(e.to_node, set()).add(from_nid)

        ow = sum(1 for v in self._road_oneway.values() if v)
        tw = len(self._road_oneway) - ow
        print(f"[VehicleManager] {ow} routes sens unique, {tw} double sens")

    # Spawn

    def spawn_vehicle(self,
                      origin_node: Optional[int] = None,
                      dest_node:   Optional[int] = None) -> Optional[Vehicle]:
        pool = self.graph.get_spawn_nodes()
        if len(pool) < 2:
            return None

        for _ in range(20):
            o = origin_node or self.rng.choice(pool)
            d = dest_node   or self.rng.choice(pool)
            if o != d:
                break
        else:
            return None

        path = self.graph.dijkstra(o, d, self._make_congestion_penalty())
        if not path or len(path) < 2:
            return None

        on = self.graph.nodes.get(o)
        if on is None:
            return None

        vid = self._next_id
        self._next_id += 1

        color = (self.rng.randint(180, 255),
                 self.rng.randint(100, 200),
                 self.rng.randint(0, 80))

        v = Vehicle(vehicle_id=vid, origin_node=o, dest_node=d,
                    path=path, path_index=1,
                    lat=on.lat, lon=on.lon,
                    speed=0.0, color=color,
                    state=VehicleState.MOVING)
        self._init_segment(v)

        self.vehicles[vid] = v
        if not self._spawn_free(v):
            del self.vehicles[vid]
            return None

        self.total_spawned += 1
        return v

    def spawn_batch(self, count: int) -> int:
        ok = 0
        for _ in range(count):
            if self.spawn_vehicle() is not None:
                ok += 1
        return ok

    def _make_congestion_penalty(self):
        edge_penalties: Dict[Tuple[int, int], float] = {}
        road_penalties: Dict[int, float] = {}

        for vehicle in self.vehicles.values():
            if vehicle.state in (VehicleState.ARRIVED, VehicleState.NO_PATH):
                continue
            if vehicle.seg_from == -1 or vehicle.seg_to == -1:
                continue

            penalty = CONGESTION_VEHICLE_PENALTY
            if vehicle.state == VehicleState.BRAKING:
                penalty += CONGESTION_BRAKING_PENALTY
            elif vehicle.state == VehicleState.STOPPED:
                penalty += CONGESTION_STOPPED_PENALTY
            if vehicle.waiting_at_light:
                penalty += CONGESTION_QUEUE_PENALTY
            if vehicle.speed < 1.0:
                penalty += CONGESTION_BRAKING_PENALTY

            key = (vehicle.seg_from, vehicle.seg_to)
            edge_penalties[key] = edge_penalties.get(key, 0.0) + penalty
            if vehicle.seg_road_id != -1:
                road_penalties[vehicle.seg_road_id] = (
                    road_penalties.get(vehicle.seg_road_id, 0.0)
                    + penalty * CONGESTION_ROAD_FACTOR
                )

        for (light_nid, seg_from), queue in self._queues.items():
            edge_penalties[(seg_from, light_nid)] = (
                edge_penalties.get((seg_from, light_nid), 0.0)
                + len(queue) * CONGESTION_QUEUE_PENALTY
            )

        def penalty(edge) -> float:
            return (
                edge_penalties.get((edge.from_node, edge.to_node), 0.0)
                + road_penalties.get(edge.road_id, 0.0)
            )

        return penalty

    # Boucle principale

    def update(self, dt: float) -> None:
        to_remove = []
        for vid, v in self.vehicles.items():
            if v.state in (VehicleState.ARRIVED, VehicleState.NO_PATH):
                to_remove.append(vid)
                continue
            v.travel_time += dt
            if v.queue_cooldown > 0.0:
                v.queue_cooldown = max(0.0, v.queue_cooldown - dt)
            self._update_vehicle(v, dt)
            if v.state == VehicleState.ARRIVED:
                to_remove.append(vid)
                self.total_arrived += 1

        for vid in to_remove:
            v = self.vehicles.pop(vid)
            self._queue_remove(v)
            self._token_release(v)

        self._resolve_same_segment_overlaps()
        self._resolve_adjacent_segment_overlaps()

    # Mise à jour d'un véhicule avec découpage du pas de temps.

    def _update_vehicle(self, v: Vehicle, dt: float) -> None:
        remaining = dt
        segs = 0
        steps = 0

        while (remaining > 1e-9
               and segs < MAX_SEGS_PER_TICK
               and steps < MAX_SEGS_PER_TICK * 3):
            steps += 1
            if v.state in (VehicleState.ARRIVED, VehicleState.NO_PATH):
                return
            if not v.path or v.path_index >= len(v.path):
                v.state = VehicleState.ARRIVED
                return

            target_nid  = v.path[v.path_index]
            target_node = self.graph.nodes.get(target_nid)
            if target_node is None:
                v.state = VehicleState.ARRIVED
                return

            dist = haversine(v.lat, v.lon, target_node.lat, target_node.lon)

            speed_cap = max(MIN_SPEED, min(v.max_speed,
                            v.speed + MAX_ACCEL * remaining))
            if dist > 0.1:
                step_dt = min(remaining, dist / max(speed_cap, MIN_SPEED))
            else:
                step_dt = remaining
            step_dt = max(1e-6, min(step_dt, remaining))

            prev_idx = v.path_index
            before = remaining
            used_dt, crossed = self._tick(
                v, target_nid, target_node, dist, step_dt)
            remaining -= max(used_dt, 1e-6)

            if not crossed or v.path_index == prev_idx:
                if v.speed <= 0.0 or used_dt >= before - 1e-6:
                    break
                continue
            segs += 1

    def _tick(self, v: Vehicle, target_nid: int,
              target_node, dist: float, dt: float) -> Tuple[float, bool]:

        if self._handle_queue(v, target_nid, dist, dt):
            return dt, False

        desired = v.max_speed
        desired = min(desired, _speed_for_gap(
            self._gap_to_leader(v, target_nid, dist), v.max_speed))
        desired = min(desired, self._light_approach_speed(v))
        desired = min(desired, self._intersection_token_speed(
            v, target_nid, dist, dt))

        _apply_speed(v, desired, dt)
        if self._red_light_stop_guard(v, target_nid, dist, dt):
            return dt, False
        if v.speed <= 0.0:
            return dt, False
        return self._move_vehicle(v, target_node, dist, dt)

    # Distance avec le véhicule devant.

    def _gap_to_leader(self, v: Vehicle, target_nid: int,
                       my_dist: float) -> float:
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

            # Même segment, même sens
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

            # Segment juste après target_nid, dans ma direction.
            if (next_nid != -1
                    and other.seg_from == target_nid
                    and other.seg_to == next_nid
                    and has_dir):
                d = haversine(v.lat, v.lon, other.lat, other.lon)
                if d < BRAKE_DISTANCE:
                    if _dot_to_other_meters(v, other, ux, uy) > 0:
                        best = min(best, max(0.0, d - VEHICLE_LENGTH))
                continue

            # Lookahead : arrêté sur le segment suivant
            if (next_nid != -1
                    and other.seg_from == target_nid
                    and other.seg_to   == next_nid
                    and other.speed    < 1.0):
                d = haversine(v.lat, v.lon, other.lat, other.lon)
                if d < BRAKE_DISTANCE * 1.5:
                    best = min(best, max(0.0, d - VEHICLE_LENGTH))

        return best

    # Freinage anticipé avant feu

    def _light_approach_speed(self, v: Vehicle) -> float:
        for lookahead in range(3):
            idx = v.path_index + lookahead
            if idx >= len(v.path):
                break
            nid = v.path[idx]
            if v.queue_light_node == nid:
                break  # géré par _handle_queue

            from_nid = v.seg_from if lookahead == 0 else v.path[idx - 1]

            light = self._light_for_approach(nid, from_nid)
            if light is None:
                continue
            ls = light.state
            if ls == LightState.GREEN:
                continue

            node = self.graph.nodes.get(nid)
            if node is None:
                continue
            d = self._path_distance_to_index(v, idx)
            if d > LIGHT_BRAKE_DIST:
                continue
            eff   = max(0.0, d - STOP_LINE_DIST)
            ratio = eff / max(1.0, LIGHT_BRAKE_DIST - STOP_LINE_DIST)
            return v.max_speed * ratio

        return v.max_speed

    def _light_for_approach(self, node_id: int, from_node: int):
        if from_node == -1:
            return None
        light = self.light_manager.get_light(node_id)
        if light is None:
            return None
        if not light.is_approached_from(from_node):
            return None
        return light

    def _path_distance_to_index(self, v: Vehicle, target_index: int) -> float:
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

    # Token d'intersection

    def _intersection_token_speed(self, v: Vehicle, target_nid: int,
                                   dist: float, dt: float) -> float:
        if v.queue_light_node != -1:
            return v.max_speed

        incoming = self._get_incoming_sources(target_nid)
        if len(incoming) < 2:
            return v.max_speed
        if not self._is_real_intersection_node(target_nid):
            return v.max_speed

        if dist > INTER_RESERVE_DIST:
            if v.reserved_node == target_nid:
                self._token_release(v)
            v.yield_timer = 0.0
            return v.max_speed

        if not self._approach_allowed_by_light(v, target_nid):
            if v.reserved_node == target_nid:
                self._token_release(v)
            return v.max_speed

        if v.reserved_node == target_nid:
            v.yield_timer = 0.0
            return v.max_speed

        owners = self._active_token_owners(target_nid, v.vehicle_id)
        has_conflict = any(
            self._movements_conflict(v, owner, target_nid)
            for owner in owners
        )

        if not has_conflict and v.yield_timer >= INTER_YIELD_TIMEOUT:
            self._token_acquire(v, target_nid)
            v.yield_timer = 0.0
            return v.max_speed

        if not has_conflict:
            if not self._must_yield_at_intersection(v, target_nid, dist):
                self._token_acquire(v, target_nid)
                v.yield_timer = 0.0
                return v.max_speed

        v.yield_timer += dt
        return self._intersection_yield_speed(v, dist)

    def _intersection_yield_speed(self, v: Vehicle, dist: float) -> float:
        if dist <= INTER_CLEAR_DIST + 0.5:
            return 0.0
        ratio = max(0.0, (dist - INTER_CLEAR_DIST) /
                    max(1.0, INTER_RESERVE_DIST - INTER_CLEAR_DIST))
        return v.max_speed * min(ratio, 0.18)

    def _active_token_owners(self, node_id: int,
                             requester_id: int = -1) -> List[Vehicle]:
        owners = self._node_tokens.get(node_id, set())
        if not owners:
            return []

        active: List[Vehicle] = []
        stale_ids: List[int] = []
        for owner_id in list(owners):
            if owner_id == requester_id:
                continue
            owner = self.vehicles.get(owner_id)
            stale = (
                owner is None
                or owner.state in (VehicleState.ARRIVED, VehicleState.NO_PATH)
                or owner.reserved_node != node_id
                or owner.path_index >= len(owner.path)
                or owner.path[owner.path_index] != node_id
            )
            if stale:
                stale_ids.append(owner_id)
                if owner is not None and owner.reserved_node == node_id:
                    owner.reserved_node = -1
                continue
            active.append(owner)

        for owner_id in stale_ids:
            owners.discard(owner_id)
        if not owners:
            self._node_tokens.pop(node_id, None)
        return active

    def _approach_allowed_by_light(self, v: Vehicle, target_nid: int) -> bool:
        light = self._light_for_approach(target_nid, v.seg_from)
        if light is None:
            return True
        return light.state == LightState.GREEN

    def _must_yield_at_intersection(self, v: Vehicle, target_nid: int,
                                    my_dist: float) -> bool:
        target_node = self.graph.nodes.get(target_nid)
        if target_node is None:
            return False

        my_turn = self._turn_kind(v, target_nid)

        for other in self.vehicles.values():
            if other.vehicle_id == v.vehicle_id:
                continue
            if other.state in (VehicleState.ARRIVED, VehicleState.NO_PATH):
                continue
            if other.queue_light_node != -1:
                continue
            if (other.path_index >= len(other.path)
                    or other.path[other.path_index] != target_nid):
                continue
            if other.seg_from == v.seg_from:
                continue
            if not self._approach_allowed_by_light(other, target_nid):
                continue

            other_dist = haversine(other.lat, other.lon,
                                   target_node.lat, target_node.lon)
            if other_dist > INTER_RESERVE_DIST + QUEUE_SLOT:
                continue

            other_turn = self._turn_kind(other, target_nid)
            if (my_turn == "left"
                    and other_turn in ("straight", "right", "end")
                    and self._is_oncoming_approach(v, other)
                    and other_dist <= my_dist + 8.0):
                return True

            if (self._is_other_on_right(v, other, target_nid)
                    and other_dist <= my_dist + 6.0):
                return True

            if other_dist + 2.0 < my_dist:
                return True

        return False

    def _turn_kind(self, v: Vehicle, target_nid: int) -> str:
        if v.path_index + 1 >= len(v.path):
            return "end"

        from_node = self.graph.nodes.get(v.seg_from)
        inter_node = self.graph.nodes.get(target_nid)
        next_node = self.graph.nodes.get(v.path[v.path_index + 1])
        if from_node is None or inter_node is None or next_node is None:
            return "straight"

        in_ux, in_uy, in_ok = _seg_dir_meters(from_node, inter_node)
        out_ux, out_uy, out_ok = _seg_dir_meters(inter_node, next_node)
        if not in_ok or not out_ok:
            return "straight"

        dot = max(-1.0, min(1.0, in_ux * out_ux + in_uy * out_uy))
        cross = in_ux * out_uy - in_uy * out_ux
        angle = math.degrees(math.atan2(cross, dot))

        if abs(angle) <= 30.0:
            return "straight"
        if angle > 0.0:
            return "left"
        return "right"

    def _is_oncoming_approach(self, v: Vehicle, other: Vehicle) -> bool:
        v_from = self.graph.nodes.get(v.seg_from)
        v_to = self.graph.nodes.get(v.seg_to)
        o_from = self.graph.nodes.get(other.seg_from)
        o_to = self.graph.nodes.get(other.seg_to)
        vux, vuy, vok = _seg_dir_meters(v_from, v_to)
        oux, ouy, ook = _seg_dir_meters(o_from, o_to)
        if not vok or not ook:
            return False
        return (vux * oux + vuy * ouy) <= -0.70

    def _next_after_intersection(self, v: Vehicle) -> int:
        if v.path_index + 1 >= len(v.path):
            return -1
        return v.path[v.path_index + 1]

    def _movements_conflict(self, v: Vehicle, other: Vehicle,
                            target_nid: int) -> bool:
        if other.vehicle_id == v.vehicle_id:
            return False
        if other.seg_from == v.seg_from:
            return False

        my_next = self._next_after_intersection(v)
        other_next = self._next_after_intersection(other)
        if my_next != -1 and my_next == other_next:
            return True

        if self._is_oncoming_approach(v, other):
            my_turn = self._turn_kind(v, target_nid)
            other_turn = self._turn_kind(other, target_nid)
            if my_turn == "left" and other_turn in ("straight", "right", "end"):
                return True
            if other_turn == "left" and my_turn in ("straight", "right", "end"):
                return True
            return False

        return True

    def _is_other_on_right(self, v: Vehicle, other: Vehicle,
                           target_nid: int) -> bool:
        inter_node = self.graph.nodes.get(target_nid)
        from_node = self.graph.nodes.get(v.seg_from)
        to_node = self.graph.nodes.get(v.seg_to)
        if inter_node is None:
            return False

        ux, uy, ok = _seg_dir_meters(from_node, to_node)
        if not ok:
            return False

        ox = (other.lon - inter_node.lon) * M_PER_DEG_LON
        oy = (other.lat - inter_node.lat) * M_PER_DEG_LAT
        norm = math.sqrt(ox * ox + oy * oy)
        if norm < 1e-6:
            return False

        right_x, right_y = uy, -ux
        return ((ox / norm) * right_x + (oy / norm) * right_y
                >= math.cos(math.radians(45.0)))

    def _token_acquire(self, v: Vehicle, node_id: int) -> None:
        if v.reserved_node != -1 and v.reserved_node != node_id:
            owners = self._node_tokens.get(v.reserved_node)
            if owners is not None:
                owners.discard(v.vehicle_id)
                if not owners:
                    del self._node_tokens[v.reserved_node]
        v.reserved_node = node_id
        self._node_tokens.setdefault(node_id, set()).add(v.vehicle_id)

    def _token_release(self, v: Vehicle) -> None:
        if v.reserved_node != -1:
            owners = self._node_tokens.get(v.reserved_node)
            if owners is not None:
                owners.discard(v.vehicle_id)
                if not owners:
                    del self._node_tokens[v.reserved_node]
            v.reserved_node = -1

    def _get_incoming_sources(self, node_id: int) -> Set[int]:
        if self._incoming_cache is None:
            return set()
        return self._incoming_cache.get(node_id, set())

    def _is_real_intersection_node(self, node_id: int) -> bool:
        neighbors = set(self._get_incoming_sources(node_id))
        for edge in self.graph.edges.get(node_id, []):
            neighbors.add(edge.to_node)
        return len(neighbors) >= 3

    # File de feu rouge

    def _handle_queue(self, v: Vehicle, target_nid: int,
                      dist: float, dt: float) -> bool:
        # Déjà en file.
        if v.queue_light_node != -1:
            key = (v.queue_light_node, v.queue_seg_from)
            if v.vehicle_id not in self._queues.get(key, []):
                self._queue_remove(v)
                return False
            ls = self.light_manager.get_state(v.queue_light_node)
            if ls == LightState.GREEN:
                return self._queue_release(v, dt)
            return self._queue_hold(v, dt)

        # Evite une réentrée immédiate dans la file.
        if v.queue_cooldown > 0.0:
            return False

        # Entrée dans une file de feu.
        if not self.light_manager.has_light(target_nid):
            return False
        if v.seg_to != target_nid:
            return False
        if v.seg_from == -1:
            return False
        if dist > QUEUE_JOIN_DIST:
            return False

        light = self.light_manager.get_light(target_nid)
        if light is None:
            return False
        ls = light.state
        if ls not in (LightState.RED, LightState.YELLOW):
            return False
        if not light.is_approached_from(v.seg_from):
            return False

        if not self._queue_join(v, target_nid):
            return False
        return self._queue_hold(v, dt)

    def _queue_join(self, v: Vehicle, light_nid: int) -> bool:
        if v.seg_from == -1:
            return False
        if v.queue_light_node != -1 and v.queue_light_node != light_nid:
            self._queue_remove(v)
        self._token_release(v)   # token + file = incompatible

        captured_seg_from = v.seg_from
        key = (light_nid, captured_seg_from)
        q   = self._queues.setdefault(key, [])
        if v.vehicle_id in q:
            self._queue_compact(key)
            return True

        self._queue_compact(key)
        q = self._queues.setdefault(key, [])
        if not self._queue_slot_fits(light_nid, captured_seg_from, len(q)):
            return False

        v.queue_light_node    = light_nid
        v.queue_index         = -1
        v.queue_seg_from      = captured_seg_from
        v.queue_release_timer = 0.0
        v.waiting_at_light    = True
        q.append(v.vehicle_id)
        self._queue_compact(key)
        self.light_manager.record_vehicle_waiting(light_nid)
        return True

    def _queue_remove(self, v: Vehicle) -> None:
        if v.queue_light_node == -1:
            return
        key = (v.queue_light_node, v.queue_seg_from)
        q   = self._queues.get(key, [])
        if v.vehicle_id in q:
            idx = q.index(v.vehicle_id)
            q.pop(idx)
            for i in range(idx, len(q)):
                ov = self.vehicles.get(q[i])
                if ov:
                    ov.queue_index = i
        v.queue_light_node    = -1
        v.queue_index         = -1
        v.queue_seg_from      = -1
        v.waiting_at_light    = False
        v.queue_release_timer = 0.0
        if not q and key in self._queues:
            del self._queues[key]
        elif q:
            self._queue_compact(key)

    def _queue_compact(self, key: Tuple[int, int]) -> None:
        light_nid, seg_from = key
        light_node = self.graph.nodes.get(light_nid)
        q = self._queues.get(key, [])
        if light_node is None:
            for vid in q:
                ov = self.vehicles.get(vid)
                if ov:
                    ov.queue_light_node = -1
                    ov.queue_index = -1
                    ov.queue_seg_from = -1
                    ov.waiting_at_light = False
            self._queues.pop(key, None)
            return

        live: List[int] = []
        for vid in q:
            ov = self.vehicles.get(vid)
            if ov is None:
                continue
            if ov.queue_light_node != light_nid or ov.queue_seg_from != seg_from:
                continue
            live.append(vid)

        live.sort(key=lambda vid: (
            haversine(self.vehicles[vid].lat, self.vehicles[vid].lon,
                      light_node.lat, light_node.lon),
            vid,
        ))

        if live:
            self._queues[key] = live
            for i, vid in enumerate(live):
                ov = self.vehicles.get(vid)
                if ov:
                    ov.queue_index = i
        else:
            self._queues.pop(key, None)

    def _queue_slot_fits(self, light_nid: int, seg_from: int,
                         slot_index: int) -> bool:
        light_node = self.graph.nodes.get(light_nid)
        origin_node = self.graph.nodes.get(seg_from)
        if light_node is None or origin_node is None:
            return False

        seg_len = haversine(origin_node.lat, origin_node.lon,
                            light_node.lat, light_node.lon)
        target_dist = STOP_LINE_DIST + slot_index * QUEUE_SLOT
        return target_dist <= max(STOP_LINE_DIST, seg_len - 0.5)

    def _queue_hold(self, v: Vehicle, dt: float) -> bool:
        """Maintient la position du véhicule dans sa file."""
        light_nid  = v.queue_light_node
        key        = (light_nid, v.queue_seg_from)
        self._queue_compact(key)
        if v.queue_light_node == -1:
            return False
        k          = v.queue_index
        light_node = self.graph.nodes.get(light_nid)

        if light_node is None:
            self._queue_remove(v)
            return False
        if v.queue_seg_from == -1 or k < 0:
            self._queue_remove(v)
            return False
        if v.vehicle_id not in self._queues.get(key, []):
            self._queue_remove(v)
            return False

        dist_to_light = haversine(v.lat, v.lon,
                                  light_node.lat, light_node.lon)
        target_dist   = STOP_LINE_DIST + k * QUEUE_SLOT
        gap           = dist_to_light - target_dist

        # Arrêt immédiat si la position de file est atteinte.
        if gap <= 0.5 or dist_to_light <= STOP_LINE_DIST + 0.5:
            self._place_at_slot(v, light_nid, target_dist)
            v.speed = 0.0
            v.state = VehicleState.STOPPED
            return True

        v_safe  = math.sqrt(2.0 * MAX_DECEL * max(0.0, gap - 0.5))
        desired = min(v.max_speed * 0.35, v_safe)
        _apply_speed(v, desired, dt)

        if v.speed <= 0.0:
            v.state = VehicleState.STOPPED
            return True

        move = v.speed * dt
        if move >= gap:
            self._place_at_slot(v, light_nid, target_dist)
            v.speed = 0.0
            v.state = VehicleState.STOPPED
        else:
            if dist_to_light > 1e-6:
                r = move / dist_to_light
                v.lat += (light_node.lat - v.lat) * r
                v.lon += (light_node.lon - v.lon) * r
            v.state = VehicleState.BRAKING
        return True

    def _queue_release(self, v: Vehicle, dt: float) -> bool:
        REACTION_HEAD = 0.8
        REACTION_NEXT = 1.0

        key = (v.queue_light_node, v.queue_seg_from)
        self._queue_compact(key)
        if v.queue_light_node == -1:
            return False
        k   = v.queue_index
        q   = self._queues.get(key, [])
        if k < 0 or v.vehicle_id not in q:
            self._queue_remove(v)
            return False

        if k == 0:
            v.queue_release_timer += dt
            if v.queue_release_timer >= REACTION_HEAD:
                self._queue_remove(v)
                v.queue_cooldown = QUEUE_RELEASE_COOLDOWN
                return False
            v.speed = 0.0
            v.state = VehicleState.STOPPED
            return True

        pred_id = q[k - 1] if (k - 1) < len(q) else None
        pred    = self.vehicles.get(pred_id) if pred_id is not None else None

        if pred is None or pred.queue_light_node == -1:
            v.queue_release_timer += dt
            if v.queue_release_timer >= REACTION_NEXT:
                self._queue_remove(v)
                v.queue_cooldown = QUEUE_RELEASE_COOLDOWN
                return False
            v.speed = 0.0
            v.state = VehicleState.STOPPED
            return True

        v.queue_release_timer = 0.0
        v.speed = 0.0
        v.state = VehicleState.STOPPED
        return True

    def _place_at_slot(self, v: Vehicle, light_nid: int,
                       target_dist: float) -> None:
        """Place v à target_dist mètres du feu sur l'axe du segment (figé au join)."""
        light_node  = self.graph.nodes.get(light_nid)
        origin_node = self.graph.nodes.get(v.queue_seg_from)
        if light_node is None or origin_node is None:
            return

        seg_len = haversine(origin_node.lat, origin_node.lon,
                            light_node.lat,  light_node.lon)
        if seg_len < 1e-6:
            return

        ux, uy, ok = _seg_dir_meters(origin_node, light_node)
        if not ok:
            return

        d = max(STOP_LINE_DIST * 0.5, min(target_dist, seg_len - 0.5))
        # Recule depuis le feu de d mètres
        v.lat = light_node.lat - uy * (d / M_PER_DEG_LAT)
        v.lon = light_node.lon - ux * (d / M_PER_DEG_LON)

    # Déplacement physique

    def _move_vehicle(self, v: Vehicle, target_node,
                      dist: float, dt: float) -> Tuple[float, bool]:
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
            v.lat        = target_node.lat
            v.lon        = target_node.lon
            v.path_index += 1
            if v.path_index >= len(v.path):
                v.state = VehicleState.ARRIVED
                return used_dt, True
            self._init_segment(v)
            v.state = VehicleState.MOVING
            return used_dt, True
        else:
            r = move / dist
            v.lat += (target_node.lat - v.lat) * r
            v.lon += (target_node.lon - v.lon) * r
            return dt, False

    def _next_segment_has_space(self, v: Vehicle) -> bool:
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

    # Initialisation segment

    def _init_segment(self, v: Vehicle) -> None:
        if v.path_index >= len(v.path):
            return
        curr = v.path[v.path_index - 1] if v.path_index > 0 else v.path[0]
        nxt  = v.path[v.path_index]
        v.seg_from = curr
        v.seg_to   = nxt

        edge = next((e for e in self.graph.edges.get(curr, [])
                     if e.to_node == nxt), None)
        if edge:
            v.max_speed      = edge.speed_limit
            v.segment_length = edge.distance
            v.seg_road_id    = edge.road_id
            v.seg_oneway     = self._road_oneway.get(edge.road_id, False)
        else:
            cn = self.graph.nodes.get(curr)
            nn = self.graph.nodes.get(nxt)
            v.max_speed      = 11.1
            v.seg_road_id    = -1
            v.seg_oneway     = False
            v.segment_length = (haversine(cn.lat, cn.lon, nn.lat, nn.lon)
                                if cn and nn else 10.0)

    # Spawn libre

    def _spawn_free(self, new_v: Vehicle) -> bool:
        for other in self.vehicles.values():
            if other.vehicle_id == new_v.vehicle_id:
                continue
            if other.state in (VehicleState.ARRIVED, VehicleState.NO_PATH):
                continue
            if haversine(new_v.lat, new_v.lon,
                         other.lat, other.lon) < SAFE_GAP * 2.0:
                return False
        return True

    # Accesseurs publics

    def get_vehicle_list(self) -> List[Vehicle]:
        return list(self.vehicles.values())

    def get_active_count(self) -> int:
        return len(self.vehicles)

    def get_stats(self) -> dict:
        moving  = sum(1 for v in self.vehicles.values()
                      if v.state == VehicleState.MOVING)
        stopped = sum(1 for v in self.vehicles.values()
                      if v.state == VehicleState.STOPPED)
        braking = sum(1 for v in self.vehicles.values()
                      if v.state == VehicleState.BRAKING)
        waiting = sum(1 for v in self.vehicles.values()
                      if v.waiting_at_light)
        queue_lengths = self.get_queue_lengths()
        queued = sum(queue_lengths.values())
        max_queue = max(queue_lengths.values(), default=0)
        return {
            "total":    self.get_active_count(),
            "moving":   moving,
            "stopped":  stopped,
            "braking":  braking,
            "at_light": waiting,
            "arrived":  self.total_arrived,
            "spawned":  self.total_spawned,
            "queued":   queued,
            "max_queue": max_queue,
        }

    def get_queue_lengths(self) -> Dict[int, int]:
        lengths: Dict[int, int] = {}
        for (light_nid, _), queue in self._queues.items():
            lengths[light_nid] = lengths.get(light_nid, 0) + len(queue)
        return lengths

    def get_light_observations(self) -> Dict[int, dict]:
        observations: Dict[int, dict] = {}
        queue_lengths = self.get_queue_lengths()

        for light in self.light_manager.get_all_lights():
            nid = light.node_id
            observations[nid] = {
                "state": light.state.value,
                "time_remaining": light.time_remaining,
                "queue_length": queue_lengths.get(nid, 0),
                "waiting_vehicle_ids": [],
            }

        for (light_nid, _), queue in self._queues.items():
            obs = observations.setdefault(light_nid, {
                "state": None,
                "time_remaining": 0.0,
                "queue_length": len(queue),
                "waiting_vehicle_ids": [],
            })
            obs["waiting_vehicle_ids"].extend(queue)

        return observations
