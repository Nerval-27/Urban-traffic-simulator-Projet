"""Gestion des feux de circulation."""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


# Durées des cycles, en secondes simulées.

CYCLE_TOTAL        = 90.0   # durée totale du cycle

GREEN_A            = 35.0
YELLOW_A           = 4.0
RED_A              = CYCLE_TOTAL - GREEN_A - YELLOW_A   # 51s

PHASE_B_OFFSET     = GREEN_A + YELLOW_A                 # 39s
GREEN_B            = 35.0
YELLOW_B           = 4.0
RED_B_BEFORE       = PHASE_B_OFFSET                     # 39s
RED_B_AFTER        = CYCLE_TOTAL - RED_B_BEFORE - GREEN_B - YELLOW_B  # 12s

ALL_RED_TIME       = 2.0
MIN_GREEN_TIME     = 12.0
MAX_GREEN_TIME     = 70.0

INTERSECTION_RADIUS = 25.0

M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(48.85))


class LightState(Enum):
    RED    = "red"
    GREEN  = "green"
    YELLOW = "yellow"


def make_cycle_A() -> List[Tuple[LightState, float]]:
    """Cycle de la première phase."""
    return [
        (LightState.GREEN,  GREEN_A),
        (LightState.YELLOW, YELLOW_A),
        (LightState.RED,    RED_A),
    ]

def make_cycle_B() -> List[Tuple[LightState, float]]:
    """Cycle de la seconde phase."""
    return [
        (LightState.RED,    RED_B_BEFORE),
        (LightState.GREEN,  GREEN_B),
        (LightState.YELLOW, YELLOW_B),
        (LightState.RED,    RED_B_AFTER),
    ]


@dataclass
class TrafficLight:
    node_id: int
    lat: float
    lon: float

    cycle: List[Tuple[LightState, float]] = field(default_factory=list)

    current_phase_index: int = 0
    time_in_phase: float     = 0.0

    phase_offset: float = 0.0

    group_id: Optional[int] = None
    group_phase: str = "A"   # "A" ou "B"

    controlled_from_nodes: List[int] = field(default_factory=list)

    def __post_init__(self):
        if not self.cycle:
            self.cycle = make_cycle_A()
        self._controlled_set: set = set(self.controlled_from_nodes)
        self._controlled_state: Optional[LightState] = None
        self._controlled_remaining: float = 0.0
        self._apply_offset(self.phase_offset)

    def _apply_offset(self, offset: float) -> None:
        """Avance dans le cycle de `offset` secondes (déterministe)."""
        remaining = offset % CYCLE_TOTAL
        while remaining > 1e-9:
            _, duration = self.cycle[self.current_phase_index]
            available = duration - self.time_in_phase
            if remaining < available:
                self.time_in_phase += remaining
                remaining = 0.0
            else:
                remaining -= available
                self.time_in_phase = 0.0
                self.current_phase_index = (
                    self.current_phase_index + 1) % len(self.cycle)

    @property
    def state(self) -> LightState:
        if self._controlled_state is not None:
            return self._controlled_state
        return self.cycle[self.current_phase_index][0]

    @property
    def time_remaining(self) -> float:
        if self._controlled_state is not None:
            return self._controlled_remaining
        _, duration = self.cycle[self.current_phase_index]
        return duration - self.time_in_phase

    def update(self, dt: float) -> None:
        if self._controlled_state is not None:
            return
        self.time_in_phase += dt
        _, duration = self.cycle[self.current_phase_index]
        while self.time_in_phase >= duration:
            self.time_in_phase -= duration
            self.current_phase_index = (
                self.current_phase_index + 1) % len(self.cycle)
            _, duration = self.cycle[self.current_phase_index]

    def is_green(self)  -> bool: return self.state == LightState.GREEN
    def is_red(self)    -> bool: return self.state == LightState.RED
    def is_yellow(self) -> bool: return self.state == LightState.YELLOW

    def get_color_rgb(self) -> Tuple[int, int, int]:
        return {
            LightState.RED:    (220, 50,  50),
            LightState.GREEN:  (50,  200, 50),
            LightState.YELLOW: (220, 200, 50),
        }[self.state]

    def is_approached_from(self, from_node: int) -> bool:
        """
        Retourne True si ce feu contrôle les véhicules venant de from_node.
        """
        if not self._controlled_set:
            return True
        return from_node in self._controlled_set

    def force_state(self, new_state: LightState) -> None:
        self._controlled_state = None
        self._controlled_remaining = 0.0
        for i, (s, _) in enumerate(self.cycle):
            if s == new_state:
                self.current_phase_index = i
                self.time_in_phase = 0.0
                return

    def apply_controlled_state(self, state: LightState,
                               time_remaining: float,
                               time_in_phase: float) -> None:
        """Etat impose par le controleur du carrefour."""
        self._controlled_state = state
        self._controlled_remaining = max(0.0, time_remaining)
        self.time_in_phase = max(0.0, time_in_phase)

        for i, (cycle_state, _) in enumerate(self.cycle):
            if cycle_state == state:
                self.current_phase_index = i
                return


