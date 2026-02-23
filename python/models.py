from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional

# Identifiants
IntersectionId = int
RoadId = int
VehicleId = int
NodeId = int

class LightColor(Enum):
    RED = "Red"
    GREEN = "Green"
    YELLOW = "Yellow"

@dataclass
class Road:
    id: RoadId
    length: float
    speed_limit: float
    nodes: List[NodeId]
    next: NodeId
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
    is_regulated: bool  # True if it has traffic lights

@dataclass
class Intersection:
    id: IntersectionId
    lat: float
    lon: float
    incoming: List[RoadId]
    outgoing: List[RoadId]
    light_state: List[Tuple[RoadId, LightColor]] = field(default_factory=list)

@dataclass
class Vehicle:
    id: VehicleId
    current_road: RoadId
    position: float
    speed: float

@dataclass
class State:
    queue_lengths: List[int]
    light_config: List[LightColor]

class Action:
    pass

@dataclass
class SwitchLights(Action):
    lights: List[Tuple[RoadId, LightColor]]

@dataclass
class Keep(Action):
    pass

@dataclass
class TrafficStats:
    mean_travel_time: float
    mean_queue_length: float
    throughput: float

@dataclass
class Snapshot:
    time: float
    state: State
    vehicles: List[Vehicle]

SimulationTrace = List[Snapshot]

@dataclass
class Network:
    roads: List[Road]
    intersections: List[Intersection]
    feux: List[TrafficSignal] = field(default_factory=list)
    passages: List[PedestrianCrossing] = field(default_factory=list)
    nodes: dict = field(default_factory=dict) # Mapping NodeId -> (lat, lon)

@dataclass
class SimConfig:
    network: Network
    initial_vehicles: List[Vehicle]
    dt: float
    max_time: float
    random_seed: Optional[int] = None
