

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class LightState(Enum):
    RED    = "red"
    GREEN  = "green"
    YELLOW = "yellow"


# Durées par défaut (en secondes simulées)
# Cycle court et visible : vert 10s → orange 3s → rouge 12s (total 25s)
# Avec sim_speed x1 : un cycle complet toutes les 25 secondes réelles
# Avec sim_speed x2 : un cycle toutes les 12 secondes réelles → bien visible à la démo
DEFAULT_GREEN_DURATION  = 10.0
DEFAULT_YELLOW_DURATION = 3.0
DEFAULT_RED_DURATION    = 12.0


@dataclass
class TrafficLight:
    """
    Représente un feu de circulation individuel attaché à un node OSM.

    Chaque feu a son propre timer et cycle. Par défaut ils sont décalés
    aléatoirement pour éviter que tous les feux soient synchronisés.
    """
    node_id: int
    lat: float
    lon: float

    # Cycle : liste de (LightState, durée_en_secondes)
    cycle: List[Tuple[LightState, float]] = field(default_factory=list)

    # Position dans le cycle
    current_phase_index: int = 0
    time_in_phase: float = 0.0      # secondes déjà passées dans la phase courante

    # Décalage initial (pour désynchroniser les feux entre eux)
    phase_offset: float = 0.0

    def __post_init__(self):
        if not self.cycle:
            # Cycle standard : vert → orange → rouge
            self.cycle = [
                (LightState.GREEN,  DEFAULT_GREEN_DURATION),
                (LightState.YELLOW, DEFAULT_YELLOW_DURATION),
                (LightState.RED,    DEFAULT_RED_DURATION),
            ]
        # Appliquer le décalage initial
        self._apply_offset(self.phase_offset)

    def _apply_offset(self, offset):
        """Avance le timer de 'offset' secondes pour désynchroniser les feux."""
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
        """Secondes restantes dans la phase courante."""
        _, duration = self.cycle[self.current_phase_index]
        return duration - self.time_in_phase

    def update(self, dt: float):
        """Avance le timer du feu de dt secondes."""
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
        """Force un état (pour plus tard). Repart du début de la phase."""
        for i, (s, _) in enumerate(self.cycle):
            if s == new_state:
                self.current_phase_index = i
                self.time_in_phase = 0.0
                return

    def get_color_rgb(self):
        """Retourne la couleur RGB pour Pygame."""
        colors = {
            LightState.RED:    (220, 50,  50),
            LightState.GREEN:  (50,  200, 50),
            LightState.YELLOW: (220, 200, 50),
        }
        return colors[self.state]


class TrafficLightManager:
    """
    Gestionnaire centralisé de tous les feux de circulation.

    Interface principale pour le reste du simulateur :
        - update(dt)           : mettre à jour tous les feux
        - is_green(node_id)    : vrai si le feu sur ce nœud est vert
        - get_state(node_id)   : retourne LightState ou None si pas de feu
        - get_light(node_id)   : retourne l'objet TrafficLight complet
        - get_all_lights()     : liste de tous les feux (pour le renderer)
    """

    def __init__(self):
        # node_id -> TrafficLight
        self._lights: Dict[int, TrafficLight] = {}
        self._simulation_time: float = 0.0

        # Statistiques pour un futur module d'optimisation
        self._red_waiting_counts: Dict[int, int] = {}   # combien de véhicules ont attendu



    def build_from_graph(self, graph):
        """
        Construit les feux à partir du graphe

        On désynchronise les feux en les décalant aléatoirement dans leur cycle.
        """
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
        """Ajoute manuellement un feu (utile pour les tests)."""
        light = TrafficLight(node_id=node_id, lat=lat, lon=lon,
                             cycle=cycle or [], phase_offset=offset)
        self._lights[node_id] = light


    def update(self, dt):
        """
        Appeler à chaque tick de simulation.
        dt = temps écoulé en secondes (ex : 1/60 pour 60 FPS).

        C'est ici que l'on pourrait brancher un algorithme d'optimisation :
        - Analyser les queues de voitures sur chaque branche
        - Prolonger les phases vertes dynamiquement
        """
        self._simulation_time += dt
        for light in self._lights.values():
            light.update(dt)


    def is_green(self, node_id):
        """
        Retourne True si le nœud n'a pas de feu OU si le feu est vert.
        """
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
        """Temps restant dans la phase courante."""
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

    def set_cycle(self, node_id: int, green_duration: float, red_duration: float,
                  yellow_duration: float = 5.0):
        """
        Modifie dynamiquement le cycle d'un feu.
        Point d'entrée pour un futur algorithme d'optimisation IA.
        """
        if node_id in self._lights:
            light = self._lights[node_id]
            light.cycle = [
                (LightState.GREEN,  green_duration),
                (LightState.YELLOW, yellow_duration),
                (LightState.RED,    red_duration),
            ]
            # Repart du début pour éviter un état incohérent
            light.current_phase_index = 0
            light.time_in_phase = 0.0

    @property
    def simulation_time(self) -> float:
        return self._simulation_time
