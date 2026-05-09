"""Structures de données des véhicules."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Tuple


class VehicleState(Enum):
    MOVING = auto()
    BRAKING = auto()
    STOPPED = auto()
    ARRIVED = auto()
    NO_PATH = auto()


@dataclass
class Vehicle:
    vehicle_id: int
    origin_node: int
    dest_node: int

    path: List[int] = field(default_factory=list)
    path_index: int = 0

    lat: float = 0.0
    lon: float = 0.0
    speed: float = 0.0
    max_speed: float = 11.1
    segment_length: float = 0.0

    state: VehicleState = VehicleState.STOPPED
    color: Tuple[int, int, int] = (255, 200, 0)
    travel_time: float = 0.0

    waiting_at_light: bool = False

    seg_from: int = -1
    seg_to: int = -1
    seg_road_id: int = -1
    seg_oneway: bool = False

    queue_light_node: int = -1
    queue_index: int = -1
    queue_seg_from: int = -1
    queue_release_timer: float = 0.0
    queue_cooldown: float = 0.0

    reserved_node: int = -1
    yield_timer: float = 0.0
