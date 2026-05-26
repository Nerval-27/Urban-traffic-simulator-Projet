"""Structures de donnees partagees par le chargement, le graphe et la simulation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Optional, Dict


# Aliases de types : ils restent des int a l'execution, mais rendent
# les signatures plus lisibles quand on manipule beaucoup d'identifiants.
IntersectionId = int
RoadId         = int
VehicleId      = int
NodeId         = int


class LightColor(Enum):
    """Couleurs possibles pour un feu dans les donnees de modele."""
    RED    = "Red"
    GREEN  = "Green"
    YELLOW = "Yellow"


@dataclass
class Road:
    """Route issue d OpenStreetMap avec son trace et ses proprietes."""
    id: RoadId
    length: float
    speed_limit: float
    nodes: List[NodeId]
    next: NodeId
    oneway: bool = False
    name: str = "Inconnue"


@dataclass
class TrafficSignal:
    """Feu de circulation localise par un identifiant et une position GPS."""
    id: int
    lat: float
    lon: float


@dataclass
class PedestrianCrossing:
    """Passage pieton localise, avec ou sans regulation par feu."""
    id: int
    lat: float
    lon: float
    is_regulated: bool  # True si feu de circulation


@dataclass
class Intersection:
    """Carrefour theorique avec ses routes entrantes et sortantes."""
    id: IntersectionId
    lat: float
    lon: float
    incoming: List[RoadId]
    outgoing: List[RoadId]
    light_state: List[Tuple[RoadId, LightColor]] = field(default_factory=list)


@dataclass
class Network:
    """Ensemble des routes, feux, passages pietons et noeuds GPS charges."""
    roads: List[Road]
    intersections: List[Intersection]
    feux: List[TrafficSignal]          = field(default_factory=list)
    passages: List[PedestrianCrossing] = field(default_factory=list)
    nodes: Dict[int, Tuple[float, float]] = field(default_factory=dict)  # node_id  (lat, lon)


@dataclass
class SimConfig:
    """Configuration minimale d une simulation non graphique."""
    network: Network
    dt: float
    max_time: float
    random_seed: Optional[int] = None