@dataclass
class IntersectionGroup:
    """Regroupe les feux d'un même carrefour physique."""
    group_id:     int
    center_lat:   float
    center_lon:   float
    phase_A_nodes: List[int] = field(default_factory=list)
    phase_B_nodes: List[int] = field(default_factory=list)


@dataclass
class GroupSignalRuntime:
    """Horloge commune d'un carrefour.

    Le RL peut demander une action, mais cette classe garde les transitions
    physiques : vert minimal, jaune, tout rouge, puis autre phase.
    """
    group_id: int
    has_phase_b: bool

    phase: str = "A"
    stage: str = "green"       # green, yellow, all_red, red
    time_in_stage: float = 0.0
    next_phase: str = "B"
    switch_requested: bool = False
    green_bonus: float = 0.0

    def apply_offset(self, offset: float) -> None:
        steps = self._cycle_steps()
        total = sum(duration for _, _, duration, _ in steps)
        remaining = offset % total

        for phase, stage, duration, next_phase in steps:
            if remaining < duration:
                self.phase = phase
                self.stage = stage
                self.next_phase = next_phase
                self.time_in_stage = remaining
                return
            remaining -= duration

    def update(self, dt: float) -> None:
        if dt <= 0.0:
            return

        self.time_in_stage += dt
        if self._can_switch_now():
            self._start_yellow()
            return

        guard = 0
        duration = self._stage_duration()
        while self.time_in_stage >= duration and guard < 8:
            overflow = self.time_in_stage - duration
            self._advance_stage()
            self.time_in_stage += overflow
            duration = self._stage_duration()
            guard += 1

    def request_switch(self) -> bool:
        if not self.has_phase_b or self.stage != "green":
            return False

        self.switch_requested = True
        if self.time_in_stage >= MIN_GREEN_TIME:
            self._start_yellow()
        return True

    def extend_green(self, seconds: float) -> bool:
        if self.stage != "green" or seconds <= 0.0:
            return False

        base_green = self._base_green_duration()
        max_bonus = max(0.0, MAX_GREEN_TIME - base_green)
        old_bonus = self.green_bonus
        self.green_bonus = min(max_bonus, self.green_bonus + seconds)
        return self.green_bonus > old_bonus

    def state_for_phase(self, phase: str) -> LightState:
        if self.stage == "green" and phase == self.phase:
            return LightState.GREEN
        if self.stage == "yellow" and phase == self.phase:
            return LightState.YELLOW
        return LightState.RED

    def time_remaining(self) -> float:
        return max(0.0, self._stage_duration() - self.time_in_stage)

    def public_status(self) -> dict:
        phase = self.phase if self.stage in ("green", "yellow") else "X"
        state = self.stage if self.stage in ("green", "yellow") else "red"
        return {
            "group_id": self.group_id,
            "phase": phase,
            "stage": self.stage,
            "state": state,
            "time_in_phase": self.time_in_stage,
            "time_remaining": self.time_remaining(),
            "next_phase": self.next_phase,
            "switch_requested": self.switch_requested,
        }

    def _can_switch_now(self) -> bool:
        return (
            self.switch_requested
            and self.stage == "green"
            and self.time_in_stage >= MIN_GREEN_TIME
        )

    def _advance_stage(self) -> None:
        if self.stage == "green":
            self._start_yellow()
        elif self.stage == "yellow":
            if self.has_phase_b:
                self.stage = "all_red"
                self.next_phase = self._other_phase(self.phase)
            else:
                self.stage = "red"
                self.next_phase = "A"
            self.time_in_stage = 0.0
        elif self.stage == "all_red":
            self.phase = self.next_phase
            self.stage = "green"
            self.time_in_stage = 0.0
            self.green_bonus = 0.0
            self.switch_requested = False
        elif self.stage == "red":
            self.phase = "A"
            self.stage = "green"
            self.time_in_stage = 0.0
            self.green_bonus = 0.0
            self.switch_requested = False

    def _start_yellow(self) -> None:
        self.stage = "yellow"
        self.time_in_stage = 0.0
        self.green_bonus = 0.0
        self.switch_requested = False

    def _stage_duration(self) -> float:
        if self.stage == "green":
            return self._base_green_duration() + self.green_bonus
        if self.stage == "yellow":
            return YELLOW_A if self.phase == "A" else YELLOW_B
        if self.stage == "all_red":
            return ALL_RED_TIME
        return RED_A

    def _base_green_duration(self) -> float:
        return GREEN_A if self.phase == "A" else GREEN_B

    def _cycle_steps(self):
        if not self.has_phase_b:
            return [
                ("A", "green", GREEN_A, "A"),
                ("A", "yellow", YELLOW_A, "A"),
                ("A", "red", RED_A, "A"),
            ]
        return [
            ("A", "green", GREEN_A, "B"),
            ("A", "yellow", YELLOW_A, "B"),
            ("A", "all_red", ALL_RED_TIME, "B"),
            ("B", "green", GREEN_B, "A"),
            ("B", "yellow", YELLOW_B, "A"),
            ("B", "all_red", ALL_RED_TIME, "A"),
        ]

    @staticmethod
    def _other_phase(phase: str) -> str:
        return "B" if phase == "A" else "A"


