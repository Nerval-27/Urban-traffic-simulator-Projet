import heapq
import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple
from simulation.models import Network, Road

TRAFFIC_SIGNAL_ATTACH_MAX_DIST = 25.0


@dataclass
class GraphNode:
    node_id: int
    lat: float
    lon: float
    # Feu rattaché à ce point du graphe, si présent.
    has_traffic_light: bool = False
    traffic_light_id: Optional[int] = None


@dataclass
class GraphEdge:
    from_node: int
    to_node: int
    road_id: int          # identifiant de la rue OSM
    road_name: str        # nom affiché de la rue
    distance: float       # mètres
    speed_limit: float    # m/s
    weight: float         # temps estimé en secondes
    # Points intermédiaires de la rue, utiles pour garder le tracé.
    intermediate_nodes: List[int] = field(default_factory=list)


class RoadGraph:
    def __init__(self):
        self.nodes: Dict[int, GraphNode] = {}
        self.edges: Dict[int, List[GraphEdge]] = {}  # adjacence
        self.all_edges: List[GraphEdge] = []



    def build_from_network(self, network):
        # nodes utilises par les routes
        road_node_ids: set = set()
        for road in network.roads:
            for nid in road.nodes:
                road_node_ids.add(nid)

        # Nodes conservés dans le graphe routier.
        for nid in road_node_ids:
            if nid in network.nodes:
                lat, lon = network.nodes[nid]
                self.nodes[nid] = GraphNode(node_id=nid, lat=lat, lon=lon)
                self.edges[nid] = []

        for road in network.roads:
            self._add_road_edges(road)

        # Les feux sont rattachés après les arcs pour mieux repérer les carrefours.
        self._attach_traffic_signals(network)

        # Points possibles pour créer des véhicules.
        self._spawn_nodes: List[int] = [
            nid for nid, edges in self.edges.items() if len(edges) > 0
        ]

        print(f"[Graph] Construit : {len(self.nodes)} nœuds routiers, "
              f"{len(self.all_edges)} arcs, "
              f"{len(self._spawn_nodes)} nœuds de spawn valides")

    def _add_road_edges(self, road):
        nlist = road.nodes
        if len(nlist) < 2:
            return

        for i in range(len(nlist) - 1):
            n_from = nlist[i]
            n_to   = nlist[i + 1]

            if n_from not in self.nodes or n_to not in self.nodes:
                continue

            c1 = self.nodes[n_from]
            c2 = self.nodes[n_to]
            dist = haversine(c1.lat, c1.lon, c2.lat, c2.lon)

            if road.speed_limit <= 0:
                road.speed_limit = 11.1  # 40 km/h par défaut

            weight = dist / road.speed_limit  # temps en secondes

            edge = GraphEdge(
                from_node=n_from,
                to_node=n_to,
                road_id=road.id,
                road_name=road.name,
                distance=dist,
                speed_limit=road.speed_limit,
                weight=weight,
                intermediate_nodes=[]
            )
            self.edges[n_from].append(edge)
            self.all_edges.append(edge)


            if not road.oneway:
                reverse_edge = GraphEdge(
                    from_node=n_to,
                    to_node=n_from,
                    road_id=road.id,
                    road_name=road.name,
                    distance=dist,
                    speed_limit=road.speed_limit,
                    weight=weight,
                    intermediate_nodes=[]
                )
                self.edges[n_to].append(reverse_edge)



    def dijkstra(self, source, target,
                 edge_penalty: Optional[Callable[[GraphEdge], float]] = None):
        if source not in self.nodes or target not in self.nodes:
            return None

        dist: Dict[int, float] = {nid: math.inf for nid in self.nodes}
        dist[source] = 0.0

        prev: Dict[int, Optional[int]] = {nid: None for nid in self.nodes}

        pq = [(0.0, source)]

        visited = set()

        while pq:
            cost, u = heapq.heappop(pq)

            if u in visited:
                continue
            visited.add(u)

            if u == target:
                break

            for edge in self.edges.get(u, []):
                v = edge.to_node
                if v in visited:
                    continue
                penalty = edge_penalty(edge) if edge_penalty else 0.0
                new_cost = cost + edge.weight + max(0.0, penalty)
                if new_cost < dist[v]:
                    dist[v] = new_cost
                    prev[v] = u
                    heapq.heappush(pq, (new_cost, v))

        if dist[target] == math.inf:
            return None

        path = []
        cur = target
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()

        return path

    def get_path_coordinates(self, path):
        coords = []
        for nid in path:
            if nid in self.nodes:
                n = self.nodes[nid]
                coords.append((n.lat, n.lon))
        return coords


    def _find_closest_node(self, lat, lon, max_distance: float = math.inf):
        best_id = None
        best_dist = max_distance
        for nid, node in self.nodes.items():
            d = haversine(lat, lon, node.lat, node.lon)
            if d < best_dist:
                best_dist = d
                best_id = nid
        return best_id

    def _attach_traffic_signals(self, network) -> None:
        road_degrees = self._compute_road_degrees()
        for signal in network.feux:
            closest = signal.id if signal.id in self.nodes else None
            if closest is None:
                closest = self._find_closest_signal_node(
                    signal.lat, signal.lon,
                    max_distance=TRAFFIC_SIGNAL_ATTACH_MAX_DIST,
                    road_degrees=road_degrees,
                )
            if closest is not None:
                self.nodes[closest].has_traffic_light = True
                self.nodes[closest].traffic_light_id = signal.id

    def _find_closest_signal_node(self, lat, lon,
                                  max_distance: float = math.inf,
                                  road_degrees: Optional[Dict[int, int]] = None):
        road_degrees = road_degrees or self._compute_road_degrees()
        # On préfère un vrai carrefour quand le feu OSM est légèrement décalé.
        closest_intersection = self._find_closest_connected_node(
            lat, lon,
            max_distance=max_distance,
            require_intersection=True,
            road_degrees=road_degrees,
        )
        if closest_intersection is not None:
            return closest_intersection

        return self._find_closest_connected_node(
            lat, lon,
            max_distance=max_distance,
            require_intersection=False,
            road_degrees=road_degrees,
        )

    def _find_closest_connected_node(self, lat, lon,
                                     max_distance: float = math.inf,
                                     require_intersection: bool = False,
                                     road_degrees: Optional[Dict[int, int]] = None):
        road_degrees = road_degrees or self._compute_road_degrees()
        best_id = None
        best_dist = max_distance
        for nid, node in self.nodes.items():
            degree = road_degrees.get(nid, 0)
            if degree <= 0:
                continue
            if require_intersection and degree < 3:
                continue
            d = haversine(lat, lon, node.lat, node.lon)
            if d < best_dist:
                best_dist = d
                best_id = nid
        return best_id

    def _compute_road_degrees(self) -> Dict[int, int]:
        neighbors: Dict[int, set] = {nid: set() for nid in self.nodes}
        for edge in self.all_edges:
            neighbors.setdefault(edge.from_node, set()).add(edge.to_node)
            neighbors.setdefault(edge.to_node, set()).add(edge.from_node)
        return {nid: len(vals) for nid, vals in neighbors.items()}

    def get_random_node_ids(self, count, rng):
        """Retourne une liste de node_ids aléatoires pour le spawn."""
        pool = getattr(self, '_spawn_nodes', list(self.nodes.keys()))
        if len(pool) < count:
            return list(pool)
        return rng.sample(pool, count)

    def get_spawn_nodes(self) -> List[int]:
        """Retourne tous les node_ids valides pour spawner un véhicule."""
        return getattr(self, '_spawn_nodes', list(self.nodes.keys()))

    def node_count(self) -> int:
        return len(self.nodes)

    def edge_count(self) -> int:
        return len(self.all_edges)


def haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
