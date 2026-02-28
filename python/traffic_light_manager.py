

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class LightState(Enum):
    RED    = "red"
    GREEN  = "green"
    YELLOW = "yellow"


# Durées par défaut (en secondes simulées)
# Cycle court et visible : vert 10s  orange 3s  rouge 12s (total 25s)
DEFAULT_GREEN_DURATION  = 10.0
DEFAULT_YELLOW_DURATION = 3.0
DEFAULT_RED_DURATION    = 12.0


@dataclass
class TrafficLight:
    # cycle vert/orange/rouge
    node_id: int
    lat: float
    lon: float

    # Cycle : liste de (LightState, durée_en_secondes)
    cycle: List[Tuple[LightState, float]] = field(default_factory=list)

    # Position dans le cycle
    current_phase_index: int = 0
    time_in_phase: float = 0.0      # secondes déjà passées dans la phase courante

    phase_offset: float = 0.0

    def __post_init__(self):
        if not self.cycle:
            # Cycle standard : vert  orange  rouge
            self.cycle = [
                (LightState.GREEN,  DEFAULT_GREEN_DURATION),
                (LightState.YELLOW, DEFAULT_YELLOW_DURATION),
                (LightState.RED,    DEFAULT_RED_DURATION),
            ]
        # Appliquer le décalage initial
        self._apply_offset(self.phase_offset)

    def _apply_offset(self, offset):
        remaining = offset
        while remaining > 0:
            _, duration = self.cycle[self.current_phase_index]
            if self.time_in_phase + remaining < duration:
                self.time_in_phase += remaining
                remaining = 0
            else:
                remaining -= (duration - self.time_in_phase)
                self.time_in_phase = 0
                self.current_phase_index = (self.current_phase_index + 1) % len(self.cycle)

    @property
    def state(self):
        return self.cycle[self.current_phase_index][0]

    @property
    def time_remaining(self):
        _, duration = self.cycle[self.current_phase_index]
        return duration - self.time_in_phase

    def update(self, dt: float):
        self.time_in_phase += dt
        _, duration = self.cycle[self.current_phase_index]
        if self.time_in_phase >= duration:
            self.time_in_phase -= duration
            self.current_phase_index = (self.current_phase_index + 1) % len(self.cycle)

    def is_green(self) -> bool:
        return self.state == LightState.GREEN

    def is_red(self) -> bool:
        return self.state == LightState.RED

    def is_yellow(self) -> bool:
        return self.state == LightState.YELLOW

    def force_state(self, new_state: LightState):
        for i, (s, _) in enumerate(self.cycle):
            if s == new_state:
                self.current_phase_index = i
                self.time_in_phase = 0.0
                return

    def get_color_rgb(self):
        colors = {
            LightState.RED:    (220, 50,  50),
            LightState.GREEN:  (50,  200, 50),
            LightState.YELLOW: (220, 200, 50),
        }
        return colors[self.state]


class TrafficLightManager:
    def __init__(self):
        # node_id -> TrafficLight
        self._lights: Dict[int, TrafficLight] = {}
        self._simulation_time: float = 0.0

        # Statistiques pour un futur module d'optimisation
        self._red_waiting_counts: Dict[int, int] = {}   # combien de véhicules ont attendu



    def build_from_graph(self, graph):
        import random
        rng = random.Random(42)  # seed fixe pour reproductibilité

        total_cycle = DEFAULT_GREEN_DURATION + DEFAULT_YELLOW_DURATION + DEFAULT_RED_DURATION

        count = 0
        for nid, node in graph.nodes.items():
            if node.has_traffic_light:
                offset = rng.uniform(0, total_cycle)
                light = TrafficLight(
                    node_id=nid,
                    lat=node.lat,
                    lon=node.lon,
                    phase_offset=offset
                )
                self._lights[nid] = light
                self._red_waiting_counts[nid] = 0
                count += 1

        print(f"[TrafficLightManager] {count} feux initialisés.")

    def add_light(self, node_id: int, lat: float, lon: float,
                  offset: float = 0.0,
                  cycle: Optional[List[Tuple[LightState, float]]] = None):
        light = TrafficLight(node_id=node_id, lat=lat, lon=lon,
                             cycle=cycle or [], phase_offset=offset)
        self._lights[node_id] = light


    def update(self, dt):
        self._simulation_time += dt
        for light in self._lights.values():
            light.update(dt)


    def is_green(self, node_id):
        if node_id not in self._lights:
            return True
        return self._lights[node_id].is_green()

    def is_red_or_yellow(self, node_id):
        """Retourne True si le feu est rouge ou orange (véhicule doit s'arrêter)."""
        if node_id not in self._lights:
            return False
        return not self._lights[node_id].is_green()

    def get_state(self, node_id):
        """Retourne l'état du feu ou None s'il n'y a pas de feu."""
        if node_id not in self._lights:
            return None
        return self._lights[node_id].state

    def get_time_remaining(self, node_id):
        if node_id not in self._lights:
            return 0.0
        return self._lights[node_id].time_remaining

    def get_light(self, node_id):
        return self._lights.get(node_id)

    def get_all_lights(self):
        return list(self._lights.values())

    def has_light(self, node_id: int):
        return node_id in self._lights


    def record_vehicle_waiting(self, node_id):
        """Enregistre qu'un véhicule a dû attendre à ce feu (pour les stats)."""
        if node_id in self._red_waiting_counts:
            self._red_waiting_counts[node_id] += 1

    def get_waiting_stats(self):
        """Retourne le nombre total d'arrêts par feu."""
        return dict(self._red_waiting_counts)

    def get_congested_lights(self, threshold: int = 10) -> List[int]:
        """Retourne les node_ids des feux avec beaucoup d'attente."""
        return [nid for nid, count in self._red_waiting_counts.items()
                if count >= threshold]


    def force_green(self, node_id: int):
        """Force un feu au vert (debug)."""
        if node_id in self._lights:
            self._lights[node_id].force_state(LightState.GREEN)

    def force_red(self, node_id: int):
        """Force un feu au rouge (debug)."""
        if node_id in self._lights:
            self._lights[node_id].force_state(LightState.RED)


    @property
    def simulation_time(self) -> float:
        return self._simulation_time
