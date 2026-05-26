"""Gestion des files devant les feux.

Un vehicule qui arrive sur un feu rouge rejoint la file de l'arete
entrante. Les places sont espacees de QUEUE_SLOT metres, le premier
s'arretant a STOP_LINE_DIST du feu. Au passage au vert on libere
voiture par voiture en respectant un petit cooldown
(QUEUE_RELEASE_COOLDOWN), sinon elles redemarrent quasiment toutes
en meme temps et finissent par se chevaucher.
"""

import math
from typing import List, Tuple

from simulation.graph import haversine
from simulation.lights import LightState
from simulation.vehicle_constants import (
    M_PER_DEG_LAT,
    M_PER_DEG_LON,
    MAX_DECEL,
    QUEUE_JOIN_DIST,
    QUEUE_RELEASE_COOLDOWN,
    QUEUE_SLOT,
    STOP_LINE_DIST,
)
from simulation.vehicle_geometry import _apply_speed, _seg_dir_meters
from simulation.vehicle_model import Vehicle, VehicleState


class VehicleQueueMixin:
    """Mixin du VehicleManager pour la gestion des files.

    Les files sont indexees par (noeud du feu, noeud d'origine du segment)
    pour qu'un meme feu serve plusieurs directions independantes.
    """

    def _handle_queue(self, v: Vehicle, target_nid: int,
                      dist: float, dt: float) -> bool:
        """Met le vehicule en file si necessaire, le libere si vert.

        Retourne True si le vehicule est en attente (le tick n'a plus
        besoin de calculer sa vitesse). Retourne False si le vehicule
        peut continuer normalement.
        """
        if v.queue_light_node != -1:
            key = (v.queue_light_node, v.queue_seg_from)
            if v.vehicle_id not in self._queues.get(key, []):
                self._queue_remove(v)
                return False
            ls = self.light_manager.get_state(v.queue_light_node)
            if ls == LightState.GREEN:
                return self._queue_release(v, dt)
            return self._queue_hold(v, dt)

        if v.queue_cooldown > 0.0:
            return False
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
        if light.state not in (LightState.RED, LightState.YELLOW):
            return False
        if not light.is_approached_from(v.seg_from):
            return False

        if not self._queue_join(v, target_nid):
            return False
        return self._queue_hold(v, dt)

    def _queue_join(self, v: Vehicle, light_nid: int) -> bool:
        """Ajoute le vehicule dans la file du feu s'il reste une place."""
        if v.seg_from == -1:
            return False
        if v.queue_light_node != -1 and v.queue_light_node != light_nid:
            self._queue_remove(v)
        self._token_release(v)

        captured_seg_from = v.seg_from
        key = (light_nid, captured_seg_from)
        q = self._queues.setdefault(key, [])
        if v.vehicle_id in q:
            self._queue_compact(key)
            return True

        self._queue_compact(key)
        q = self._queues.setdefault(key, [])
        if not self._queue_slot_fits(light_nid, captured_seg_from, len(q)):
            return False

        v.queue_light_node = light_nid
        v.queue_index = -1
        v.queue_seg_from = captured_seg_from
        v.queue_release_timer = 0.0
        v.waiting_at_light = True
        q.append(v.vehicle_id)
        self._queue_compact(key)
        self.light_manager.record_vehicle_waiting(light_nid)
        return True

    def _queue_remove(self, v: Vehicle) -> None:
        """Retire un vehicule de sa file et remet ses marqueurs a zero."""
        if v.queue_light_node == -1:
            return
        key = (v.queue_light_node, v.queue_seg_from)
        q = self._queues.get(key, [])
        if v.vehicle_id in q:
            idx = q.index(v.vehicle_id)
            q.pop(idx)
            for i in range(idx, len(q)):
                ov = self.vehicles.get(q[i])
                if ov:
                    ov.queue_index = i
        v.queue_light_node = -1
        v.queue_index = -1
        v.queue_seg_from = -1
        v.waiting_at_light = False
        v.queue_release_timer = 0.0
        if not q and key in self._queues:
            del self._queues[key]
        elif q:
            self._queue_compact(key)

    def _queue_compact(self, key: Tuple[int, int]) -> None:
        """Nettoie une file puis recalcule l'ordre des vehicules."""
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
        """Verifie que la place demandee tient encore sur le segment."""
        light_node = self.graph.nodes.get(light_nid)
        origin_node = self.graph.nodes.get(seg_from)
        if light_node is None or origin_node is None:
            return False

        seg_len = haversine(origin_node.lat, origin_node.lon,
                            light_node.lat, light_node.lon)
        target_dist = STOP_LINE_DIST + slot_index * QUEUE_SLOT
        return target_dist <= max(STOP_LINE_DIST, seg_len - 0.5)

    def _queue_hold(self, v: Vehicle, dt: float) -> bool:
        """Garde le vehicule a sa position de file tant que le feu bloque."""
        light_nid = v.queue_light_node
        key = (light_nid, v.queue_seg_from)
        self._queue_compact(key)
        if v.queue_light_node == -1:
            return False
        k = v.queue_index
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
        target_dist = STOP_LINE_DIST + k * QUEUE_SLOT
        gap = dist_to_light - target_dist

        if gap <= 0.5 or dist_to_light <= STOP_LINE_DIST + 0.5:
            self._place_at_slot(v, light_nid, target_dist)
            v.speed = 0.0
            v.state = VehicleState.STOPPED
            return True

        v_safe = math.sqrt(2.0 * MAX_DECEL * max(0.0, gap - 0.5))
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
        """Libere progressivement les vehicules quand le feu repasse au vert."""
        reaction_head = 0.8
        reaction_next = 1.0

        key = (v.queue_light_node, v.queue_seg_from)
        self._queue_compact(key)
        if v.queue_light_node == -1:
            return False
        k = v.queue_index
        q = self._queues.get(key, [])
        if k < 0 or v.vehicle_id not in q:
            self._queue_remove(v)
            return False

        if k == 0:
            v.queue_release_timer += dt
            if v.queue_release_timer >= reaction_head:
                self._queue_remove(v)
                v.queue_cooldown = QUEUE_RELEASE_COOLDOWN
                return False
            v.speed = 0.0
            v.state = VehicleState.STOPPED
            return True

        pred_id = q[k - 1] if (k - 1) < len(q) else None
        pred = self.vehicles.get(pred_id) if pred_id is not None else None

        if pred is None or pred.queue_light_node == -1:
            v.queue_release_timer += dt
            if v.queue_release_timer >= reaction_next:
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
        """Place le vehicule a la bonne distance de la ligne d'arret."""
        light_node = self.graph.nodes.get(light_nid)
        origin_node = self.graph.nodes.get(v.queue_seg_from)
        if light_node is None or origin_node is None:
            return

        seg_len = haversine(origin_node.lat, origin_node.lon,
                            light_node.lat, light_node.lon)
        if seg_len < 1e-6:
            return

        ux, uy, ok = _seg_dir_meters(origin_node, light_node)
        if not ok:
            return

        d = max(STOP_LINE_DIST * 0.5, min(target_dist, seg_len - 0.5))
        v.lat = light_node.lat - uy * (d / M_PER_DEG_LAT)
        v.lon = light_node.lon - ux * (d / M_PER_DEG_LON)
