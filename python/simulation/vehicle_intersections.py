"""Gestion des priorités et conflits aux intersections."""

import math
from typing import List, Set

from simulation.graph import haversine
from simulation.lights import LightState
from simulation.vehicle_constants import (
    INTER_CLEAR_DIST,
    INTER_RESERVE_DIST,
    INTER_YIELD_TIMEOUT,
    M_PER_DEG_LAT,
    M_PER_DEG_LON,
    QUEUE_SLOT,
)
from simulation.vehicle_geometry import _seg_dir_meters
from simulation.vehicle_model import Vehicle, VehicleState


class VehicleIntersectionMixin:
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
