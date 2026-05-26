"""Structures de données des véhicules.

Un Vehicle regroupe le trajet (path + path_index), la position
geographique, la vitesse courante et plusieurs petits etats : ou il
attend (s'il est en file devant un feu), ou il a reserve (s'il
attend de traverser une intersection sans feu). On garde tout dans
un seul dataclass parce que les mixins en ont tous besoin.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Tuple


class VehicleState(Enum):
    """Etat dynamique d'un vehicule.

    ARRIVED et NO_PATH sont des etats terminaux : le vehicule sera
    retire au prochain update().
    """
    MOVING = auto()
    BRAKING = auto()
    STOPPED = auto()
    ARRIVED = auto()
    NO_PATH = auto()


@dataclass
class Vehicle:
    """Une voiture de la simulation."""
    vehicle_id: int
    origin_node: int
    dest_node: int

    path: List[int] = field(default_factory=list)
    path_index: int = 0

    lat: float = 0.0
    lon: float = 0.0
    speed: float = 0.0
    max_speed: float = 11.1   # ~40 km/h, vitesse de croisiere urbaine
    segment_length: float = 0.0

    state: VehicleState = VehicleState.STOPPED
    color: Tuple[int, int, int] = (255, 200, 0)
    travel_time: float = 0.0

    waiting_at_light: bool = False

    # Segment courant et infos sur la route qu'il parcourt
    seg_from: int = -1
    seg_to: int = -1
    seg_road_id: int = -1
    seg_oneway: bool = False

    # Etat dans une file devant un feu (-1 si pas en file)
    queue_light_node: int = -1
    queue_index: int = -1
    queue_seg_from: int = -1
    queue_release_timer: float = 0.0
    queue_cooldown: float = 0.0

    # Reservation d'un noeud d'intersection sans feu
    reserved_node: int = -1
    yield_timer: float = 0.0
