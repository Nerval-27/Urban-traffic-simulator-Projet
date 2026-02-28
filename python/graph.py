import heapq
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from models import Network, Road


@dataclass
class GraphNode:
    node_id: int
    lat: float
    lon: float
    # Indique si ce nœud possède un feu de circulation
    has_traffic_light: bool = False
    # ID du feu associé (pour interroger le TrafficLightManager)
    traffic_light_id: Optional[int] = None


@dataclass
class GraphEdge:
    from_node: int
    to_node: int
    road_id: int          # ID de la Way OSM d'origine
    road_name: str        # Nom de la rue (pour affichage/debug)
    distance: float       # Distance en mètres
    speed_limit: float    # Vitesse limite en m/s
    weight: float         # Poids = distance / speed_limit (temps estimé en secondes)
    # Liste ordonnée des nodes OSM traversés (pour dessiner le chemin exact)
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

        # 2. Créer les GraphNodes uniquement pour ces nodes-là
        for nid in road_node_ids:
            if nid in network.nodes:
                lat, lon = network.nodes[nid]
                self.nodes[nid] = GraphNode(node_id=nid, lat=lat, lon=lon)
                self.edges[nid] = []

        # 3. Marquer les nœuds qui ont un feu de circulation
        #    On cherche le node routier le plus proche de chaque feu OSM
        for signal in network.feux:
            closest = self._find_closest_node(signal.lat, signal.lon)
            if closest is not None:
                self.nodes[closest].has_traffic_light = True
                self.nodes[closest].traffic_light_id = signal.id

        # 4. Construire les arcs depuis les routes
        for road in network.roads:
            self._add_road_edges(road)

        # 5. Liste des nodes valides pour le spawn = nodes avec au moins 1 arc sortant
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

            # Les deux nœuds doivent exister dans le graphe
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



    def dijkstra(self, source, target):
        if source not in self.nodes or target not in self.nodes:
            return None

        # dist[nid] = meilleur temps connu pour atteindre nid
        dist: Dict[int, float] = {nid: math.inf for nid in self.nodes}
        dist[source] = 0.0

        # prev[nid] = nœud précédent sur le chemin optimal
        prev: Dict[int, Optional[int]] = {nid: None for nid in self.nodes}

        # Priority queue : (coût, node_id)
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
                new_cost = cost + edge.weight
                if new_cost < dist[v]:
                    dist[v] = new_cost
                    prev[v] = u
                    heapq.heappush(pq, (new_cost, v))

        # Reconstruction du chemin
        if dist[target] == math.inf:
            return None  # Pas de chemin

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


    def _find_closest_node(self, lat, lon):
        best_id = None
        best_dist = math.inf
        for nid, node in self.nodes.items():
            d = haversine(lat, lon, node.lat, node.lon)
            if d < best_dist:
                best_dist = d
                best_id = nid
        return best_id

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
