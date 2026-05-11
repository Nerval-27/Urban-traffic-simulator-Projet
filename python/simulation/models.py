
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional, Dict


# Aliases de types
IntersectionId = int
RoadId         = int
VehicleId      = int
NodeId         = int


class LightColor(Enum):
    RED    = "Red"
    GREEN  = "Green"
    YELLOW = "Yellow"


@dataclass
class Road:
    id: RoadId
    length: float
    speed_limit: float
    nodes: List[NodeId]
    next: NodeId
    oneway: bool = False
    name: str = "Inconnue"


@dataclass
class TrafficSignal:
    id: int
    lat: float
    lon: float


@dataclass
class PedestrianCrossing:
    id: int
    lat: float
    lon: float
    is_regulated: bool  # True si feu de circulation


@dataclass
class Intersection:
    id: IntersectionId
    lat: float
    lon: float
    incoming: List[RoadId]
    outgoing: List[RoadId]
    light_state: List[Tuple[RoadId, LightColor]] = field(default_factory=list)


@dataclass
class Network:
    roads: List[Road]
    intersections: List[Intersection]
    feux: List[TrafficSignal]          = field(default_factory=list)
    passages: List[PedestrianCrossing] = field(default_factory=list)
    nodes: Dict[int, Tuple[float, float]] = field(default_factory=dict)  # node_id  (lat, lon)


@dataclass
class SimConfig:
    network: Network
    dt: float
    max_time: float
    random_seed: Optional[int] = None