class TrafficLightManager:

    def __init__(self):
        self._lights:              Dict[int, TrafficLight]      = {}
        self._lights_by_group:     Dict[int, List[TrafficLight]] = {}
        self._groups:              Dict[int, IntersectionGroup] = {}
        self._group_runtimes:      Dict[int, GroupSignalRuntime] = {}
        self._simulation_time:     float                        = 0.0
        self._red_waiting_counts:  Dict[int, int]               = {}

    def build_from_graph(self, graph) -> None:
        """Crée les feux du graphe et les regroupe par carrefour."""
        self._lights.clear()
        self._lights_by_group.clear()
        self._groups.clear()
        self._group_runtimes.clear()
        self._red_waiting_counts.clear()

        light_nodes = [
            (nid, node)
            for nid, node in graph.nodes.items()
            if node.has_traffic_light
        ]

        if not light_nodes:
            print("[TrafficLightManager] Aucun feu détecté dans le graphe.")
            return

        groups = self._cluster_lights(light_nodes, graph)

        total_lights = 0
        for grp in groups:
            self._groups[grp.group_id] = grp

            coord_hash = (
                int(grp.center_lat * 10_000) * 31 +
                int(grp.center_lon * 10_000)
            ) % int(CYCLE_TOTAL)
            group_offset = float(coord_hash)
            runtime = GroupSignalRuntime(
                group_id=grp.group_id,
                has_phase_b=bool(grp.phase_B_nodes),
            )
            runtime.apply_offset(group_offset)
            self._group_runtimes[grp.group_id] = runtime

            for nid in grp.phase_A_nodes:
                node = graph.nodes[nid]
                controlled = self._compute_controlled_from(nid, "A", grp, graph)
                light = TrafficLight(
                    node_id=nid, lat=node.lat, lon=node.lon,
                    cycle=make_cycle_A(),
                    phase_offset=group_offset,
                    group_id=grp.group_id,
                    group_phase="A",
                    controlled_from_nodes=controlled,
                )
                self._lights[nid] = light
                self._lights_by_group.setdefault(grp.group_id, []).append(light)
                self._red_waiting_counts[nid] = 0
                total_lights += 1

            for nid in grp.phase_B_nodes:
                node = graph.nodes[nid]
                controlled = self._compute_controlled_from(nid, "B", grp, graph)
                light = TrafficLight(
                    node_id=nid, lat=node.lat, lon=node.lon,
                    cycle=make_cycle_B(),
                    phase_offset=group_offset,
                    group_id=grp.group_id,
                    group_phase="B",
                    controlled_from_nodes=controlled,
                )
                self._lights[nid] = light
                self._lights_by_group.setdefault(grp.group_id, []).append(light)
                self._red_waiting_counts[nid] = 0
                total_lights += 1

            self._apply_group_runtime(runtime)

        nb_isolated = sum(1 for g in groups if not g.phase_B_nodes)
        print(
            f"[TrafficLightManager] {total_lights} feux initialisés "
            f"dans {len(groups)} carrefours "
            f"({nb_isolated} feux isolés, cycle A seul)."
        )

    def _cluster_lights(self, light_nodes, graph) -> List[IntersectionGroup]:
        """
        Regroupe les feux proches sans former de carrefours trop larges.
        """
        nids  = [n[0] for n in light_nodes]
        nodes = {n[0]: n[1] for n in light_nodes}

        clusters: List[List[int]] = []
        centers: List[Tuple[float, float]] = []

        for nid in sorted(nids):
            node = nodes[nid]
            best_idx: Optional[int] = None
            best_dist = math.inf

            for idx, members in enumerate(clusters):
                center_lat, center_lon = centers[idx]
                d_center = _haversine(
                    node.lat, node.lon,
                    center_lat, center_lon,
                )
                if d_center > INTERSECTION_RADIUS:
                    continue

                # Le nouveau feu doit rester proche de tous les feux du groupe.
                if any(
                    _haversine(
                        node.lat, node.lon,
                        nodes[mid].lat, nodes[mid].lon,
                    ) > INTERSECTION_RADIUS
                    for mid in members
                ):
                    continue

                if d_center < best_dist:
                    best_idx = idx
                    best_dist = d_center

            if best_idx is None:
                clusters.append([nid])
                centers.append((node.lat, node.lon))
            else:
                clusters[best_idx].append(nid)
                members = clusters[best_idx]
                centers[best_idx] = (
                    sum(nodes[m].lat for m in members) / len(members),
                    sum(nodes[m].lon for m in members) / len(members),
                )

        groups: List[IntersectionGroup] = []
        for gid, members in enumerate(clusters):
            center_lat = sum(nodes[m].lat for m in members) / len(members)
            center_lon = sum(nodes[m].lon for m in members) / len(members)

            grp = IntersectionGroup(
                group_id=gid,
                center_lat=center_lat,
                center_lon=center_lon,
            )

            if len(members) == 1:
                grp.phase_A_nodes = list(members)
            else:
                self._assign_phases(grp, members, nodes, graph)

            groups.append(grp)

        return groups

    def _assign_phases(self, grp: IntersectionGroup,
                       members: List[int], nodes, graph) -> None:
        """Répartit les feux d'un carrefour en deux phases."""
        angles: Dict[int, float] = {}
        for nid in members:
            incoming = [
                e
                for elist in graph.edges.values()
                for e in elist
                if e.to_node == nid
            ]
            if not incoming:
                angles[nid] = 0.0
                continue

            thetas = []
            for e in incoming:
                fn = graph.nodes.get(e.from_node)
                tn = graph.nodes.get(e.to_node)
                if fn and tn:
                    theta = _axis_angle(fn, tn)
                    if theta is not None:
                        thetas.append(theta)

            angles[nid] = (sum(thetas) / len(thetas)) if thetas else 0.0

        ref_angle = angles[members[0]]
        phase_A, phase_B = [], []

        for nid in members:
            diff = abs(angles[nid] - ref_angle) % 180.0
            diff = min(diff, 180.0 - diff)
            if diff <= 45.0:
                phase_A.append(nid)
            else:
                phase_B.append(nid)

        # Si tout tombe sur le même axe, on sépare le groupe en deux phases.
        if not phase_B and len(phase_A) >= 2:
            half    = len(phase_A) // 2
            phase_B = phase_A[half:]
            phase_A = phase_A[:half]

        grp.phase_A_nodes = phase_A
        grp.phase_B_nodes = phase_B

    def _compute_controlled_from(self, nid: int, phase: str,
                                  grp: "IntersectionGroup", graph) -> List[int]:
        """Indique quelles arrivées sont contrôlées par ce feu."""
        incoming_edges = [
            e
            for edges_list in graph.edges.values()
            for e in edges_list
            if e.to_node == nid
        ]
        if not incoming_edges:
            return []

        other_phase_nodes = grp.phase_B_nodes if phase == "A" else grp.phase_A_nodes
        if not other_phase_nodes:
            return [e.from_node for e in incoming_edges]

        same_phase_nodes = grp.phase_A_nodes if phase == "A" else grp.phase_B_nodes

        own_bearings: List[float] = []
        for sib_nid in same_phase_nodes:
            for edges_list in graph.edges.values():
                for edge in edges_list:
                    if edge.to_node == sib_nid:
                        fn = graph.nodes.get(edge.from_node)
                        tn = graph.nodes.get(edge.to_node)
                        if fn and tn:
                            b = _axis_angle(fn, tn)
                            if b is not None:
                                own_bearings.append(b)

        if not own_bearings:
            return [e.from_node for e in incoming_edges]

        sin_sum = sum(math.sin(math.radians(b * 2)) for b in own_bearings)
        cos_sum = sum(math.cos(math.radians(b * 2)) for b in own_bearings)
        ref_angle = (math.degrees(math.atan2(sin_sum, cos_sum)) / 2.0) % 180.0

        controlled: List[int] = []
        for e in incoming_edges:
            fn = graph.nodes.get(e.from_node)
            tn = graph.nodes.get(e.to_node)
            if fn is None or tn is None:
                continue
            b = _axis_angle(fn, tn)
            if b is None:
                continue
            diff = abs(b - ref_angle) % 180.0
            diff = min(diff, 180.0 - diff)
            if diff <= 50.0:
                controlled.append(e.from_node)

        if not controlled:
            controlled = [e.from_node for e in incoming_edges]

        return list(dict.fromkeys(controlled))

    def add_light(self, node_id: int, lat: float, lon: float,
                  offset: float = 0.0,
                  cycle: Optional[List[Tuple[LightState, float]]] = None) -> None:
        light = TrafficLight(
            node_id=node_id, lat=lat, lon=lon,
            cycle=cycle or make_cycle_A(),
            phase_offset=offset,
        )
        self._lights[node_id] = light
        self._red_waiting_counts[node_id] = 0

    def update(self, dt: float) -> None:
        self._simulation_time += dt
        controlled_groups = set()
        for runtime in self._group_runtimes.values():
            runtime.update(dt)
            self._apply_group_runtime(runtime)
            controlled_groups.add(runtime.group_id)

        for light in self._lights.values():
            if light.group_id in controlled_groups:
                continue
            light.update(dt)

    def is_green(self, node_id: int) -> bool:
        if node_id not in self._lights:
            return True
        return self._lights[node_id].is_green()

    def is_green_for(self, node_id: int, from_node: int) -> bool:
        """Vérifie si l'arrivée donnée peut passer ce feu."""
        light = self._lights.get(node_id)
        if light is None:
            return True
        if not light.is_approached_from(from_node):
            return True
        return light.is_green()

    def is_red_or_yellow(self, node_id: int) -> bool:
        if node_id not in self._lights:
            return False
        return not self._lights[node_id].is_green()

    def is_red_or_yellow_for(self, node_id: int, from_node: int) -> bool:
        """Vérifie si l'arrivée donnée doit s'arrêter à ce feu."""
        light = self._lights.get(node_id)
        if light is None:
            return False
        if not light.is_approached_from(from_node):
            return False
        return not light.is_green()

    def get_state(self, node_id: int) -> Optional[LightState]:
        if node_id not in self._lights:
            return None
        return self._lights[node_id].state

    def get_time_remaining(self, node_id: int) -> float:
        if node_id not in self._lights:
            return 0.0
        return self._lights[node_id].time_remaining

    def get_light(self, node_id: int) -> Optional[TrafficLight]:
        return self._lights.get(node_id)

    def get_all_lights(self) -> List[TrafficLight]:
        return list(self._lights.values())

    def has_light(self, node_id: int) -> bool:
        return node_id in self._lights

    def record_vehicle_waiting(self, node_id: int) -> None:
        if node_id in self._red_waiting_counts:
            self._red_waiting_counts[node_id] += 1

    def get_waiting_stats(self) -> Dict[int, int]:
        return dict(self._red_waiting_counts)

    def get_light_states(self) -> Dict[int, dict]:
        return {
            nid: {
                "state": light.state.value,
                "time_remaining": light.time_remaining,
                "group_id": light.group_id,
                "group_phase": light.group_phase,
                "group_stage": self._group_stage(light.group_id),
                "controlled_from_nodes": list(light.controlled_from_nodes),
            }
            for nid, light in self._lights.items()
        }

    def get_congested_lights(self, threshold: int = 10) -> List[int]:
        return [
            nid for nid, count in self._red_waiting_counts.items()
            if count >= threshold
        ]

    def force_green(self, node_id: int) -> None:
        light = self._lights.get(node_id)
        if light is None:
            return

        runtime = self._group_runtimes.get(light.group_id)
        if runtime is None:
            light.force_state(LightState.GREEN)
            return

        runtime.phase = light.group_phase
        runtime.stage = "green"
        runtime.time_in_stage = 0.0
        runtime.next_phase = GroupSignalRuntime._other_phase(light.group_phase)
        runtime.switch_requested = False
        runtime.green_bonus = 0.0
        self._apply_group_runtime(runtime)

    def force_red(self, node_id: int) -> None:
        light = self._lights.get(node_id)
        if light is None:
            return

        runtime = self._group_runtimes.get(light.group_id)
        if runtime is None:
            light.force_state(LightState.RED)
            return

        runtime.stage = "all_red" if runtime.has_phase_b else "red"
        runtime.time_in_stage = 0.0
        runtime.next_phase = light.group_phase
        runtime.switch_requested = False
        runtime.green_bonus = 0.0
        self._apply_group_runtime(runtime)

    def get_group_info(self, node_id: int) -> Optional[IntersectionGroup]:
        light = self._lights.get(node_id)
        if light and light.group_id is not None:
            return self._groups.get(light.group_id)
        return None

    def get_groups(self) -> Dict[int, IntersectionGroup]:
        return dict(self._groups)

    def get_group_lights(self, group_id: int,
                         phase: Optional[str] = None) -> List[TrafficLight]:
        result: List[TrafficLight] = []
        for light in self._lights_by_group.get(group_id, []):
            if phase is not None and light.group_phase != phase:
                continue
            result.append(light)
        return result

    def request_phase_switch(self, group_id: int) -> bool:
        """Demande un changement de phase sans casser la sécurité."""
        if group_id not in self._groups:
            return False

        runtime = self._group_runtimes.get(group_id)
        if runtime is not None:
            switched = runtime.request_switch()
            self._apply_group_runtime(runtime)
            return switched

        switched = False
        for light in self._lights.values():
            if light.group_id != group_id:
                continue
            if light.state == LightState.GREEN:
                light.force_state(LightState.YELLOW)
                switched = True
        return switched

    def extend_green(self, group_id: int, seconds: float = 5.0) -> bool:
        """Prolonge le vert courant sans dépasser la limite de sécurité."""
        if group_id not in self._groups:
            return False

        runtime = self._group_runtimes.get(group_id)
        if runtime is not None:
            extended = runtime.extend_green(seconds)
            self._apply_group_runtime(runtime)
            return extended

        extended = False
        for light in self._lights.values():
            if light.group_id != group_id:
                continue
            if light.state != LightState.GREEN:
                continue
            light.time_in_phase = max(0.0, light.time_in_phase - seconds)
            extended = True
        return extended

    def get_group_status(self, group_id: int) -> Optional[dict]:
        runtime = self._group_runtimes.get(group_id)
        if runtime is None:
            return None
        return runtime.public_status()

    def _apply_group_runtime(self, runtime: GroupSignalRuntime) -> None:
        remaining = runtime.time_remaining()
        for light in self._lights_by_group.get(runtime.group_id, []):
            state = runtime.state_for_phase(light.group_phase)
            time_in_phase = runtime.time_in_stage if light.group_phase == runtime.phase else 0.0
            light.apply_controlled_state(state, remaining, time_in_phase)

    def _group_stage(self, group_id: Optional[int]) -> Optional[str]:
        runtime = self._group_runtimes.get(group_id)
        return None if runtime is None else runtime.stage

    @property
    def simulation_time(self) -> float:
        return self._simulation_time


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi       = math.radians(lat2 - lat1)
    dlambda    = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2.0 * R * math.asin(math.sqrt(a))


def _axis_angle(from_node, to_node) -> Optional[float]:
    """Axe metrique d'un segment, ramene sur [0, 180[ pour ignorer le sens."""
    dx = (to_node.lon - from_node.lon) * M_PER_DEG_LON
    dy = (to_node.lat - from_node.lat) * M_PER_DEG_LAT
    if math.sqrt(dx * dx + dy * dy) < 1e-6:
        return None
    return math.degrees(math.atan2(dy, dx)) % 180.0
