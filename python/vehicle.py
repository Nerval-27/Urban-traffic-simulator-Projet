"""Coordination générale des véhicules de la simulation."""

import random
from typing import Dict, List, Optional, Set, Tuple

from graph import RoadGraph, haversine
from traffic_light_manager import TrafficLightManager
from vehicle_constants import (
    CONGESTION_BRAKING_PENALTY,
    CONGESTION_QUEUE_PENALTY,
    CONGESTION_ROAD_FACTOR,
    CONGESTION_STOPPED_PENALTY,
    CONGESTION_VEHICLE_PENALTY,
    MAX_ACCEL,
    MAX_SEGS_PER_TICK,
    MIN_SPEED,
    QUEUE_RELEASE_COOLDOWN,
)
from vehicle_geometry import _apply_speed, _speed_for_gap
from vehicle_intersections import VehicleIntersectionMixin
from vehicle_model import Vehicle, VehicleState
from vehicle_motion import VehicleMotionMixin
from vehicle_queues import VehicleQueueMixin


class VehicleManager(VehicleQueueMixin,
                     VehicleIntersectionMixin,
                     VehicleMotionMixin):
    def __init__(self, graph: RoadGraph, light_manager: TrafficLightManager,
                 rng: Optional[random.Random] = None):
        self.graph = graph
        self.light_manager = light_manager
        self.rng = rng or random.Random(0)

        self.vehicles: Dict[int, Vehicle] = {}
        self._next_id = 0
        self.total_arrived = 0
        self.total_spawned = 0

        self._road_oneway: Dict[int, bool] = {}
        self._queues: Dict[Tuple[int, int], List[int]] = {}
        self._node_tokens: Dict[int, Set[int]] = {}
        self._incoming_cache: Optional[Dict[int, Set[int]]] = None

    def build_edge_index(self) -> None:
        existing: Set[Tuple[int, int, int]] = set()
        road_fwd: Dict[int, List[Tuple[int, int]]] = {}

        for edges_list in self.graph.edges.values():
            for edge in edges_list:
                existing.add((edge.road_id, edge.from_node, edge.to_node))
                road_fwd.setdefault(edge.road_id, []).append(
                    (edge.from_node, edge.to_node)
                )

        for road_id, pairs in road_fwd.items():
            self._road_oneway[road_id] = all(
                (road_id, to_node, from_node) not in existing
                for (from_node, to_node) in pairs
            )

        self._incoming_cache = {}
        for from_nid, edges in self.graph.edges.items():
            for edge in edges:
                self._incoming_cache.setdefault(edge.to_node, set()).add(from_nid)

        one_way_count = sum(1 for value in self._road_oneway.values() if value)
        two_way_count = len(self._road_oneway) - one_way_count
        print(
            f"[VehicleManager] {one_way_count} routes sens unique, "
            f"{two_way_count} double sens"
        )

    def spawn_vehicle(self,
                      origin_node: Optional[int] = None,
                      dest_node: Optional[int] = None) -> Optional[Vehicle]:
        pool = self.graph.get_spawn_nodes()
        if len(pool) < 2:
            return None

        for _ in range(20):
            origin = origin_node or self.rng.choice(pool)
            dest = dest_node or self.rng.choice(pool)
            if origin != dest:
                break
        else:
            return None

        path = self.graph.dijkstra(origin, dest, self._make_congestion_penalty())
        if not path or len(path) < 2:
            return None

        origin_graph_node = self.graph.nodes.get(origin)
        if origin_graph_node is None:
            return None

        vehicle_id = self._next_id
        self._next_id += 1

        color = (
            self.rng.randint(180, 255),
            self.rng.randint(100, 200),
            self.rng.randint(0, 80),
        )

        vehicle = Vehicle(
            vehicle_id=vehicle_id,
            origin_node=origin,
            dest_node=dest,
            path=path,
            path_index=1,
            lat=origin_graph_node.lat,
            lon=origin_graph_node.lon,
            speed=0.0,
            color=color,
            state=VehicleState.MOVING,
        )
        self._init_segment(vehicle)

        self.vehicles[vehicle_id] = vehicle
        if not self._spawn_free(vehicle):
            del self.vehicles[vehicle_id]
            return None

        self.total_spawned += 1
        return vehicle

    def spawn_batch(self, count: int) -> int:
        created = 0
        for _ in range(count):
            if self.spawn_vehicle() is not None:
                created += 1
        return created

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

    def update(self, dt: float) -> None:
        to_remove = []
        for vehicle_id, vehicle in self.vehicles.items():
            if vehicle.state in (VehicleState.ARRIVED, VehicleState.NO_PATH):
                to_remove.append(vehicle_id)
                continue

            vehicle.travel_time += dt
            if vehicle.queue_cooldown > 0.0:
                vehicle.queue_cooldown = max(
                    0.0,
                    vehicle.queue_cooldown - dt,
                )

            self._update_vehicle(vehicle, dt)
            if vehicle.state == VehicleState.ARRIVED:
                to_remove.append(vehicle_id)
                self.total_arrived += 1

        for vehicle_id in to_remove:
            vehicle = self.vehicles.pop(vehicle_id)
            self._queue_remove(vehicle)
            self._token_release(vehicle)

        self._resolve_same_segment_overlaps()
        self._resolve_adjacent_segment_overlaps()

    def _update_vehicle(self, vehicle: Vehicle, dt: float) -> None:
        remaining = dt
        segs = 0
        steps = 0

        while (remaining > 1e-9
               and segs < MAX_SEGS_PER_TICK
               and steps < MAX_SEGS_PER_TICK * 3):
            steps += 1
            if vehicle.state in (VehicleState.ARRIVED, VehicleState.NO_PATH):
                return
            if not vehicle.path or vehicle.path_index >= len(vehicle.path):
                vehicle.state = VehicleState.ARRIVED
                return

            target_nid = vehicle.path[vehicle.path_index]
            target_node = self.graph.nodes.get(target_nid)
            if target_node is None:
                vehicle.state = VehicleState.ARRIVED
                return

            dist = haversine(
                vehicle.lat,
                vehicle.lon,
                target_node.lat,
                target_node.lon,
            )

            speed_cap = max(
                MIN_SPEED,
                min(vehicle.max_speed, vehicle.speed + MAX_ACCEL * remaining),
            )
            if dist > 0.1:
                step_dt = min(remaining, dist / max(speed_cap, MIN_SPEED))
            else:
                step_dt = remaining
            step_dt = max(1e-6, min(step_dt, remaining))

            prev_idx = vehicle.path_index
            before = remaining
            used_dt, crossed = self._tick(
                vehicle,
                target_nid,
                target_node,
                dist,
                step_dt,
            )
            remaining -= max(used_dt, 1e-6)

            if not crossed or vehicle.path_index == prev_idx:
                if vehicle.speed <= 0.0 or used_dt >= before - 1e-6:
                    break
                continue
            segs += 1

    def _tick(self, vehicle: Vehicle, target_nid: int,
              target_node, dist: float, dt: float) -> Tuple[float, bool]:
        if self._handle_queue(vehicle, target_nid, dist, dt):
            return dt, False

        desired = vehicle.max_speed
        desired = min(desired, _speed_for_gap(
            self._gap_to_leader(vehicle, target_nid, dist),
            vehicle.max_speed,
        ))
        desired = min(desired, self._light_approach_speed(vehicle))
        desired = min(desired, self._intersection_token_speed(
            vehicle,
            target_nid,
            dist,
            dt,
        ))

        _apply_speed(vehicle, desired, dt)
        if self._red_light_stop_guard(vehicle, target_nid, dist, dt):
            return dt, False
        if vehicle.speed <= 0.0:
            return dt, False
        return self._move_vehicle(vehicle, target_node, dist, dt)

    def get_vehicle_list(self) -> List[Vehicle]:
        return list(self.vehicles.values())

    def get_active_count(self) -> int:
        return len(self.vehicles)

    def get_stats(self) -> dict:
        moving = sum(1 for v in self.vehicles.values()
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
            "total": self.get_active_count(),
            "moving": moving,
            "stopped": stopped,
            "braking": braking,
            "at_light": waiting,
            "arrived": self.total_arrived,
            "spawned": self.total_spawned,
            "queued": queued,
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


__all__ = ["Vehicle", "VehicleManager", "VehicleState"]
